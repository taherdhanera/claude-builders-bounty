"""Pure/local regression tests. No HTTP, models, subprocesses or real sleeps."""

import copy
import json
import tempfile
import unittest
from pathlib import Path

import anthropic_openai_bridge as bridge


def tool():
    return {"name": "Read", "description": "Read an allowed fixture", "input_schema": {
        "type": "object", "properties": {"file_path": {"type": "string"}}, "required": ["file_path"],
        "additionalProperties": False,
    }}


def request():
    return {"model": "claude-test", "max_tokens": 100, "stream": True,
            "messages": [{"role": "user", "content": "Read the fixture."}], "tools": [tool()]}


def response(tool_calls=False):
    message = {"role": "assistant", "content": "Read complete."}
    if tool_calls:
        message.update(content=None, tool_calls=[{"id": "call_1", "type": "function", "function": {
            "name": "Read", "arguments": '{"file_path":"fixture.txt"}',
        }}])
    return {"id": "chatcmpl_actual", "model": "openai-fast", "choices": [{"index": 0,
        "message": message, "finish_reason": "tool_calls" if tool_calls else "stop"}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 7, "total_tokens": 19}}


class ConversionTests(unittest.TestCase):
    def test_system_text_tools_and_output_cap(self):
        req = request()
        req.update(system=[{"type": "text", "text": "First", "cache_control": {"type": "ephemeral"}},
                           {"type": "text", "text": "Second"}], max_tokens=100_000)
        out = bridge.anthropic_to_openai(req)
        self.assertEqual(out["messages"][0], {"role": "system", "content": "First\nSecond"})
        self.assertEqual(out["model"], "openai-fast")
        self.assertFalse(out["stream"])
        self.assertEqual(out["max_tokens"], 4096)
        self.assertEqual(out["tools"][0]["function"]["parameters"], tool()["input_schema"])

    def test_complete_tool_cycle_preserves_ids_and_actual_results(self):
        req = request()
        req["messages"] += [
            {"role": "assistant", "content": [{"type": "text", "text": "Reading."},
                {"type": "tool_use", "id": "call_1", "name": "Read", "input": {"file_path": "fixture.txt"}}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "call_1",
                "content": [{"type": "text", "text": "actual fixture bytes"}]}, {"type": "text", "text": "Summarize."}]},
        ]
        out = bridge.anthropic_to_openai(req)
        self.assertEqual(out["messages"][1]["tool_calls"][0]["id"], "call_1")
        self.assertEqual(json.loads(out["messages"][1]["tool_calls"][0]["function"]["arguments"]), {"file_path": "fixture.txt"})
        self.assertEqual(out["messages"][2], {"role": "tool", "tool_call_id": "call_1", "content": "actual fixture bytes"})
        self.assertEqual(out["messages"][3], {"role": "user", "content": "Summarize."})

    def test_parallel_tool_results_can_arrive_in_either_order(self):
        req = request()
        req["messages"] += [
            {"role": "assistant", "content": [{"type": "tool_use", "id": i, "name": "Read", "input": {}} for i in ["a", "b"]]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": i, "content": i} for i in ["b", "a"]]},
        ]
        out = bridge.anthropic_to_openai(req)
        self.assertEqual([m["tool_call_id"] for m in out["messages"] if m["role"] == "tool"], ["b", "a"])

    def test_tool_error_is_preserved_explicitly(self):
        req = request()
        req["messages"] += [{"role": "assistant", "content": [{"type": "tool_use", "id": "a", "name": "Read", "input": {}}]},
                            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "a", "content": "denied", "is_error": True}]}]
        out = bridge.anthropic_to_openai(req)
        self.assertEqual(json.loads(out["messages"][-1]["content"]), {"is_error": True, "content": "denied"})

    def test_unknown_unresolved_duplicate_and_out_of_order_tools_fail(self):
        base = request()
        assistant = {"role": "assistant", "content": [{"type": "tool_use", "id": "a", "name": "Read", "input": {}}]}
        cases = [
            [assistant],
            [{"role": "user", "content": [{"type": "tool_result", "tool_use_id": "a", "content": "x"}]}],
            [assistant, {"role": "user", "content": "tool was skipped"}],
            [assistant, {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "a", "content": "x"},
                                                      {"type": "tool_result", "tool_use_id": "a", "content": "x"}]}],
            [{"role": "assistant", "content": [{"type": "tool_use", "id": "a", "name": "Read", "input": {}},
                                                  {"type": "text", "text": "out of order"}]}],
        ]
        for extra in cases:
            with self.subTest(extra=extra), self.assertRaises(bridge.ProtocolError):
                req = copy.deepcopy(base)
                req["messages"] += extra
                bridge.anthropic_to_openai(req)

    def test_unsupported_semantics_fail_before_provider(self):
        cases = [
            {"thinking": {"type": "enabled", "budget_tokens": 100}},
            {"messages": [{"role": "user", "content": [{"type": "image", "source": {}}]}]},
            {"output_config": {"effort": "medium"}}, {"max_tokens": True}, {"max_tokens": 0},
            {"tools": [tool(), tool()]}, {"stream": "true"}, {"temperature": float("nan")},
            {"tool_choice": {"type": "tool", "name": "Unavailable"}},
        ]
        for change in cases:
            with self.subTest(change=change), self.assertRaises(bridge.ProtocolError):
                bridge.anthropic_to_openai({**request(), **change})

    def test_specific_tool_and_serial_tool_option(self):
        req = request()
        req["tool_choice"] = {"type": "tool", "name": "Read", "disable_parallel_tool_use": True}
        out = bridge.anthropic_to_openai(req)
        self.assertEqual(out["tool_choice"], {"type": "function", "function": {"name": "Read"}})
        self.assertFalse(out["parallel_tool_calls"])

    def test_actual_response_text_usage_and_finish(self):
        out = bridge.openai_to_anthropic(response(), {"Read"})
        self.assertEqual(out["content"], [{"type": "text", "text": "Read complete."}])
        self.assertEqual(out["usage"], {"input_tokens": 12, "output_tokens": 7})
        self.assertEqual(out["stop_reason"], "end_turn")
        provider = response()
        provider["choices"][0]["finish_reason"] = "length"
        self.assertEqual(bridge.openai_to_anthropic(provider, {"Read"})["stop_reason"], "max_tokens")

    def test_actual_response_tool_json(self):
        out = bridge.openai_to_anthropic(response(True), {"Read"})
        self.assertEqual(out["content"], [{"type": "tool_use", "id": "call_1", "name": "Read", "input": {"file_path": "fixture.txt"}}])
        self.assertEqual(out["stop_reason"], "tool_use")

    def test_malformed_or_undeclared_provider_arguments_fail_closed(self):
        invalid = ["not json", "[]", '{"x":1,"x":2}', '{"x":NaN}', '"plain string"']
        for arguments in invalid:
            with self.subTest(arguments=arguments), self.assertRaises(bridge.ProtocolError):
                provider = response(True)
                provider["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = arguments
                bridge.openai_to_anthropic(provider, {"Read"})
        with self.assertRaises(bridge.ProtocolError):
            bridge.openai_to_anthropic(response(True), {"Other"})

    def test_provider_error_missing_usage_or_truncation_is_not_faked(self):
        providers = [{"error": {"message": "quota"}}, response(), response(True), response()]
        providers[1].pop("usage")
        providers[2]["choices"][0]["finish_reason"] = "length"
        providers[3]["usage"]["prompt_tokens"] = -1
        for provider in providers:
            with self.subTest(provider=provider), self.assertRaises(bridge.ProtocolError):
                bridge.openai_to_anthropic(provider, {"Read"})

    def test_actual_provider_reasoning_is_not_injected_into_answer_or_plan(self):
        provider = response()
        provider["choices"][0]["message"]["reasoning"] = "provider reasoning retained only in raw bytes"
        out = bridge.openai_to_anthropic(provider, {"Read"})
        self.assertEqual(out["content"], [{"type": "text", "text": "Read complete."}])
        self.assertNotIn("reasoning", bridge.encode(out).decode("utf-8"))

    def test_sse_text_reconstructs_exact_content_and_real_usage(self):
        msg = bridge.openai_to_anthropic(response(), {"Read"})
        frames = parse_sse(bridge.anthropic_sse(msg))
        self.assertEqual([f[0] for f in frames], ["message_start", "content_block_start", "content_block_delta", "content_block_stop", "message_delta", "message_stop"])
        self.assertEqual(frames[0][1]["message"]["usage"], {"input_tokens": 12, "output_tokens": 0})
        self.assertEqual(frames[2][1]["delta"]["text"], "Read complete.")
        self.assertEqual(frames[-2][1]["usage"], {"output_tokens": 7})
        self.assertEqual(frames[-2][1]["delta"]["stop_reason"], "end_turn")

    def test_sse_tool_arguments_reconstruct_exact_object(self):
        msg = bridge.openai_to_anthropic(response(True), {"Read"})
        frames = parse_sse(bridge.anthropic_sse(msg))
        self.assertEqual(frames[1][1]["content_block"], {"type": "tool_use", "id": "call_1", "name": "Read", "input": {}})
        self.assertEqual(json.loads(frames[2][1]["delta"]["partial_json"]), {"file_path": "fixture.txt"})
        self.assertEqual(frames[-2][1]["delta"]["stop_reason"], "tool_use")

    def test_raw_json_duplicate_and_nonfinite_values_rejected(self):
        for raw in [b'{"model":1,"model":2}', b'{"x":NaN}', b'\xff', b'{']:
            with self.subTest(raw=raw), self.assertRaises(bridge.ProtocolError):
                bridge.decode(raw)

    def test_header_guard(self):
        self.assertIsNone(bridge.quota_header_failure([("X-RateLimit-Remaining", "3")]))
        for headers in [[("Retry-After", "60")], [("WWW-Authenticate", "Bearer")], [("x-ratelimit-remaining", "0")], [("Quota-Remaining", "-1")]]:
            self.assertIsNotNone(bridge.quota_header_failure(headers))

    def test_observed_beta_route_only(self):
        for path in ["/v1/messages", "/v1/messages?", "/v1/messages?beta=true"]:
            self.assertEqual(bridge.message_route(path), "messages")
        self.assertEqual(bridge.message_route("/v1/messages/count_tokens?beta=true"), "count_tokens")
        for path in ["/v1/messages?beta=false", "/v1/messages?beta=true&extra=1", "/v1/messages?beta=true#fragment", "https://other/v1/messages", "/v1/messages/anything"]:
            self.assertIsNone(bridge.message_route(path))

    def test_ordered_system_turn_and_observed_effort_mapping(self):
        req = request()
        req["system"] = "original leading system"
        req["messages"] += [{"role": "system", "content": [{"type": "text", "text": "original environment turn"}]}]
        for effort in ["low", "high"]:
            req["output_config"] = {"effort": effort}
            out = bridge.anthropic_to_openai(req)
            self.assertEqual(out["reasoning_effort"], effort)
            self.assertEqual(out["messages"], [{"role": "system", "content": "original leading system"},
                                              {"role": "user", "content": "Read the fixture."},
                                              {"role": "system", "content": "original environment turn"}])

    def test_observed_safeguards_preserved_with_classifier_disclosure(self):
        req = request()
        req["safeguards"] = restricted_safeguards()
        original = copy.deepcopy(req)
        out = bridge.anthropic_to_openai(req)
        self.assertEqual(req, original)
        context = out["messages"][0]
        self.assertEqual(context["role"], "system")
        self.assertIn("does NOT implement Anthropic's server-side", context["content"])
        self.assertEqual(bridge.decode(context["content"].split("Original context:\n", 1)[1].encode()), req["safeguards"])

    def test_unsafe_safety_modes_types_and_executable_tools_rejected(self):
        for mutation in ["mode", "restricted", "type", "allow", "network", "remote", "auto"]:
            req = request()
            req["safeguards"] = restricted_safeguards()
            context = req["safeguards"][0]["classifier_context"]
            if mutation == "mode": context["permission_mode"] = "bypassPermissions"
            if mutation == "restricted": context["restricted"] = False
            if mutation == "type": req["safeguards"][0]["type"] = "different_classifier"
            if mutation == "allow": context["rules"]["allow"].append({"rule": "Bash", "source": "cliArg"})
            if mutation == "network": context["trusted_directories"]["network"] = ["remote"]
            if mutation == "remote": context["is_remote_mode"] = True
            if mutation == "auto": context["auto_mode"]["allow"] = ["Bash"]
            with self.subTest(mutation=mutation), self.assertRaises(bridge.ProtocolError):
                bridge.anthropic_to_openai(req)
        for name in ["Bash", "Write", "Edit", "Agent", "PowerShell", "mcp__ide__executeCode"]:
            req = request()
            req["tools"][0]["name"] = name
            with self.subTest(tool=name), self.assertRaises(bridge.ProtocolError):
                bridge.anthropic_to_openai(req)

    def test_actual_offline_capture_translation_preserves_original_fields(self):
        capture = Path(__file__).resolve().parents[2] / "watch-logs/free-execution-followup-20261021T125814Z/offline-cli-protocol/request-1.json"
        if not capture.is_file():
            self.skipTest("Root's actual offline capture is not installed on this runner")
        req = bridge.decode(capture.read_bytes())
        original = copy.deepcopy(req)
        out = bridge.anthropic_to_openai(req)
        self.assertEqual(req, original)
        self.assertEqual(out["reasoning_effort"], req["output_config"]["effort"])
        self.assertEqual({x["function"]["name"] for x in out["tools"]}, {"Read", "Glob", "Grep"})
        for source, translated in zip(req["tools"], out["tools"]):
            self.assertEqual(translated["function"]["parameters"], source["input_schema"])
            self.assertEqual(translated["function"]["description"], source["description"])
        translated_history = out["messages"][2:]
        self.assertEqual([m["role"] for m in translated_history], [m["role"] for m in req["messages"]])
        for source, translated in zip(req["messages"], translated_history):
            self.assertEqual(translated["content"], "\n".join(block["text"] for block in source["content"]))
        self.assertEqual(bridge.decode(out["messages"][1]["content"].split("Original context:\n", 1)[1].encode()), req["safeguards"])

    def test_stop_file_is_confined_to_evidence_children(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self.assertEqual(bridge.resolve_stop_file(root, Path("client-finished.stop")), root / "client-finished.stop")
            self.assertEqual(bridge.resolve_stop_file(root, root / "nested/finished.stop"), root / "nested/finished.stop")
            self.assertIsNone(bridge.resolve_stop_file(root, None))
            for path in [Path(".."), root, root.parent / "outside.stop"]:
                with self.subTest(path=path), self.assertRaises(bridge.ProtocolError):
                    bridge.resolve_stop_file(root, path)


def restricted_safeguards():
    return [{"type": "dangerous_tool_use", "classifier_context": {
        "v": 1, "permission_mode": "plan", "restricted": True, "platform": "linux", "is_remote_mode": False,
        "rules": {"allow": [{"rule": "Read", "source": "cliArg"}], "deny": [{"rule": "Bash", "source": "toolsNarrowing"}], "ask": []},
        "trusted_directories": {"primary": {"path": "/fixture", "resolved": ["/fixture"]}, "additional": [], "network": []},
        "auto_mode": {"allow": [], "soft_deny": [], "hard_deny": [], "environment": []},
    }}]


def parse_sse(raw):
    frames = []
    for frame in raw.decode("utf-8").split("\n\n"):
        if not frame:
            continue
        name, data = frame.split("\n", 1)
        frames.append((name.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return frames


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class FakeTransport:
    def __init__(self, clock, status=200, headers=None, raw=None):
        self.clock = clock
        self.status = status
        self.headers = [] if headers is None else headers
        self.raw = bridge.encode(response()) if raw is None else raw
        self.calls = []

    def exchange(self, raw, timeout):
        self.calls.append((self.clock(), raw, timeout))
        self.clock.now += 2
        return {"status": self.status, "reason": "fixture", "headers": self.headers,
                "body": self.raw, "complete": True, "error": None, "timed_out": False}


class FakeSocket:
    def __init__(self):
        self.timeouts = []
        self.shutdowns = []

    def settimeout(self, value):
        self.timeouts.append(value)

    def shutdown(self, how):
        self.shutdowns.append(how)


class FakeTimer:
    def __init__(self, seconds, callback):
        self.seconds = seconds
        self.callback = callback
        self.started = False
        self.cancelled = False
        self.daemon = False

    def start(self):
        self.started = True

    def cancel(self):
        self.cancelled = True


class AcceptedSocketBudgetTests(unittest.TestCase):
    def test_header_guard_is_absolute_and_whole_deadline_stays_armed(self):
        clock = FakeClock()
        connection = FakeSocket()
        timers = []

        def factory(seconds, callback):
            timer = FakeTimer(seconds, callback)
            timers.append(timer)
            return timer

        guard = bridge.AcceptedSocketGuard(connection, 1200.0, clock, factory)
        self.assertEqual([t.seconds for t in timers], [1200.0, 10.0])
        self.assertEqual(connection.timeouts, [10.0])
        self.assertTrue(all(t.started and t.daemon for t in timers))
        # Completing header parsing cancels only its phase, not the lifetime.
        guard.finish_phase()
        self.assertTrue(timers[1].cancelled)
        self.assertFalse(timers[0].cancelled)
        clock.now = 1197.0
        guard.start_phase()
        self.assertEqual(timers[-1].seconds, 3.0)
        self.assertEqual(connection.timeouts[-1], 3.0)
        # Timer expiry interrupts even a client trickling individual bytes.
        timers[0].callback()
        self.assertEqual(connection.shutdowns, [bridge.socket.SHUT_RDWR])
        guard.close()
        self.assertTrue(timers[0].cancelled)
        self.assertTrue(timers[-1].cancelled)

    def test_expired_budget_rejects_socket_before_request_parsing(self):
        clock = FakeClock()
        clock.now = 1200.0
        connection = FakeSocket()
        with self.assertRaises(TimeoutError):
            bridge.AcceptedSocketGuard(connection, 1200.0, clock, FakeTimer)
        self.assertEqual(connection.shutdowns, [bridge.socket.SHUT_RDWR])
        self.assertEqual(connection.timeouts, [])


class EvidenceAndBudgetTests(unittest.TestCase):
    def state(self, directory, **kwargs):
        clock = FakeClock()
        transport = FakeTransport(clock, **kwargs)
        state = bridge.BridgeState(Path(directory), [{"url": "fixture://source", "id": "test-source"}], transport, clock, clock.sleep)
        return state, clock, transport

    def perform(self, state):
        req = request()
        return state.perform(bridge.encode(req), req, bridge.anthropic_to_openai(req))

    def test_pacing_and_verbatim_evidence_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            state, clock, transport = self.state(directory)
            self.perform(state)
            self.perform(state)
            self.assertEqual(transport.calls[1][0] - 2, 40.0)
            self.assertEqual(clock.sleeps, [40.0])
            self.assertEqual(transport.calls[0][2], 180.0)
            record = json.loads((Path(directory) / "round-01/exchange.json").read_bytes())
            self.assertEqual((Path(directory) / "round-01/provider-request.json").read_bytes(), transport.calls[0][1])
            self.assertEqual((Path(directory) / "round-01/provider-response.bin").read_bytes(), transport.raw)
            for key in ["providerRequest", "providerResponse", "providerResponseHeaders", "anthropicResponse"]:
                self.assertEqual(bridge.hashlib.sha256(Path(record[key]["path"]).read_bytes()).hexdigest(), record[key]["sha256"])
            self.assertNotIn("Authorization", (Path(directory) / "round-01/provider-request.json").read_text())

    def test_call_budget_blocks_seventeenth_without_transport(self):
        with tempfile.TemporaryDirectory() as directory:
            state, _, transport = self.state(directory)
            for _ in range(16):
                self.perform(state)
            with self.assertRaises(bridge.ProtocolError):
                self.perform(state)
            self.assertEqual(len(transport.calls), 16)

    def test_whole_bridge_deadline_blocks_transport(self):
        with tempfile.TemporaryDirectory() as directory:
            state, clock, transport = self.state(directory)
            clock.now = 1200
            with self.assertRaises(bridge.ProtocolError):
                self.perform(state)
            self.assertEqual(transport.calls, [])

    def test_http_failure_retains_exact_body_and_blocks_future_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            state, _, transport = self.state(directory, status=429, headers=[("Retry-After", "60")], raw=b'{"error":"quota exact bytes"}')
            with self.assertRaises(bridge.ProtocolError):
                self.perform(state)
            with self.assertRaises(bridge.ProtocolError):
                self.perform(state)
            self.assertEqual(len(transport.calls), 1)
            self.assertEqual((Path(directory) / "round-01/provider-response.bin").read_bytes(), b'{"error":"quota exact bytes"}')

    def test_exhausted_header_allows_actual_result_then_stops(self):
        with tempfile.TemporaryDirectory() as directory:
            state, _, transport = self.state(directory, headers=[("x-ratelimit-remaining", "0")])
            self.assertEqual(self.perform(state)["content"][0]["text"], "Read complete.")
            with self.assertRaises(bridge.ProtocolError):
                self.perform(state)
            self.assertEqual(len(transport.calls), 1)

    def test_malformed_response_stops_without_synthesized_result(self):
        with tempfile.TemporaryDirectory() as directory:
            state, _, transport = self.state(directory, raw=b'{"id":"actual","error":"bad arguments"}')
            with self.assertRaises(bridge.ProtocolError):
                self.perform(state)
            self.assertEqual(len(transport.calls), 1)
            self.assertFalse((Path(directory) / "round-01/anthropic-response.json").exists())

    def test_unsupported_client_semantics_retains_exact_raw_before_stopping(self):
        with tempfile.TemporaryDirectory() as directory:
            state, _, transport = self.state(directory)
            raw = b'{ "model": "claude-test", "messages": [{"role":"user","content":"fixture"}], "output_config": {} }\n'
            try:
                bridge.anthropic_to_openai(bridge.decode(raw))
                self.fail("Unsupported semantic must be rejected")
            except bridge.ProtocolError as exc:
                state.reject_before_provider(raw, str(exc), True)
            record = json.loads((Path(directory) / "rejected-client-01/rejection.json").read_bytes())
            self.assertEqual((Path(directory) / "rejected-client-01/client-request.bin").read_bytes(), raw)
            self.assertEqual(record["clientRequest"]["sha256"], bridge.hashlib.sha256(raw).hexdigest())
            self.assertIn("output_config", record["error"])
            self.assertTrue(record["detectedAtUtc"])
            self.assertTrue(record["clientBodyComplete"])
            self.assertFalse(record["clientHeadersRetained"])
            self.assertEqual(record["upstreamCallsForThisRejectedRequest"], 0)
            self.assertEqual(record["totalUpstreamCallsObserved"], 0)
            self.assertFalse(record["providerRequestStartedForThisClientRequest"])
            self.assertEqual(transport.calls, [])
            self.assertEqual(state.stop_reason, "client_protocol_failure")
            with self.assertRaises(bridge.ProtocolError):
                self.perform(state)
            self.assertEqual(transport.calls, [])

    def test_client_rejection_preserves_prior_observed_call_count(self):
        with tempfile.TemporaryDirectory() as directory:
            state, _, transport = self.state(directory)
            self.perform(state)
            state.reject_before_provider(b'not-json', "Invalid UTF-8 JSON", True)
            record = json.loads((Path(directory) / "rejected-client-01/rejection.json").read_bytes())
            self.assertEqual(record["upstreamCallsForThisRejectedRequest"], 0)
            self.assertEqual(record["totalUpstreamCallsObserved"], 1)
            self.assertEqual(len(transport.calls), 1)


if __name__ == "__main__":
    unittest.main()
