"""Offline phase regressions using captured run 39854899148 telemetry."""
import ast
import copy
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import run_native_ollama_linux as runner

WORK = Path(__file__).resolve().parent
CAPTURE = json.loads((WORK / 'resource-regression-fixture.json').read_bytes())
MIB = 1024 ** 2


class ResourcePhaseTests(unittest.TestCase):
    def test_actual_loading_paging_is_recorded_separately(self):
        before, after, stop = CAPTURE['beforeLoad'], CAPTURE['afterLoad'], CAPTURE['stop']['sample']
        self.assertGreater(runner.paging_bytes_since(after, before), 64 * MIB)
        self.assertEqual(after['pagingPages']['pswpout'], stop['pagingPages']['pswpout'])
        self.assertEqual(runner.paging_bytes_since(stop, after), (487 - 8) * 4096)
        self.assertIsNone(runner.resource_stop_reason(after, 'loading', before))
        self.assertIsNone(runner.resource_stop_reason(stop, 'inference', after))

    def test_ram_floor_is_enforced_in_both_phases(self):
        sample = copy.deepcopy(CAPTURE['afterLoad'])
        for phase in ('loading', 'inference'):
            sample['memory']['MemAvailableBytes'] = 768 * MIB - 1
            self.assertEqual(runner.resource_stop_reason(sample, phase, sample), 'RAM floor reached')
            sample['memory']['MemAvailableBytes'] = 768 * MIB
            self.assertIsNone(runner.resource_stop_reason(sample, phase, sample))

    def test_inference_cutoff_is_cumulative_and_unchanged(self):
        baseline = CAPTURE['afterLoad']
        first = copy.deepcopy(baseline)
        first['pagingPages']['pswpout'] += 8192
        self.assertIsNone(runner.resource_stop_reason(first, 'inference', baseline))
        second = copy.deepcopy(first)
        second['pagingPages']['pswpout'] += 8192
        self.assertEqual(runner.paging_bytes_since(second, baseline), 64 * MIB)
        self.assertIsNone(runner.resource_stop_reason(second, 'inference', baseline))
        second['pagingPages']['pswpin'] += 1
        self.assertEqual(runner.resource_stop_reason(second, 'inference', baseline),
                         'Inference-phase cumulative paging exceeded 64 MiB')

    def make_watch(self, directory):
        with patch.object(runner, 'resources', return_value=copy.deepcopy(CAPTURE['beforeLoad'])):
            return runner.ResourceWatch(directory, directory, SimpleNamespace(pid=-1))

    def test_actual_transition_is_durable_and_one_time(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            watch = self.make_watch(directory)
            with patch.object(runner, 'resources', return_value=copy.deepcopy(CAPTURE['afterLoad'])):
                with watch.lock:
                    watch.begin_inference()
            receipt_path = directory / 'resource-inference-baseline.json'
            raw = receipt_path.read_bytes()
            receipt = json.loads(raw)
            self.assertEqual(receipt['sample'], CAPTURE['afterLoad'])
            self.assertEqual(receipt['loadBaseline'], CAPTURE['beforeLoad'])
            self.assertGreater(receipt['observedLoadingPagingBytes'], 64 * MIB)
            self.assertFalse(receipt['baselineMayReset'])
            self.assertEqual(watch.phase, 'inference')
            with watch.lock:
                observation = watch.observe_locked(CAPTURE['stop']['sample'])
            self.assertEqual(observation['phase'], 'inference')
            self.assertEqual(observation['inferencePagingBytes'], 479 * 4096)
            self.assertIsNone(watch.failed)
            with self.assertRaisesRegex(RuntimeError, 'only once'):
                watch.begin_inference()
            self.assertEqual(receipt_path.read_bytes(), raw)

    def test_loading_ram_failure_is_sticky_and_blocks_launch(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            watch = self.make_watch(directory)
            low = copy.deepcopy(CAPTURE['afterLoad'])
            low['memory']['MemAvailableBytes'] = 700 * MIB
            with watch.lock:
                watch.observe_locked(low)
                first_failure = copy.deepcopy(watch.failed)
                watch.observe_locked(CAPTURE['afterLoad'])
            self.assertEqual(watch.failed, first_failure)
            with self.assertRaisesRegex(RuntimeError, 'cannot be cleared'):
                watch.begin_inference()
            self.assertEqual(watch.phase, 'loading')
            self.assertFalse((directory / 'resource-inference-baseline.json').exists())

    def test_immediate_prelaunch_requires_two_gib(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            watch = self.make_watch(directory)
            sample = copy.deepcopy(CAPTURE['afterLoad'])
            sample['memory']['MemAvailableBytes'] = 2 * runner.GIB - 1
            with patch.object(runner, 'resources', return_value=sample):
                with self.assertRaisesRegex(RuntimeError, 'available RAM is insufficient'):
                    watch.begin_inference()
            self.assertEqual(watch.phase, 'loading')
            self.assertFalse((directory / 'resource-inference-baseline.json').exists())

    def test_fresh_low_ram_at_transition_fails_and_latches(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            watch = self.make_watch(directory)
            sample = copy.deepcopy(CAPTURE['afterLoad'])
            sample['memory']['MemAvailableBytes'] = 700 * MIB
            with patch.object(runner, 'resources', return_value=sample):
                with self.assertRaisesRegex(RuntimeError, 'RAM guard failed'):
                    watch.begin_inference()
            self.assertEqual(watch.failed['reason'], 'RAM floor reached')
            self.assertEqual(watch.failed['phase'], 'loading')
            self.assertEqual(watch.phase, 'loading')

    def test_sampling_or_baseline_write_failure_does_not_arm_inference(self):
        for failing_stage in ('sample', 'write'):
            with self.subTest(stage=failing_stage), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                watch = self.make_watch(directory)
                resource_effect = OSError('missing telemetry') if failing_stage == 'sample' else None
                with patch.object(runner, 'resources', side_effect=resource_effect, return_value=CAPTURE['afterLoad']):
                    with patch.object(runner, 'write_json', side_effect=OSError('receipt cannot persist')):
                        with self.assertRaises(OSError):
                            watch.begin_inference()
                self.assertEqual(watch.phase, 'loading')
                self.assertEqual(watch.baseline, CAPTURE['beforeLoad'])

    def test_sampling_assessment_and_launch_share_lock(self):
        tree = ast.parse((WORK / 'run_native_ollama_linux.py').read_text())
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'ResourceWatch')
        monitor = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == 'monitor')
        monitor_locks = [node for node in ast.walk(monitor) if isinstance(node, ast.With)
                         and any(isinstance(item.context_expr, ast.Attribute) and item.context_expr.attr == 'lock'
                                 for item in node.items)]
        self.assertTrue(any('sample = resources(self.private)' in ast.unparse(node)
                            and 'self.observe_locked(sample)' in ast.unparse(node) for node in monitor_locks))
        main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'main')
        launch_lock = [node for node in ast.walk(main) if isinstance(node, ast.With)
                       and any(ast.unparse(item.context_expr) == 'watch.lock' for item in node.items)]
        self.assertEqual(len(launch_lock), 1)
        body = launch_lock[0].body
        self.assertEqual(len(body), 2)
        self.assertEqual(ast.unparse(body[0]), 'watch.begin_inference()')
        self.assertEqual(ast.unparse(body[1].value.func), 'subprocess.Popen')

    def test_monitor_error_is_latched_before_competing_launch_acquires_lock(self):
        for stage in ('open', 'sample', 'write', 'flush', 'close'):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                watch = self.make_watch(directory)
                fault_seen, released, competed = threading.Event(), threading.Event(), threading.Event()
                observed, errors = {}, []
                real_lock, original_open = threading.RLock(), Path.open

                class ReleaseWitnessLock:
                    def __enter__(self):
                        real_lock.acquire()
                        return self

                    def __exit__(self, *_):
                        first_release = (threading.current_thread().name == 'faulting-monitor'
                                         and fault_seen.is_set() and not released.is_set())
                        if first_release:
                            observed['failedAtFirstRelease'] = watch.failed is not None
                        real_lock.release()
                        if first_release:
                            released.set()
                            if not competed.wait(3):
                                errors.append('Competing launch did not run at the forced boundary.')

                watch.lock = ReleaseWitnessLock()

                def fault(label):
                    if label == stage:
                        fault_seen.set()
                        raise OSError('injected ' + label + ' failure')

                class Stream:
                    def write(self, _):
                        fault('write')
                        if stage == 'close':
                            watch.stop.set()

                    def flush(self):
                        fault('flush')

                    def close(self):
                        fault('close')

                def open_file(path, *args, **kwargs):
                    if path.name == 'model-resource-samples.jsonl':
                        fault('open')
                        return Stream()
                    return original_open(path, *args, **kwargs)

                def sample(_):
                    if threading.current_thread().name == 'faulting-monitor':
                        fault('sample')
                    return copy.deepcopy(CAPTURE['afterLoad'])

                def competing_launch():
                    if not released.wait(3):
                        errors.append('Monitor did not reach the failing release boundary.')
                        competed.set()
                        return
                    try:
                        with watch.lock:
                            watch.begin_inference()
                            observed['launchAllowed'] = True
                    except RuntimeError:
                        observed['launchAllowed'] = False
                    except Exception as error:
                        errors.append(str(error))
                    finally:
                        competed.set()

                def monitor():
                    try:
                        watch.monitor()
                    except Exception as error:
                        errors.append(str(error))

                with patch.object(runner, 'resources', side_effect=sample), patch.object(Path, 'open', open_file), \
                        patch.object(runner.os, 'killpg', create=True):
                    competitor = threading.Thread(target=competing_launch, name='competing-launch')
                    observer = threading.Thread(target=monitor, name='faulting-monitor')
                    competitor.start()
                    observer.start()
                    observer.join(5)
                    competitor.join(5)
                self.assertFalse(observer.is_alive())
                self.assertFalse(competitor.is_alive())
                self.assertEqual(errors, [])
                self.assertTrue(observed['failedAtFirstRelease'])
                self.assertFalse(observed['launchAllowed'])
                self.assertEqual(watch.phase, 'loading')
                self.assertEqual(watch.failed['reason'], 'Resource monitoring unavailable')
                self.assertFalse((directory / 'resource-inference-baseline.json').exists())


if __name__ == '__main__':
    unittest.main()
