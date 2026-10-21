"""Pure parser/body checks only: no engine, model, socket, process or network."""
import json
import unittest

from run_free_n8n_linux import raw_engine_data, validate_sink_body


class EngineOutputParsingTests(unittest.TestCase):
    def setUp(self):
        self.data = {'resultData': {'runData': {'Observed Node': [{'executionStatus': 'success'}]}}}

    def test_complete_raw_shape_with_log_prefix(self):
        raw = b'Engine startup log\n' + json.dumps(self.data).encode() + b'\n'
        self.assertEqual(raw_engine_data(raw), self.data)

    def test_pretty_wrapped_actual_data_is_not_counted_twice(self):
        raw = json.dumps({'finished': True, 'data': self.data}, indent=2).encode()
        self.assertEqual(raw_engine_data(raw), self.data)

    def test_unrelated_json_log_does_not_supply_run_data(self):
        raw = b'{"level":"info","message":"startup"}\n' + json.dumps(self.data).encode()
        self.assertEqual(raw_engine_data(raw), self.data)

    def test_two_identical_complete_objects_are_ambiguous(self):
        raw = json.dumps(self.data).encode()
        with self.assertRaises(RuntimeError):
            raw_engine_data(raw + b'\n' + raw)

    def test_two_different_complete_objects_are_ambiguous(self):
        other = {'resultData': {'runData': {'Different Node': []}}}
        with self.assertRaises(RuntimeError):
            raw_engine_data(json.dumps(self.data).encode() + b'\n' + json.dumps(other).encode())

    def test_rejects_missing_wrong_and_truncated_data(self):
        for raw in (b'plain log only', b'{}', b'{"resultData":null}',
                    b'{"resultData":{"runData":[]}}', b'{"resultData":', b'\xff'):
            with self.subTest(raw=raw), self.assertRaises(RuntimeError):
                raw_engine_data(raw)

    def test_incomplete_outer_document_cannot_supply_nested_fragment(self):
        raw = json.dumps({'data': self.data}, indent=2).encode().rstrip()[:-1]
        with self.assertRaises(RuntimeError):
            raw_engine_data(raw)


class SinkBodyValidationTests(unittest.TestCase):
    def check_payload(self, payload):
        raw = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        return validate_sink_body(raw, len(raw))

    def test_preserves_actual_multiline_unicode_body(self):
        payload = {'content': 'Weekly summary\n"Renée" — मुंबई 🚀\tpath\\name'}
        self.assertEqual(self.check_payload(payload), payload)

    def test_rejects_wrong_fields_types_empty_and_oversized_message(self):
        for payload in ({}, [], {'content': ''}, {'content': 42}, {'content': 'ok', 'id': 'invented'},
                        {'content': 'x' * 1901}):
            with self.subTest(payload_type=type(payload).__name__), self.assertRaises(ValueError):
                self.check_payload(payload)

    def test_accepts_exact_message_boundary(self):
        self.assertEqual(self.check_payload({'content': 'x' * 1900})['content'], 'x' * 1900)

    def test_rejects_incomplete_malformed_and_invalid_utf8_bodies(self):
        raw = b'{"content":"actual"}'
        for body, length in ((raw, len(raw) + 1), (b'{"content":', 11), (b'\xff', 1),
                             (raw, True), (raw, 1_048_577), (b'', 0)):
            with self.subTest(length=length), self.assertRaises(ValueError):
                validate_sink_body(body, length)


if __name__ == '__main__':
    unittest.main()
