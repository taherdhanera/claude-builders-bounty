"""Pure boundary regressions; author has not executed this file."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from guard_fixture_paths import check
from native_http_recorder import MODEL, allowed_path, validate_request
from run_native_ollama_linux import (GIB, digest, gate_resources, inspect_local_manifests,
    parse_pinned_registry_manifest, parse_stream, verify_installed_blobs)


class NativeBoundaryTests(unittest.TestCase):
    def request(self):
        return dict(model=MODEL, max_tokens=4096, stream=True,
            tools=[dict(name='Read'), dict(name='Glob'), dict(name='Grep')],
            messages=[dict(role='user', content='unchanged prompt')],
            safeguards=[dict(type='dangerous_tool_use', classifier_context=dict(permission_mode='plan', restricted=True))])

    def test_request_validation_does_not_translate_or_repair(self):
        payload = self.request()
        payload['messages'].append(dict(role='assistant', content=[dict(type='tool_use', name='Glob<|channel|>commentary', id='raw-id', input={})]))
        raw = json.dumps(payload, indent=3).encode()
        self.assertEqual(validate_request(raw), payload)
        self.assertIn(b'Glob<|channel|>commentary', raw)

    def test_unsafe_declared_tool_is_rejected(self):
        payload = self.request()
        payload['tools'].append(dict(name='Bash'))
        with self.assertRaises(ValueError):
            validate_request(json.dumps(payload).encode())

    def test_other_model_duplicate_tools_and_oversized_output_rejected(self):
        for field, value in [('model', 'qwen3.5:9b'), ('max_tokens', 4097), ('max_tokens', True),
                             ('tools', [dict(name='Read'), dict(name='Read')])]:
            with self.subTest(field=field, value=value):
                payload = self.request()
                payload[field] = value
                with self.assertRaises(ValueError):
                    validate_request(json.dumps(payload).encode())

    def test_native_paths_are_exact(self):
        self.assertTrue(allowed_path('/v1/messages'))
        self.assertTrue(allowed_path('/v1/messages?beta=true'))
        for path in ['/api/generate', '/v1/messages?beta=false', '/v1/messages?beta=true&model=x',
                     'https://external.invalid/v1/messages', '/v1/messages#fragment']:
            self.assertFalse(allowed_path(path))

    def test_system_string_notice_does_not_hide_complete_terminal_result(self):
        events = [dict(type='system', message='notice'), dict(type='result', subtype='success', is_error=False, stop_reason='end_turn')]
        self.assertTrue(parse_stream('\n'.join(map(json.dumps, events)))['nonErrorCompleteResultObserved'])

    def test_success_exit_equivalent_does_not_override_incomplete_stream(self):
        result = dict(type='result', subtype='success', is_error=False, stop_reason='end_turn')
        for text in [json.dumps(result) + '\nnot-json', json.dumps(result) + '\n' + json.dumps(dict(type='assistant')),
                     json.dumps(dict(type='result', subtype='success', is_error=False, stop_reason='max_tokens')),
                     json.dumps(result) + '\n' + json.dumps(result)]:
            self.assertFalse(parse_stream(text)['nonErrorCompleteResultObserved'])

    def test_guard_rejects_escape_and_all_mutating_tools(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Path(temporary) / 'fixture'
            fixture.mkdir()
            self.assertTrue(check(dict(tool_name='Read', tool_input=dict(file_path='CLAUDE.md')), fixture))
            for tool, data in [('Read', dict(file_path='../outside')), ('Glob', dict(pattern='../**')),
                               ('Bash', dict(command='true')), ('Write', dict(file_path='CLAUDE.md')),
                               ('ExitPlanMode', {})]:
                self.assertFalse(check(dict(tool_name=tool, tool_input=data), fixture))

    def test_measured_resource_gate_cannot_assume_advertised_capacity(self):
        sample = dict(memory=dict(MemTotalBytes=16 * GIB, MemAvailableBytes=12 * GIB), cpuCount=4, diskFreeBytes=14 * GIB)
        gate_resources(sample, 12 * GIB)
        for key, value in [('cpuCount', 2), ('diskFreeBytes', 11 * GIB)]:
            changed = {**sample, key: value}
            with self.assertRaises(RuntimeError):
                gate_resources(changed, 12 * GIB)
        for key, value in [('MemTotalBytes', 8 * GIB), ('MemAvailableBytes', 10 * GIB)]:
            changed = {**sample, 'memory': {**sample['memory'], key: value}}
            with self.assertRaises(RuntimeError):
                gate_resources(changed, 12 * GIB)

    def manifest(self, blob_bytes=b'owned fixture weight bytes'):
        config = b'owned fixture config bytes'
        return dict(schemaVersion=2, config=dict(digest='sha256:' + digest(config), size=len(config)),
                    layers=[dict(digest='sha256:' + digest(blob_bytes), size=len(blob_bytes))]), config, blob_bytes

    def test_pinned_registry_bytes_are_authoritative_not_semantic_json_only(self):
        manifest, _, _ = self.manifest()
        raw = json.dumps(manifest, separators=(',', ':')).encode()
        with patch('run_native_ollama_linux.MODEL_DIGEST', digest(raw)):
            self.assertEqual(parse_pinned_registry_manifest(raw), manifest)
            with self.assertRaisesRegex(RuntimeError, 'SHA256 differs'):
                parse_pinned_registry_manifest(json.dumps(manifest, indent=2).encode())

    def test_missing_old_manifest_layout_is_diagnostic_only(self):
        manifest, _, _ = self.manifest()
        with tempfile.TemporaryDirectory() as temporary:
            store = Path(temporary)
            path = store / 'manifests/ollama.com/library/qwen3.5/9b-q4_K_M'
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(manifest, indent=2))
            observed = inspect_local_manifests(store, manifest)
            self.assertFalse(observed['authoritative'])
            self.assertFalse(observed['truncated'])
            self.assertEqual(len(observed['files']), 1)
            self.assertTrue(observed['files'][0]['semanticRegistryJsonMatch'])
            self.assertFalse(observed['files'][0]['exactRegistryBytesMatch'])
            self.assertFalse((store / 'manifests/registry.ollama.ai').exists())

    def test_every_installed_blob_is_hashed_and_tampering_fails_with_receipt(self):
        manifest, config, weight = self.manifest()
        with tempfile.TemporaryDirectory() as temporary:
            store = Path(temporary)
            blobs = store / 'blobs'
            blobs.mkdir()
            for value in (config, weight):
                (blobs / ('sha256-' + digest(value))).write_bytes(value)
            checks = verify_installed_blobs(store, manifest, store / 'first-check.json')
            self.assertEqual(len(checks), 2)
            self.assertTrue(all(item['matched'] for item in checks))
            (blobs / ('sha256-' + digest(weight))).write_bytes(b'x' * len(weight))
            with self.assertRaisesRegex(RuntimeError, 'blob SHA256 differs'):
                verify_installed_blobs(store, manifest, store / 'tamper-check.json')
            receipt = json.loads((store / 'tamper-check.json').read_bytes())
            self.assertFalse(receipt['allMatched'])
            self.assertEqual(receipt['checkedBlobCount'], 2)

    def test_missing_expected_blob_stops_instead_of_guessing_another_file(self):
        manifest, config, weight = self.manifest()
        with tempfile.TemporaryDirectory() as temporary:
            store = Path(temporary)
            blobs = store / 'blobs'
            blobs.mkdir()
            (blobs / ('sha256-' + digest(config))).write_bytes(config)
            (blobs / 'some-other-weight-file').write_bytes(weight)
            with self.assertRaisesRegex(RuntimeError, 'missing, nonregular, or outside'):
                verify_installed_blobs(store, manifest, store / 'missing-check.json')
            receipt = json.loads((store / 'missing-check.json').read_bytes())
            self.assertFalse(receipt['allMatched'])
            self.assertFalse(receipt['blobs'][-1]['exists'])


if __name__ == '__main__':
    unittest.main()
