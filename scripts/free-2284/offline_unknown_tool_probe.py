"""One offline Claude Code unknown-tool boundary probe; no provider transport.

Only run_probe starts the supplied, already-installed official CLI. Importing
this module and its pure checks performs no process or network operation.
Replayed model bytes are an explicitly labelled fixture from a prior failed
live run, never new inference or acceptance evidence. The CLI must create its
own error; this helper never fabricates a tool_result.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import importlib.util
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit
import uuid


SOURCE_SHA256 = "aeaba105df6491d982e580cc4daf6a1942db3b09e904ffbbe5fdc2b48d3741ab"
RAW_TOOL_NAME = "Glob<|channel|>commentary"
READ_ONLY_TOOLS = {"Read", "Glob", "Grep"}
MAX_REQUEST_BYTES = 1_048_576
PROBE_SECONDS = 40
OFFLINE_ERROR = {
    "type": "error",
    "error": {"type": "api_error", "message":
              "Offline unknown-tool probe complete. No provider was contacted; no retry or fallback is authorized."},
}


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encode(value):
    return (json.dumps(value, ensure_ascii=True, allow_nan=False, indent=2) + "\n").encode()


def write_new(path, data):
    with path.open("xb") as output:
        output.write(data)


def snapshot(fixture):
    """Include Git metadata too; this probe has no permission to change it."""
    if fixture.is_symlink() or not fixture.is_dir():
        raise ValueError("Probe fixture must be an ordinary directory")
    result = {}
    for candidate in sorted(fixture.rglob("*")):
        if candidate.is_symlink():
            raise ValueError("Probe fixture contains a symlink")
        if candidate.is_file():
            data = candidate.read_bytes()
            result[candidate.relative_to(fixture).as_posix()] = dict(size=len(data), sha256=digest(data))
    return result


def source_call(provider):
    calls = provider["choices"][0]["message"]["tool_calls"]
    if len(calls) != 1 or calls[0].get("type") != "function":
        raise ValueError("Recorded fixture must contain its one actual function call")
    call = calls[0]
    if call["function"].get("name") != RAW_TOOL_NAME or not isinstance(call.get("id"), str):
        raise ValueError("Recorded malformed tool identity changed")
    arguments = json.loads(call["function"]["arguments"])
    if not isinstance(arguments, dict):
        raise ValueError("Recorded tool arguments must be an object")
    return call["id"], arguments


def check_actual_error(request, converted, tool_id, arguments):
    """Check only captured actual CLI bytes and their protocol conversion."""
    calls, errors = [], []
    for message in request.get("messages", []):
        content = message.get("content", [])
        if not isinstance(content, list):
            continue
        for item in content:
            if not isinstance(item, dict):
                continue
            if message.get("role") == "assistant" and item.get("type") == "tool_use" and item.get("id") == tool_id:
                calls.append(item)
            if message.get("role") == "user" and item.get("type") == "tool_result" and item.get("tool_use_id") == tool_id:
                errors.append(item)
    if len(calls) != 1 or calls[0].get("name") != RAW_TOOL_NAME or calls[0].get("input") != arguments:
        raise ValueError("Actual CLI assistant history did not preserve the exact raw tool call")
    if len(errors) != 1 or errors[0].get("is_error") is not True:
        raise ValueError("Actual CLI did not produce exactly one matching is_error tool_result")
    error_content = errors[0].get("content")
    if not error_content:
        raise ValueError("Actual CLI error result is empty")
    # Extract the CLI's exact error text using the same independently reviewed
    # bridge content routine; do not replace it with a synthetic error message.
    converted_calls, converted_errors = [], []
    for message in converted.get("messages", []):
        if message.get("role") == "assistant":
            converted_calls += [call for call in message.get("tool_calls", []) if call.get("id") == tool_id]
        if message.get("role") == "tool" and message.get("tool_call_id") == tool_id:
            converted_errors.append(message)
    if len(converted_calls) != 1 or len(converted_errors) != 1:
        raise ValueError("OpenAI conversion lost or duplicated the real unknown-tool cycle")
    function = converted_calls[0].get("function", {})
    if function.get("name") != RAW_TOOL_NAME or json.loads(function.get("arguments", "null")) != arguments:
        raise ValueError("OpenAI conversion changed the unknown tool name or arguments")
    wrapped = json.loads(converted_errors[0].get("content", "null"))
    if not isinstance(wrapped, dict) or wrapped.get("is_error") is not True:
        raise ValueError("OpenAI conversion lost the actual CLI error marker")
    if isinstance(error_content, str):
        actual_text = error_content
    elif isinstance(error_content, list) and all(isinstance(x, dict) and x.get("type") == "text" and isinstance(x.get("text"), str) for x in error_content):
        actual_text = "\n".join(x["text"] for x in error_content)
    else:
        raise ValueError("Actual CLI error has an unsupported content shape")
    if wrapped.get("content") != actual_text:
        raise ValueError("OpenAI conversion changed the actual CLI error text")
    if RAW_TOOL_NAME not in actual_text:
        raise ValueError("Actual CLI error does not identify the unmodified unknown tool")
    return dict(exactRawToolNamePreserved=True, exactToolIdPreserved=True,
                actualCliErrorObserved=True, actualCliErrorTextSha256=digest(actual_text.encode()),
                unknownToolCycleRoundTripPreserved=True)


def hook_log_paths(settings):
    found = set()
    data = json.loads(settings.read_bytes())
    groups = data.get("hooks", {}).get("PreToolUse", [])
    for group in groups:
        for hook in group.get("hooks", []):
            if hook.get("type") != "command" or not isinstance(hook.get("command"), str):
                continue
            words = shlex.split(hook["command"])
            for index, word in enumerate(words[:-1]):
                if word == "--log":
                    log = Path(words[index + 1])
                    if not log.is_absolute():
                        raise ValueError("Probe hook log path must be absolute")
                    found.add(log)
    if not found:
        raise ValueError("Probe settings contain no independently inspectable guard log")
    return sorted(found)


def probe_environment(env, base_url):
    safe = {"PATH", "LANG", "LC_ALL", "HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "TMPDIR",
            "GIT_CONFIG_NOSYSTEM", "GIT_CONFIG_GLOBAL", "GIT_TERMINAL_PROMPT", "NPM_CONFIG_USERCONFIG",
            "CLAUDE_CONFIG_DIR"}
    clean = {key: value for key, value in env.items() if key in safe}
    if not clean.get("HOME") or not Path(clean["HOME"]).is_absolute():
        raise ValueError("Caller must supply a clean, isolated absolute HOME")
    clean.update(CI="1", NO_COLOR="1", ANTHROPIC_BASE_URL=base_url,
                 ANTHROPIC_AUTH_TOKEN="offline-unknown-tool-probe-only", ANTHROPIC_API_KEY="",
                 ANTHROPIC_MODEL="openai-fast", ANTHROPIC_SMALL_FAST_MODEL="openai-fast",
                 ANTHROPIC_DEFAULT_HAIKU_MODEL="openai-fast", ANTHROPIC_DEFAULT_SONNET_MODEL="openai-fast",
                 ANTHROPIC_DEFAULT_OPUS_MODEL="openai-fast", CLAUDE_CODE_SUBAGENT_MODEL="openai-fast",
                 DISABLE_AUTOUPDATER="1", DISABLE_TELEMETRY="1", DISABLE_ERROR_REPORTING="1",
                 CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1", CLAUDE_CODE_MAX_RETRIES="0",
                 CLAUDE_CODE_MAX_OUTPUT_TOKENS="4096", MAX_THINKING_TOKENS="0", API_TIMEOUT_MS="20000")
    return clean


def stop_owned_group(process):
    if process is None:
        return
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=3)
            return
        except subprocess.TimeoutExpired:
            pass
    if process.poll() is None:
        raise RuntimeError("Owned probe CLI process group did not stop")


def load_bridge():
    module_path = Path(__file__).with_name("anthropic_openai_bridge.py")
    spec = importlib.util.spec_from_file_location("offline_probe_bridge_" + uuid.uuid4().hex, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load the reviewed sibling protocol adapter")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, digest(module_path.read_bytes())


def run_probe(cli: Path, fixture: Path, env: dict, settings: Path, prompt: str,
              recorded_response_path: Path, evidence_dir: Path) -> dict:
    """Run once before live inference. A false result forbids proceeding live."""
    cli, fixture, settings = Path(cli), Path(fixture), Path(settings)
    recorded_response_path, evidence_dir = Path(recorded_response_path), Path(evidence_dir)
    if evidence_dir.absolute().is_relative_to(fixture.absolute()):
        raise ValueError("Probe evidence must live outside the immutable fixture")
    evidence_dir.mkdir(mode=0o700, exist_ok=False)
    result = dict(schemaVersion=1, startedAtUtc=now(), probePassed=False, providerCalls=0,
                  scope="Offline replay of recorded malformed tool call; actual CLI error only",
                  recordedProviderFixtureSha256=SOURCE_SHA256, modelInferencePerformed=False,
                  successfulAcceptanceVerified=False, receivedCashVerified=False,
                  cliExecuted=False, automaticRetriesAuthorized=False)
    process = server = thread = None
    before = None
    records = []
    handler_errors = []
    snapshots = {}
    bridge = None
    try:
        if not sys.platform.startswith("linux"):
            raise ValueError("This bounded probe requires the isolated Linux CI runner")
        if not cli.is_file() or not settings.is_file() or not isinstance(prompt, str) or not prompt:
            raise ValueError("Already-installed CLI, exact settings and prompt are required")
        raw_provider = recorded_response_path.read_bytes()
        write_new(evidence_dir / "recorded-provider-response.bin", raw_provider)
        if digest(raw_provider) != SOURCE_SHA256:
            raise ValueError("Recorded real provider response SHA256 does not match the immutable fixture")
        bridge, adapter_sha = load_bridge()
        provider = bridge.decode(raw_provider)
        tool_id, arguments = source_call(provider)
        translated = bridge.openai_to_anthropic(provider, READ_ONLY_TOOLS)
        blocks = translated.get("content", [])
        if len(blocks) != 1 or blocks[0].get("name") != RAW_TOOL_NAME or blocks[0].get("id") != tool_id or blocks[0].get("input") != arguments:
            raise ValueError("Response translation did not preserve the exact raw unknown tool")
        sse = bridge.anthropic_sse(translated)
        write_new(evidence_dir / "replayed-anthropic-response.json", encode(translated))
        write_new(evidence_dir / "replayed-response.sse", sse)
        result.update(adapterSha256=adapter_sha, rawToolName=RAW_TOOL_NAME, rawToolId=tool_id,
                      settingsSha256=digest(settings.read_bytes()), promptSha256=digest(prompt.encode()))
        write_new(evidence_dir / "probe-settings.json", settings.read_bytes())
        before = snapshot(fixture)
        write_new(evidence_dir / "fixture-before.json", encode(before))
        for log in hook_log_paths(settings):
            if log.is_symlink():
                raise ValueError("Hook log must not be a symlink")
            snapshots[log] = log.read_bytes() if log.exists() else b""

        class Server(HTTPServer):
            allow_reuse_address = False

            def get_request(self):
                connection, address = super().get_request()
                connection.settimeout(5)
                return connection, address

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"

            def log_message(self, *_):
                pass

            def do_POST(self):
                number = len(records) + 1
                row = dict(number=number, receivedAtUtc=now(), path=self.path)
                records.append(row)
                try:
                    if self.client_address[0] != "127.0.0.1" or urlsplit(self.path).path != "/v1/messages":
                        raise ValueError("Only loopback /v1/messages is permitted")
                    size = int(self.headers.get("Content-Length", "-1"))
                    if not 0 < size <= MAX_REQUEST_BYTES:
                        raise ValueError("Invalid or excessive request body")
                    raw = self.rfile.read(size)
                    if len(raw) != size:
                        raise ValueError("Incomplete request body")
                    name = f"request-{number:02d}.json"
                    write_new(evidence_dir / name, raw)
                    row.update(bodyFile=name, bodyBytes=len(raw), bodySha256=digest(raw))
                    observed = bridge.decode(raw)
                    if number == 1:
                        names = [tool.get("name") for tool in observed.get("tools", [])]
                        if set(names) != READ_ONLY_TOOLS or len(names) != 3 or observed.get("stream") is not True:
                            raise ValueError("Actual CLI request does not expose exactly the three readonly streaming tools")
                        # Validate the first actual request using the normal
                        # adapter, without sending it anywhere.
                        bridge.anthropic_to_openai(observed)
                        body, status, content_type = sse, 200, "text/event-stream"
                    else:
                        body, status, content_type = encode(OFFLINE_ERROR), 501, "application/json"
                        write_new(evidence_dir / f"response-{number:02d}.json", body)
                    row.update(responseStatus=status, responseBytes=len(body), responseSha256=digest(body))
                    self.send_response(status)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Connection", "close")
                    self.end_headers()
                    self.wfile.write(body)
                    self.wfile.flush()
                    row["completedAtUtc"] = now()
                except Exception as error:
                    row["error"] = type(error).__name__ + ": " + str(error)
                    handler_errors.append(row["error"])
                    try:
                        self.send_error(400, "Offline probe rejected input")
                    except OSError:
                        pass

        server = Server(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
        thread.start()
        clean = probe_environment(env, "http://127.0.0.1:" + str(server.server_port))
        command = [str(cli), "--restricted", "--permission-mode", "plan", "--tools", "Read,Glob,Grep",
                   "--allowedTools", "Read,Glob,Grep", "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
                   "--settings", str(settings), "--setting-sources", "", "--session-id", str(uuid.uuid4()),
                   "--max-turns", "2", "--effort", "low", "--output-format", "stream-json", "--verbose", "-p", prompt]
        write_new(evidence_dir / "probe-intent.json", encode(dict(command=command, cwd=str(fixture),
                  startedAtUtc=now(), timeoutSeconds=PROBE_SECONDS, loopbackHost="127.0.0.1",
                  loopbackPort=server.server_port, providerCalls=0, sourceFixtureSha256=SOURCE_SHA256)))
        with (evidence_dir / "cli-stdout.jsonl").open("xb") as stdout, (evidence_dir / "cli-stderr.txt").open("xb") as stderr:
            process = subprocess.Popen(command, cwd=fixture, env=clean, stdin=subprocess.DEVNULL,
                                       stdout=stdout, stderr=stderr, start_new_session=True)
            result.update(cliExecuted=True, cliPid=process.pid)
            try:
                result["cliExitCode"] = process.wait(timeout=PROBE_SECONDS)
            except subprocess.TimeoutExpired:
                result["cliTimedOut"] = True
            finally:
                stop_owned_group(process)
        if result.get("cliTimedOut") or handler_errors or len(records) != 2:
            raise ValueError("Probe timed out, request handling failed, or actual CLI did not make exactly two requests")
        if records[0].get("responseStatus") != 200 or records[1].get("responseStatus") != 501:
            raise ValueError("Probe response sequence differs from replay then explicit offline stop")
        actual = bridge.decode((evidence_dir / "request-02.json").read_bytes())
        converted = bridge.anthropic_to_openai(actual)
        write_new(evidence_dir / "actual-second-request-openai.json", encode(converted))
        result.update(check_actual_error(actual, converted, tool_id, arguments))
    except Exception as error:
        result["error"] = type(error).__name__ + ": " + str(error)
    finally:
        try:
            stop_owned_group(process)
            result["ownedProcessStopped"] = process is None or process.poll() is not None
        except Exception as error:
            result["cleanupError"] = type(error).__name__ + ": " + str(error)
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None:
            thread.join(timeout=6)
            result["loopbackServerStopped"] = not thread.is_alive()
        try:
            if before is not None:
                after = snapshot(fixture)
                write_new(evidence_dir / "fixture-after.json", encode(after))
                result["fixtureUnchanged"] = before == after
            hook_entries = []
            for index, (log, prior) in enumerate(snapshots.items(), 1):
                current = log.read_bytes() if log.exists() else b""
                if not current.startswith(prior):
                    raise ValueError("Probe guard log history changed instead of appending")
                added = current[len(prior):]
                write_new(evidence_dir / f"observed-hook-log-{index:02d}.jsonl", added)
                hook_entries += [json.loads(line) for line in added.splitlines() if line.strip()]
            result["unknownToolHookEntries"] = sum(entry.get("tool") == RAW_TOOL_NAME for entry in hook_entries)
            result["allowedToolHookEntries"] = sum(entry.get("allowed") is True for entry in hook_entries)
            result["noMatchingUnknownToolExecution"] = bool(snapshots) and not hook_entries
        except Exception as error:
            result["verificationError"] = type(error).__name__ + ": " + str(error)
        result.update(completedAtUtc=now(), requests=records, handlerErrors=handler_errors,
                      providerCalls=0, noAutomaticSemanticPass=True)
        result["probePassed"] = (not any(key in result for key in ("error", "cleanupError", "verificationError"))
            and result.get("actualCliErrorObserved") is True
            and result.get("unknownToolCycleRoundTripPreserved") is True
            and result.get("fixtureUnchanged") is True
            and result.get("noMatchingUnknownToolExecution") is True
            and result.get("ownedProcessStopped") is True and result.get("loopbackServerStopped") is True)
        result["files"] = {file.name: dict(size=file.stat().st_size, sha256=digest(file.read_bytes()))
                           for file in sorted(evidence_dir.iterdir()) if file.is_file()}
        write_new(evidence_dir / "probe-result.json", encode(result))
    return result
