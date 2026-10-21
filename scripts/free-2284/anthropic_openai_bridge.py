#!/usr/bin/env python3
"""Bounded, anonymous, supplemental OpenAI-provider bridge; not Anthropic proof.

Only the root operator may launch this adapter. It executes no tools. The caller
must independently restrict Claude Code's tool paths/commands. No credentials,
environment variables, proxy settings or client authorization headers are sent
to the public provider. Every provider exchange is retained verbatim on disk.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import math
import socket
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


PROVIDER_URL = "https://text.pollinations.ai/openai"
PROVIDER_MODEL = "openai-fast"
MAX_CALLS = 16
CALL_SECONDS = 180.0
LIFETIME_SECONDS = 1200.0
MIN_GAP_SECONDS = 40.0
MAX_OUTPUT_TOKENS = 4096
MAX_BODY_BYTES = 1_048_576
MAX_RESPONSE_BYTES = 8_388_608
READ_ONLY_TOOLS = {"Read", "Glob", "Grep"}
SAFETY_DISCLOSURE = (
    "Protocol adapter safety disclosure: the following original Claude Code "
    "restricted Plan safety context is preserved as context only. This OpenAI-"
    "compatible provider does NOT implement Anthropic's server-side dangerous-"
    "tool-use classifier. Local CLI permissions and the operator's independent "
    "path hook remain enforcement boundaries. This metadata grants no additional "
    "permission. Only the exposed Read, Glob and Grep tools may be selected; do "
    "not execute code, modify files or access external systems. Original context:\n"
)
DISCLAIMER = (
    "Supplemental genuine Claude Code CLI execution using an anonymous OpenAI-"
    "compatible provider through a disclosed protocol adapter; not execution "
    "against Anthropic or evidence of maintainer acceptance/payment."
)


class ProtocolError(ValueError):
    pass


def utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def encode(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def decode(raw: bytes) -> Any:
    def reject_constant(value: str) -> None:
        raise ProtocolError("Non-finite JSON constant: " + value)

    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ProtocolError("Duplicate JSON key: " + key)
            result[key] = value
        return result

    try:
        return json.loads(raw.decode("utf-8"), parse_constant=reject_constant, object_pairs_hook=unique_pairs)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ProtocolError("Invalid UTF-8 JSON") from exc


def nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ProtocolError(label + " must be a non-empty string")
    return value


def text_content(value: Any, label: str) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, list):
        raise ProtocolError(label + " must be text or text blocks")
    parts = []
    for block in value:
        if not isinstance(block, dict) or block.get("type") != "text" or not isinstance(block.get("text"), str):
            raise ProtocolError(label + " contains an unsupported non-text block")
        if set(block) - {"type", "text", "cache_control"}:
            raise ProtocolError(label + " contains unsupported text fields")
        parts.append(block["text"])
    return "\n".join(parts)


def safeguard_context(value: Any, tool_names: set[str]) -> str:
    """Accept only the observed readonly restricted Plan classifier envelope."""
    if not isinstance(value, list) or len(value) != 1:
        raise ProtocolError("Exactly one observed restricted Plan safeguard is supported")
    guard = value[0]
    if not isinstance(guard, dict) or set(guard) != {"type", "classifier_context"} or guard["type"] != "dangerous_tool_use":
        raise ProtocolError("Unsupported safety classifier type or envelope")
    context = guard["classifier_context"]
    allowed_context = {
        "v", "permission_mode", "platform", "live_cwd", "home_dir", "rule_roots",
        "trusted_directories", "rules", "auto_mode", "artifact_consent_holdback",
        "case_insensitive_paths", "restricted", "is_remote_mode", "classify_all_shell",
        "user_identity", "git_state",
    }
    if not isinstance(context, dict) or set(context) - allowed_context:
        raise ProtocolError("Unsupported safety classifier context fields")
    if type(context.get("v")) is not int or context["v"] != 1 or context.get("permission_mode") != "plan" or context.get("restricted") is not True:
        raise ProtocolError("Only version-1 restricted Plan safety context is supported")
    if not isinstance(context.get("platform"), str) or context["platform"] not in {"windows", "linux"} or context.get("is_remote_mode") is not False:
        raise ProtocolError("Unsupported safety platform or remote mode")
    if not tool_names or not tool_names.issubset(READ_ONLY_TOOLS):
        raise ProtocolError("Safety context requires readonly Read/Glob/Grep tools only")
    rules = context.get("rules")
    if not isinstance(rules, dict) or set(rules) != {"allow", "deny", "ask"}:
        raise ProtocolError("Unsupported safety rules envelope")
    for kind in ("allow", "deny", "ask"):
        if not isinstance(rules[kind], list):
            raise ProtocolError("Safety rule lists are required")
        for rule in rules[kind]:
            if not isinstance(rule, dict) or set(rule) != {"rule", "source"} or not isinstance(rule["source"], str) or not isinstance(rule["rule"], str):
                raise ProtocolError("Unsupported safety rule entry")
    allowed_names = {rule["rule"] for rule in rules["allow"]}
    if allowed_names != tool_names or rules["ask"]:
        raise ProtocolError("Safety allows must match exposed readonly tools with no extra asks")
    trusted = context.get("trusted_directories")
    if not isinstance(trusted, dict) or trusted.get("additional") != [] or trusted.get("network") != []:
        raise ProtocolError("Additional or network safety directories are unsupported")
    automatic = context.get("auto_mode")
    if automatic != {"allow": [], "soft_deny": [], "hard_deny": [], "environment": []}:
        raise ProtocolError("Automatic-mode safety rules are unsupported")
    return SAFETY_DISCLOSURE + encode(value).decode("utf-8")


def message_route(path: str) -> str | None:
    if path in {"/v1/messages", "/v1/messages?", "/v1/messages?beta=true"}:
        return "messages"
    if path in {"/v1/messages/count_tokens", "/v1/messages/count_tokens?", "/v1/messages/count_tokens?beta=true"}:
        return "count_tokens"
    return None


def resolve_stop_file(directory: Path, requested: Path | None) -> Path | None:
    if requested is None:
        return None
    path = (requested if requested.is_absolute() else directory / requested).resolve()
    if path == directory or not path.is_relative_to(directory):
        raise ProtocolError("stop-file must be a child path under the evidence directory")
    return path


def anthropic_to_openai(request: Any) -> dict[str, Any]:
    """Translate text/custom-tool conversation only; reject unsupported semantics."""
    if not isinstance(request, dict):
        raise ProtocolError("Request must be an object")
    allowed = {
        "model", "system", "messages", "max_tokens", "stream", "tools", "tool_choice",
        "temperature", "top_p", "stop_sequences", "metadata", "thinking", "safeguards", "output_config",
    }
    unknown = set(request) - allowed
    if unknown:
        raise ProtocolError("Unsupported request fields: " + ", ".join(sorted(unknown)))
    nonempty(request.get("model"), "model")
    if "stream" in request and not isinstance(request["stream"], bool):
        raise ProtocolError("stream must be boolean")
    thinking = request.get("thinking")
    if thinking is not None and thinking != {"type": "disabled"}:
        raise ProtocolError("Extended/adaptive thinking is unsupported")
    if "metadata" in request and not isinstance(request["metadata"], dict):
        raise ProtocolError("metadata must be an object")
    requested_tokens = request.get("max_tokens", 1024)
    if isinstance(requested_tokens, bool) or not isinstance(requested_tokens, int) or requested_tokens < 1:
        raise ProtocolError("max_tokens must be a positive integer")
    result: dict[str, Any] = {
        "model": PROVIDER_MODEL, "stream": False, "reasoning_effort": "low",
        "max_tokens": min(requested_tokens, MAX_OUTPUT_TOKENS), "messages": [],
    }
    if "output_config" in request:
        output_config = request["output_config"]
        if not isinstance(output_config, dict) or set(output_config) != {"effort"} or not isinstance(output_config["effort"], str) or output_config["effort"] not in {"low", "high"}:
            raise ProtocolError("Only observed output_config.effort low/high is supported")
        result["reasoning_effort"] = output_config["effort"]
    for field in ("temperature", "top_p"):
        if field in request:
            value = request[field]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ProtocolError(field + " must be finite numeric")
            if not 0 <= value <= (2 if field == "temperature" else 1):
                raise ProtocolError(field + " is out of range")
            result[field] = value
    if "stop_sequences" in request:
        stops = request["stop_sequences"]
        if not isinstance(stops, list) or len(stops) > 4 or not all(isinstance(s, str) and s for s in stops):
            raise ProtocolError("stop_sequences must contain at most four non-empty strings")
        result["stop"] = stops

    tool_names: set[str] = set()
    tools = request.get("tools", [])
    if not isinstance(tools, list):
        raise ProtocolError("tools must be an array")
    converted_tools = []
    for tool in tools:
        if not isinstance(tool, dict) or set(tool) - {"name", "description", "input_schema", "cache_control", "type"}:
            raise ProtocolError("Unsupported custom tool fields")
        if tool.get("type", "custom") != "custom":
            raise ProtocolError("Only custom tools are supported")
        name = nonempty(tool.get("name"), "tool name")
        if name not in READ_ONLY_TOOLS:
            raise ProtocolError("Only readonly Read, Glob and Grep tools are supported")
        if name in tool_names:
            raise ProtocolError("Duplicate tool name")
        schema = tool.get("input_schema")
        if not isinstance(schema, dict) or schema.get("type") != "object":
            raise ProtocolError("Tool input_schema must be an object JSON schema")
        description = tool.get("description", "")
        if not isinstance(description, str):
            raise ProtocolError("Tool description must be text")
        tool_names.add(name)
        converted_tools.append({"type": "function", "function": {"name": name, "description": description, "parameters": schema}})
    if converted_tools:
        result["tools"] = converted_tools
    choice = request.get("tool_choice")
    if choice is not None:
        if not isinstance(choice, dict) or set(choice) - {"type", "name", "disable_parallel_tool_use"}:
            raise ProtocolError("Unsupported tool_choice")
        kind = choice.get("type")
        if kind in ("auto", "none", "any"):
            if "name" in choice:
                raise ProtocolError("Unexpected tool_choice name")
            result["tool_choice"] = {"auto": "auto", "none": "none", "any": "required"}[kind]
        elif kind == "tool" and choice.get("name") in tool_names:
            result["tool_choice"] = {"type": "function", "function": {"name": choice["name"]}}
        else:
            raise ProtocolError("Unknown or unavailable tool_choice")
        if not tools and kind != "none":
            raise ProtocolError("tool_choice requires tools")
        if "disable_parallel_tool_use" in choice:
            if not isinstance(choice["disable_parallel_tool_use"], bool):
                raise ProtocolError("disable_parallel_tool_use must be boolean")
            result["parallel_tool_calls"] = not choice["disable_parallel_tool_use"]

    messages = result["messages"]
    if "system" in request:
        messages.append({"role": "system", "content": text_content(request["system"], "system")})
    if "safeguards" in request:
        messages.append({"role": "system", "content": safeguard_context(request["safeguards"], tool_names)})
    history = request.get("messages")
    if not isinstance(history, list) or not history:
        raise ProtocolError("messages must be a non-empty array")
    pending: set[str] = set()
    seen_tool_ids: set[str] = set()
    for message in history:
        if not isinstance(message, dict) or set(message) != {"role", "content"}:
            raise ProtocolError("Each message requires only role and content")
        role = message["role"]
        if role not in ("user", "assistant", "system"):
            raise ProtocolError("Unsupported message role")
        content = message["content"]
        if isinstance(content, str):
            if pending:
                raise ProtocolError("Unresolved tool call before text message")
            messages.append({"role": role, "content": content})
            continue
        if not isinstance(content, list) or not content:
            raise ProtocolError("Message content must be text or non-empty blocks")
        if role == "system":
            if pending:
                raise ProtocolError("Unresolved tool call before system message")
            messages.append({"role": "system", "content": text_content(content, "system message")})
            continue
        if role == "assistant":
            if pending:
                raise ProtocolError("Unresolved tool call before assistant message")
            texts = []
            calls = []
            for block in content:
                if not isinstance(block, dict):
                    raise ProtocolError("Invalid assistant block")
                if block.get("type") == "text":
                    if calls:
                        raise ProtocolError("Text after tool_use cannot be represented faithfully")
                    texts.append(text_content([block], "assistant"))
                elif block.get("type") == "tool_use":
                    if set(block) - {"type", "id", "name", "input", "cache_control"}:
                        raise ProtocolError("Unsupported tool_use fields")
                    ident = nonempty(block.get("id"), "tool_use id")
                    name = nonempty(block.get("name"), "tool_use name")
                    if ident in seen_tool_ids or name not in tool_names or not isinstance(block.get("input"), dict):
                        raise ProtocolError("Duplicate, unknown or malformed tool_use")
                    seen_tool_ids.add(ident)
                    pending.add(ident)
                    calls.append({"id": ident, "type": "function", "function": {"name": name, "arguments": encode(block["input"]).decode("utf-8")}})
                else:
                    raise ProtocolError("Unsupported assistant block type")
            converted = {"role": "assistant", "content": "\n".join(texts) if texts else None}
            if calls:
                converted["tool_calls"] = calls
            messages.append(converted)
        else:
            texts = []
            for block in content:
                if not isinstance(block, dict):
                    raise ProtocolError("Invalid user block")
                if block.get("type") == "tool_result":
                    if texts or set(block) - {"type", "tool_use_id", "content", "is_error", "cache_control"}:
                        raise ProtocolError("Unsupported or out-of-order tool_result")
                    ident = nonempty(block.get("tool_use_id"), "tool_result id")
                    if ident not in pending:
                        raise ProtocolError("Unknown or duplicate tool_result id")
                    tool_text = text_content(block.get("content", ""), "tool_result")
                    is_error = block.get("is_error", False)
                    if not isinstance(is_error, bool):
                        raise ProtocolError("tool_result is_error must be boolean")
                    if is_error:
                        tool_text = encode({"is_error": True, "content": tool_text}).decode("utf-8")
                    messages.append({"role": "tool", "tool_call_id": ident, "content": tool_text})
                    pending.remove(ident)
                elif block.get("type") == "text":
                    if pending:
                        raise ProtocolError("All pending tools require results before user text")
                    texts.append(text_content([block], "user"))
                else:
                    raise ProtocolError("Unsupported user block type")
            if texts:
                messages.append({"role": "user", "content": "\n".join(texts)})
    if pending:
        raise ProtocolError("Unresolved tool calls at end of request")
    # Also rejects non-JSON schema data, NaN, or non-serializable tool inputs.
    encode(result)
    return result


def openai_to_anthropic(response: Any, declared_tools: set[str]) -> dict[str, Any]:
    if not isinstance(response, dict) or response.get("error"):
        raise ProtocolError("Provider returned an error object or non-object")
    ident = nonempty(response.get("id"), "provider response id")
    model = nonempty(response.get("model"), "provider response model")
    choices = response.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        raise ProtocolError("Exactly one provider choice is required")
    choice = choices[0]
    message = choice.get("message")
    if not isinstance(message, dict) or message.get("role") != "assistant":
        raise ProtocolError("Provider choice must be an assistant message")
    if message.get("refusal") or message.get("function_call"):
        raise ProtocolError("Unsupported provider refusal or legacy function call")
    # Provider reasoning remains in the verbatim raw exchange. It is deliberately
    # not injected into the visible answer, tool inputs, or a synthetic plan.
    text = message.get("content")
    if text is not None and not isinstance(text, str):
        raise ProtocolError("Provider content must be text or null")
    content = [{"type": "text", "text": text}] if text else []
    tool_calls = message.get("tool_calls", [])
    if tool_calls is None:
        tool_calls = []
    if not isinstance(tool_calls, list):
        raise ProtocolError("Provider tool_calls must be an array")
    seen = set()
    for call in tool_calls:
        if not isinstance(call, dict) or call.get("type") != "function":
            raise ProtocolError("Provider returned a non-function tool call")
        call_id = nonempty(call.get("id"), "provider tool call id")
        function = call.get("function")
        if call_id in seen or not isinstance(function, dict) or function.get("name") not in declared_tools:
            raise ProtocolError("Provider returned duplicate or undeclared tool call")
        seen.add(call_id)
        arguments = function.get("arguments")
        if not isinstance(arguments, str):
            raise ProtocolError("Provider tool arguments must be raw JSON text")
        parsed = decode(arguments.encode("utf-8"))
        if not isinstance(parsed, dict):
            raise ProtocolError("Provider tool arguments must decode to an object")
        content.append({"type": "tool_use", "id": call_id, "name": function["name"], "input": parsed})
    finish = choice.get("finish_reason")
    if tool_calls:
        if finish != "tool_calls":
            raise ProtocolError("Provider tool calls require tool_calls finish_reason")
        stop_reason = "tool_use"
    elif finish in ("stop", "length"):
        stop_reason = {"stop": "end_turn", "length": "max_tokens"}[finish]
    else:
        raise ProtocolError("Unsupported provider finish_reason")
    usage = response.get("usage")
    if not isinstance(usage, dict):
        raise ProtocolError("Provider usage is required; token counts must not be fabricated")
    translated_usage = {}
    for source, dest in (("prompt_tokens", "input_tokens"), ("completion_tokens", "output_tokens")):
        value = usage.get(source)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ProtocolError("Provider token usage must be a non-negative integer")
        translated_usage[dest] = value
    return {"id": "msg_bridge_" + ident, "type": "message", "role": "assistant", "model": model,
            "content": content, "stop_reason": stop_reason, "stop_sequence": None, "usage": translated_usage}


def anthropic_sse(message: dict[str, Any]) -> bytes:
    """Buffer provider's actual result, then emit Anthropic-compatible SSE events."""
    events = []
    start = {**message, "content": [], "stop_reason": None, "stop_sequence": None,
             "usage": {"input_tokens": message["usage"]["input_tokens"], "output_tokens": 0}}
    events.append(("message_start", {"type": "message_start", "message": start}))
    for index, block in enumerate(message["content"]):
        if block["type"] == "text":
            opening = {"type": "text", "text": ""}
            delta = {"type": "text_delta", "text": block["text"]}
        else:
            opening = {"type": "tool_use", "id": block["id"], "name": block["name"], "input": {}}
            delta = {"type": "input_json_delta", "partial_json": encode(block["input"]).decode("utf-8")}
        events.append(("content_block_start", {"type": "content_block_start", "index": index, "content_block": opening}))
        events.append(("content_block_delta", {"type": "content_block_delta", "index": index, "delta": delta}))
        events.append(("content_block_stop", {"type": "content_block_stop", "index": index}))
    events.append(("message_delta", {"type": "message_delta", "delta": {"stop_reason": message["stop_reason"], "stop_sequence": None}, "usage": {"output_tokens": message["usage"]["output_tokens"]}}))
    events.append(("message_stop", {"type": "message_stop"}))
    return b"".join(b"event: " + name.encode("ascii") + b"\ndata: " + encode(value) + b"\n\n" for name, value in events)


