"""Pure validator tests only. Synthetic values below are not execution evidence."""
import copy
import json
from pathlib import Path
import unittest

import offline_unknown_tool_probe as probe


class UnknownToolChecks(unittest.TestCase):
    def cycle(self, *, array_content=False):
        ident = "synthetic-unit-tool-id"
        arguments = {"path": "", "pattern": "db/schema.ts"}
        text = f"Synthetic unit error: No such tool available: {probe.RAW_TOOL_NAME}"
        content = [{"type": "text", "text": text}] if array_content else text
        original = dict(messages=[
            dict(role="assistant", content=[dict(type="tool_use", id=ident,
                 name=probe.RAW_TOOL_NAME, input=arguments)]),
            dict(role="user", content=[dict(type="tool_result", tool_use_id=ident,
                 is_error=True, content=content)]),
        ])
        converted = dict(messages=[
            dict(role="assistant", content=None, tool_calls=[dict(id=ident, type="function",
                 function=dict(name=probe.RAW_TOOL_NAME, arguments=json.dumps(arguments)))]),
            dict(role="tool", tool_call_id=ident,
                 content=json.dumps(dict(is_error=True, content=text))),
        ])
        return original, converted, ident, arguments

    def test_string_and_array_error_content_preserved(self):
        for array_content in (False, True):
            original, converted, ident, arguments = self.cycle(array_content=array_content)
            before = copy.deepcopy((original, converted))
            result = probe.check_actual_error(original, converted, ident, arguments)
            self.assertTrue(result["unknownToolCycleRoundTripPreserved"])
            self.assertEqual((original, converted), before)

    def test_missing_or_false_error_marker_fails(self):
        for marker in (None, False, "true", 1):
            original, converted, ident, arguments = self.cycle()
            original["messages"][1]["content"][0]["is_error"] = marker
            with self.subTest(marker=marker), self.assertRaises(ValueError):
                probe.check_actual_error(original, converted, ident, arguments)

    def test_renaming_either_side_fails(self):
        for side in ("original", "converted"):
            original, converted, ident, arguments = self.cycle()
            if side == "original":
                original["messages"][0]["content"][0]["name"] = "Glob"
            else:
                converted["messages"][0]["tool_calls"][0]["function"]["name"] = "Glob"
            with self.subTest(side=side), self.assertRaises(ValueError):
                probe.check_actual_error(original, converted, ident, arguments)

    def test_changed_error_text_or_arguments_fails(self):
        for change in ("error", "arguments", "duplicate"):
            original, converted, ident, arguments = self.cycle()
            if change == "error":
                converted["messages"][1]["content"] = json.dumps(dict(is_error=True, content="Invented"))
            elif change == "arguments":
                converted["messages"][0]["tool_calls"][0]["function"]["arguments"] = "{}"
            else:
                original["messages"][1]["content"] *= 2
            with self.subTest(change=change), self.assertRaises(ValueError):
                probe.check_actual_error(original, converted, ident, arguments)

    def test_no_user_credentials_or_proxy_settings_forwarded(self):
        environment = probe.probe_environment(dict(HOME=str(Path.cwd() / "synthetic-isolated-probe-home"), PATH="/usr/bin",
            ANTHROPIC_API_KEY="synthetic-sensitive-test-only", CLAUDE_CODE_OAUTH_TOKEN="synthetic-test-only",
            GITHUB_TOKEN="synthetic-test-only", HTTPS_PROXY="https://unused.invalid"), "http://127.0.0.1:12345")
        self.assertEqual(environment["ANTHROPIC_API_KEY"], "")
        self.assertEqual(environment["ANTHROPIC_AUTH_TOKEN"], "offline-unknown-tool-probe-only")
        self.assertEqual(environment["CLAUDE_CODE_MAX_RETRIES"], "0")
        self.assertFalse({"GITHUB_TOKEN", "HTTPS_PROXY", "CLAUDE_CODE_OAUTH_TOKEN"} & set(environment))


if __name__ == "__main__":
    unittest.main()
