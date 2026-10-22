"""Offline fixture evidence regressions: raw bytes, complete inventories, and mutation guards."""
from contextlib import contextmanager
import hashlib
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch

import run_native_ollama_linux as runner


class FixtureObservationTests(unittest.TestCase):
    def test_hashes_and_sizes_cover_the_same_complete_file_inventory(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Path(temporary)
            contents = {
                'CLAUDE.md': '\u0052\u00e9sum\u00e9 \u2014 project\n'.encode('utf-8'),
                '.hidden': b'\x00\xff\x01',
                'app/page.tsx': b'export default function Page() { return null; }\n',
                'public/empty': b'',
            }
            for name, raw in contents.items():
                target = fixture / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
            (fixture / '.git').mkdir()
            (fixture / '.git/config').write_bytes(b'excluded disposable git bookkeeping')
            (fixture / 'empty-directory').mkdir()

            hashes, sizes = runner.fixture_observation(fixture)
            self.assertEqual(hashes, {name: hashlib.sha256(raw).hexdigest() for name, raw in contents.items()})
            self.assertEqual(sizes, {name: len(raw) for name, raw in contents.items()})
            self.assertEqual(hashes.keys(), sizes.keys())
            self.assertEqual(runner.fixture_observation(fixture), (hashes, sizes))
            self.assertGreater(sizes['CLAUDE.md'], len(contents['CLAUDE.md'].decode('utf-8')))

    def test_size_changes_and_inventory_additions_or_removals_are_observable(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Path(temporary)
            target = fixture / 'CLAUDE.md'
            target.write_bytes(b'initial')
            before_hashes, before_sizes = runner.fixture_observation(fixture)
            target.write_bytes(b'a longer changed file')
            after_hashes, after_sizes = runner.fixture_observation(fixture)
            self.assertNotEqual(before_hashes, after_hashes)
            self.assertNotEqual(before_sizes, after_sizes)
            self.assertEqual(after_sizes['CLAUDE.md'], len(b'a longer changed file'))

            (fixture / 'new-empty-file').write_bytes(b'')
            added_hashes, added_sizes = runner.fixture_observation(fixture)
            self.assertEqual(set(added_hashes), {'CLAUDE.md', 'new-empty-file'})
            self.assertEqual(set(added_sizes), set(added_hashes))
            self.assertNotEqual(after_sizes, added_sizes)
            target.unlink()
            removed_hashes, removed_sizes = runner.fixture_observation(fixture)
            self.assertEqual(set(removed_hashes), {'new-empty-file'})
            self.assertEqual(removed_sizes, {'new-empty-file': 0})

    def test_same_size_edit_cannot_pass_the_retained_hash_gate(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Path(temporary)
            target = fixture / 'CLAUDE.md'
            target.write_bytes(b'one')
            before_hashes, before_sizes = runner.fixture_observation(fixture)
            target.write_bytes(b'two')
            after_hashes, after_sizes = runner.fixture_observation(fixture)
            self.assertEqual(before_sizes, after_sizes)
            self.assertNotEqual(before_hashes, after_hashes)
            result = dict(processCompletedSuccessfully=True, fixtureUnchanged=before_hashes == after_hashes,
                          fixtureSizesUnchanged=before_sizes == after_sizes, nonErrorCompleteResultObserved=True,
                          noUnexpectedToolAttemptsObserved=True, noToolErrorsObserved=True,
                          nativeHttpEvidenceComplete=True)
            self.assertFalse(runner.structural_run_complete(result))

    def test_changed_file_during_observation_fails_without_partial_result(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Path(temporary)
            target = fixture / 'CLAUDE.md'
            target.write_bytes(b'initial')
            original_open = Path.open

            @contextmanager
            def open_then_mutate(path, *args, **kwargs):
                with original_open(path, *args, **kwargs) as stream:
                    yield stream
                if path == target and args == ('rb',):
                    target.write_bytes(b'changed and longer')

            with patch.object(Path, 'open', open_then_mutate):
                with self.assertRaisesRegex(RuntimeError, 'changed during observation'):
                    runner.fixture_observation(fixture)

    def test_file_and_directory_symlinks_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            fixture = base / 'fixture'
            fixture.mkdir()
            outside = base / 'outside'
            outside.mkdir()
            (outside / 'private.txt').write_bytes(b'must not be inventoried')
            for directory in (False, True):
                with self.subTest(directory=directory):
                    link = fixture / ('linked-directory' if directory else 'linked-file')
                    try:
                        link.symlink_to(outside if directory else outside / 'private.txt', target_is_directory=directory)
                    except OSError as error:
                        if sys.platform != 'win32':
                            raise  # The Linux workflow must execute actual symlink checks, never skip them.
                        self.skipTest('Host cannot create symlinks: ' + str(error))
                    try:
                        with self.assertRaisesRegex(RuntimeError, 'Unexpected fixture symlink'):
                            runner.fixture_observation(fixture)
                    finally:
                        link.unlink()

    def test_reported_symlink_file_or_directory_is_rejected_without_host_privilege(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Path(temporary)
            target_file = fixture / 'file'
            target_file.write_bytes(b'not read when reported as a symlink')
            target_directory = fixture / 'directory'
            target_directory.mkdir()
            original_is_symlink = Path.is_symlink
            for target in (target_file, target_directory):
                with self.subTest(target=target.name):
                    with patch.object(Path, 'is_symlink', lambda path: path == target or original_is_symlink(path)):
                        with self.assertRaisesRegex(RuntimeError, 'Unexpected fixture symlink'):
                            runner.fixture_observation(fixture)

    def test_reported_symlink_root_is_rejected_without_host_privilege(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Path(temporary)
            original_is_symlink = Path.is_symlink
            with patch.object(Path, 'is_symlink', lambda path: path == fixture or original_is_symlink(path)):
                with self.assertRaisesRegex(RuntimeError, 'Fixture root'):
                    runner.fixture_observation(fixture)

    def test_symlink_root_and_missing_root_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            with self.assertRaisesRegex(RuntimeError, 'Fixture root'):
                runner.fixture_observation(base / 'missing')
            fixture = base / 'fixture'
            fixture.mkdir()
            link = base / 'root-link'
            try:
                link.symlink_to(fixture, target_is_directory=True)
            except OSError as error:
                if sys.platform != 'win32':
                    raise  # The Linux workflow must execute actual symlink checks, never skip them.
                self.skipTest('Host cannot create symlinks: ' + str(error))
            with self.assertRaisesRegex(RuntimeError, 'Fixture root'):
                runner.fixture_observation(link)


if __name__ == '__main__':
    unittest.main()