def quota_header_failure(headers: list[tuple[str, str]]) -> str | None:
    for name, value in headers:
        key = name.lower()
        if key in {"retry-after", "www-authenticate"}:
            return key
        if key in {"x-ratelimit-remaining", "ratelimit-remaining", "x-rate-limit-remaining",
                   "x-quota-remaining", "quota-remaining", "x-ratelimit-remaining-requests", "x-ratelimit-remaining-tokens"}:
            try:
                if float(value) <= 0:
                    return key + " exhausted"
            except ValueError:
                return key + " malformed"
    return None


class ProviderTransport:
    """Fixed HTTPS destination, no proxy/redirect/auth. Watchdog aborts on timeout.

    The daemon worker cannot initiate a second request. On a timeout the bridge
    stops permanently; retained timeout evidence contains observed bytes only.
    Remote cancellation cannot prove that a provider stopped server-side work.
    """

    def exchange(self, body: bytes, timeout: float) -> dict[str, Any]:
        endpoint = urlsplit(PROVIDER_URL)
        assert endpoint.scheme == "https" and endpoint.hostname == "text.pollinations.ai" and endpoint.path == "/openai"
        state: dict[str, Any] = {"status": None, "reason": None, "headers": [], "body": b"", "error": None, "timed_out": False}
        done = threading.Event()
        cancelled = threading.Event()
        connection = http.client.HTTPSConnection(endpoint.hostname, 443, timeout=timeout)
        deadline = time.monotonic() + timeout

        def worker() -> None:
            try:
                connection.connect()
                if cancelled.is_set():
                    return
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Provider deadline expired before request")
                connection.sock.settimeout(remaining)
                connection.request("POST", endpoint.path, body=body, headers={"Content-Type": "application/json", "Accept": "application/json"})
                response = connection.getresponse()
                state.update(status=response.status, reason=response.reason, headers=response.getheaders())
                chunks = []
                size = 0
                while not cancelled.is_set():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("Provider response deadline expired")
                    if connection.sock is not None:
                        connection.sock.settimeout(remaining)
                    chunk = response.read1(65_536)
                    if not chunk:
                        break
                    size += len(chunk)
                    chunks.append(chunk)
                    state["body"] = b"".join(chunks)
                    if size > MAX_RESPONSE_BYTES:
                        raise ProtocolError("Provider response exceeds evidence size bound")
                state["complete"] = not cancelled.is_set()
            except Exception as exc:
                state["error"] = type(exc).__name__ + ": " + str(exc)
                state["complete"] = False
            finally:
                connection.close()
                done.set()

        thread = threading.Thread(target=worker, name="single-provider-call", daemon=True)
        thread.start()
        if not done.wait(timeout):
            cancelled.set()
            state["timed_out"] = True
            state["complete"] = False
            state["error"] = "Provider total call exceeded the bounded timeout; no retries or further calls"
            if connection.sock is not None:
                try:
                    connection.sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            connection.close()
        return dict(state)


class BridgeState:
    def __init__(self, directory: Path, sources: Any, transport: Any = None, clock: Any = time.monotonic, sleeper: Any = time.sleep):
        self.directory = directory
        self.clock = clock
        self.sleeper = sleeper
        self.transport = transport or ProviderTransport()
        self.started = clock()
        self.deadline = self.started + LIFETIME_SECONDS
        self.last_completion: float | None = None
        self.calls = 0
        self.stop_reason: str | None = None
        self.metadata = {
            "schemaVersion": 1, "createdAtUtc": utc(), "disclosure": DISCLAIMER,
            "providerUrl": PROVIDER_URL, "providerModel": PROVIDER_MODEL, "sourceIds": sources,
            "adapterPath": str(Path(__file__).resolve()), "adapterSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "limits": {"maxModelCalls": MAX_CALLS, "callTimeoutSeconds": CALL_SECONDS, "wholeBridgeSeconds": LIFETIME_SECONDS,
                       "maxOutputTokens": MAX_OUTPUT_TOKENS, "minimumGapSeconds": MIN_GAP_SECONDS},
            "providerAuth": "anonymous; no environment or client credentials copied", "calls": 0, "stopped": False,
        }
        self.save_metadata()

    def save_metadata(self) -> None:
        self.metadata.update(calls=self.calls, stopped=bool(self.stop_reason), stopReason=self.stop_reason, updatedAtUtc=utc())
        self.write("session.json", encode(self.metadata))

    def write(self, relative: str, data: bytes) -> dict[str, Any]:
        path = self.directory / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return {"path": str(path.resolve()), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}

    def stop(self, reason: str) -> None:
        if self.stop_reason is None:
            self.stop_reason = reason
        self.save_metadata()

    def reject_before_provider(self, raw: bytes | None, error: str, body_complete: bool) -> None:
        """Retain observed client bytes before a pre-provider rejection stops us.

        Called only by request preflight, before perform(); zero calls for this
        rejected request is an observed control-flow fact, not a model result.
        Previous successful calls remain counted separately and are not erased.
        """
        index = self.metadata.get("rejectedClientRequests", 0) + 1
        prefix = "rejected-client-" + str(index).zfill(2) + "/"
        record = {
            "schemaVersion": 1, "detectedAtUtc": utc(), "error": error,
            "rawClientBytesAvailable": raw is not None,
            "clientBodyComplete": body_complete,
            "clientHeadersRetained": False,
            "upstreamCallsForThisRejectedRequest": 0,
            "totalUpstreamCallsObserved": self.calls,
            "providerRequestStartedForThisClientRequest": False,
        }
        if raw is not None:
            record["clientRequest"] = self.write(prefix + "client-request.bin", raw)
        self.write(prefix + "rejection.json", encode(record))
        self.metadata["rejectedClientRequests"] = index
        self.stop("client_protocol_failure")

    def perform(self, client_raw: bytes, request: Any, converted: dict[str, Any]) -> dict[str, Any]:
        if self.stop_reason:
            raise ProtocolError("Bridge stopped: " + self.stop_reason)
        if self.calls >= MAX_CALLS:
            self.stop("model_call_budget_exhausted")
            raise ProtocolError("Model call budget exhausted")
        if self.last_completion is not None:
            wait = max(0.0, self.last_completion + MIN_GAP_SECONDS - self.clock())
            if self.clock() + wait >= self.deadline:
                self.stop("whole_bridge_deadline")
                raise ProtocolError("Bridge deadline expired before paced call")
            if wait:
                self.sleeper(wait)
        remaining = self.deadline - self.clock()
        if remaining <= 0:
            self.stop("whole_bridge_deadline")
            raise ProtocolError("Bridge deadline expired")
        self.calls += 1
        number = self.calls
        prefix = "round-" + str(number).zfill(2) + "/"
        provider_raw = encode(converted)
        record = {"round": number, "startedAtUtc": utc(), "startedMonotonic": self.clock(),
                  "gapAfterPriorCompletionSeconds": None if self.last_completion is None else self.clock() - self.last_completion,
                  "clientRequestedModel": request["model"], "clientStreaming": request.get("stream", False),
                  "clientRequest": self.write(prefix + "client-request.json", client_raw),
                  "providerRequest": self.write(prefix + "provider-request.json", provider_raw)}
        self.write(prefix + "exchange.json", encode(record))
        self.save_metadata()
        try:
            exchange = self.transport.exchange(provider_raw, min(CALL_SECONDS, remaining))
            record.update(providerStatus=exchange.get("status"), providerReason=exchange.get("reason"),
                          providerHeaders=exchange.get("headers", []), providerComplete=exchange.get("complete", False),
                          providerError=exchange.get("error"), providerTimedOut=exchange.get("timed_out", False))
            record["providerResponse"] = self.write(prefix + "provider-response.bin", exchange.get("body", b""))
            record["providerResponseHeaders"] = self.write(prefix + "provider-response-headers.json", encode(exchange.get("headers", [])))
            if exchange.get("error") or not exchange.get("complete"):
                raise ProtocolError("Provider transport failed; exact error retained in exchange.json")
            status = exchange.get("status")
            if not isinstance(status, int) or not 200 <= status < 300:
                raise ProtocolError("Provider HTTP failure " + str(status) + "; no retries")
            poison = quota_header_failure(exchange.get("headers", []))
            if poison:
                self.stop("provider_header_guard: " + poison)
            actual = decode(exchange["body"])
            declared = {tool["function"]["name"] for tool in converted.get("tools", [])}
            message = openai_to_anthropic(actual, declared)
            record["providerReasoningPolicy"] = "preserved in provider-response.bin; never forwarded or injected into a plan"
            if "safeguards" in request:
                record["safeguardsPolicy"] = "original restricted Plan context preserved as disclosed system metadata; Anthropic server-side classifier NOT implemented"
            record["anthropicResponse"] = self.write(prefix + "anthropic-response.json", encode(message))
            record["translationVerified"] = True
            return message
        except Exception as exc:
            record["adapterError"] = type(exc).__name__ + ": " + str(exc)
            self.stop("provider_or_protocol_failure")
            raise
        finally:
            self.last_completion = self.clock()
            record.update(completedAtUtc=utc(), completedMonotonic=self.last_completion)
            self.write(prefix + "exchange.json", encode(record))
            self.save_metadata()


class AcceptedSocketGuard:
    """Absolute whole-session and phase deadlines, including slow header input.

    Socket timeouts alone reset on individual reads; the timers also interrupt
    clients that trickle bytes forever. They only shut down this accepted socket.
    The injectable clock/timer support local tests without starting threads.
    """

    def __init__(self, connection: Any, deadline: float, clock: Any = time.monotonic,
                 timer_factory: Any = threading.Timer):
        self.connection = connection
        self.deadline = deadline
        self.clock = clock
        self.timer_factory = timer_factory
        self.whole_timer = None
        self.phase_timer = None
        remaining = self.deadline - self.clock()
        if remaining <= 0:
            self.abort()
            raise TimeoutError("Bridge deadline expired before accepted request")
        self.whole_timer = self.arm(remaining)
        self.start_phase()

    def arm(self, seconds: float) -> Any:
        timer = self.timer_factory(seconds, self.abort)
        timer.daemon = True
        timer.start()
        return timer

    def abort(self) -> None:
        try:
            self.connection.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    def finish_phase(self) -> None:
        if self.phase_timer is not None:
            self.phase_timer.cancel()
            self.phase_timer = None

    def start_phase(self) -> None:
        self.finish_phase()
        remaining = self.deadline - self.clock()
        if remaining <= 0:
            self.abort()
            raise TimeoutError("Bridge deadline expired before client input")
        timeout = min(10.0, remaining)
        self.connection.settimeout(timeout)
        self.phase_timer = self.arm(timeout)

    def close(self) -> None:
        self.finish_phase()
        if self.whole_timer is not None:
            self.whole_timer.cancel()
            self.whole_timer = None


class BoundedHTTPServer(HTTPServer):
    def __init__(self, address: Any, handler: Any, bridge_state: BridgeState):
        self.bridge_state = bridge_state
        self.accepted_guards: dict[int, AcceptedSocketGuard] = {}
        super().__init__(address, handler)

    def get_request(self) -> Any:
        connection, address = super().get_request()
        try:
            # Installed before handler construction/setup/request-line parsing.
            self.accepted_guards[id(connection)] = AcceptedSocketGuard(
                connection, self.bridge_state.deadline, self.bridge_state.clock)
        except Exception:
            connection.close()
            raise
        return connection, address

    def shutdown_request(self, request: Any) -> None:
        guard = self.accepted_guards.pop(id(request), None)
        if guard is not None:
            guard.close()
        super().shutdown_request(request)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_: Any) -> None:
        # No client headers, secrets, prompts or noisy access logging to stdout.
        pass

    def parse_request(self) -> bool:
        try:
            return super().parse_request()
        finally:
            # BaseHTTP has now read the request line/headers. The whole-session
            # timer remains armed during the body, provider call and response.
            self.server.accepted_guards[id(self.connection)].finish_phase()  # type: ignore[attr-defined]

    @property
    def state(self) -> BridgeState:
        return self.server.bridge_state  # type: ignore[attr-defined]

    def respond(self, status: int, body: bytes, content_type: str = "application/json") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def error(self, status: int, message: str) -> None:
        self.respond(status, encode({"type": "error", "error": {"type": "invalid_request_error" if status < 500 else "api_error", "message": message}}))

    def do_POST(self) -> None:
        route = message_route(self.path)
        if route == "count_tokens":
            self.error(501, "count_tokens unsupported; no provider request made")
            return
        if route != "messages":
            self.error(404, "Only /v1/messages is supported")
            return
        raw = None
        body_complete = False
        try:
            if self.client_address[0] != "127.0.0.1":
                raise ProtocolError("Loopback clients only")
            if self.headers.get("Transfer-Encoding"):
                raise ProtocolError("Transfer-Encoding is unsupported")
            if self.headers.get("Origin"):
                raise ProtocolError("Browser-origin requests are unsupported")
            if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
                raise ProtocolError("Content-Type application/json is required")
            lengths = self.headers.get_all("Content-Length", [])
            if len(lengths) != 1 or not lengths[0].isdigit():
                raise ProtocolError("A single Content-Length is required")
            length = int(lengths[0])
            if not 0 < length <= MAX_BODY_BYTES:
                raise ProtocolError("Client request size exceeds bound")
            guard = self.server.accepted_guards[id(self.connection)]  # type: ignore[attr-defined]
            guard.start_phase()
            try:
                raw = self.rfile.read(length)
            finally:
                guard.finish_phase()
            if len(raw) != length:
                raise ProtocolError("Incomplete client request")
            body_complete = True
            request = decode(raw)
            converted = anthropic_to_openai(request)
        except (ProtocolError, OSError, ValueError) as exc:
            self.state.reject_before_provider(raw, str(exc), body_complete)
            self.error(400, str(exc))
            return
        try:
            message = self.state.perform(raw, request, converted)
            if request.get("stream", False):
                self.respond(200, anthropic_sse(message), "text/event-stream; charset=utf-8")
            else:
                self.respond(200, encode(message))
        except (ProtocolError, OSError, ValueError) as exc:
            self.state.stop("provider_or_protocol_failure")
            self.error(502, str(exc))

    def do_GET(self) -> None:
        self.error(404, "Only POST /v1/messages is supported")

    do_PUT = do_GET
    do_DELETE = do_GET
    do_PATCH = do_GET


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", required=True, type=Path, help="New directory; must not already exist")
    parser.add_argument("--source-ids-file", required=True, type=Path, help="Existing verified source-ID metadata JSON supplied by root")
    parser.add_argument("--stop-file", type=Path, help="Optional child path under evidence directory; operator creates it after CLI completion")
    args = parser.parse_args()
    sources = decode(args.source_ids_file.read_bytes())
    if not isinstance(sources, (dict, list)) or not sources:
        parser.error("Non-empty actual source-ID metadata is required")
    directory = args.evidence_dir.resolve()
    stop_file = resolve_stop_file(directory, args.stop_file)
    directory.mkdir(parents=True, exist_ok=False)
    state = BridgeState(directory, sources)
    server = BoundedHTTPServer(("127.0.0.1", 0), Handler, state)
    server.timeout = 1.0
    state.metadata.update(listenHost="127.0.0.1", listenPort=server.server_port, sourceIdsFileSha256=hashlib.sha256(args.source_ids_file.read_bytes()).hexdigest())
    state.metadata.update(operatorStopFile=str(stop_file) if stop_file else None,
                          safeguardsClassifier="Anthropic server-side classifier NOT implemented; readonly CLI permissions/operator path hook required")
    state.save_metadata()
    print(encode({"port": server.server_port, "baseUrl": "http://127.0.0.1:" + str(server.server_port),
                  "sessionJson": str((directory / "session.json").resolve()), "adapterSha256": state.metadata["adapterSha256"],
                  "disclosure": DISCLAIMER}).decode("utf-8"), flush=True)
    try:
        while state.clock() < state.deadline and not state.stop_reason:
            if stop_file is not None and stop_file.exists():
                state.stop("operator_client_completed")
                break
            server.handle_request()
        if state.stop_reason is None:
            state.stop("whole_bridge_deadline")
    except KeyboardInterrupt:
        state.stop("operator_interrupt")
    finally:
        server.server_close()
        state.metadata["closedAtUtc"] = utc()
        state.save_metadata()


if __name__ == "__main__":
    main()
