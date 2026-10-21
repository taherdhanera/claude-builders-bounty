# Supplemental Claude Code CLI protocol adapter

Prepared only. **The authoring subagent has not executed this code or its tests,
started a server, or contacted any provider.** Root must inspect and test it.

This uses the real Claude Code CLI with a disclosed Anthropic-to-OpenAI adapter
and an anonymous third-party model. It is **not Anthropic execution proof**, a
claim that the provider is Anthropic, maintainer acceptance, or received cash.
The adapter executes no tools. Root must separately guard all CLI tool paths,
commands, allowed files and environment. Never run code supplied in email.

The fixed upstream is `https://text.pollinations.ai/openai`, model `openai-fast`.
No fallback, retry, proxy, API key, inherited environment credential or upstream
authorization header is supported. Client headers are not logged or forwarded.

## Root-operated preparation

1. Inspect the source, then run the local-only tests:

   ```powershell
   python -m unittest discover -s work/free-cli-2284-20261021 -p test_anthropic_openai_bridge.py -v
   ```

2. Save the **actual independently verified** source IDs/URLs, retrieval time,
   anonymous-tier/model metadata and policy conclusions as a JSON object/array.
   No example file with fabricated verification is supplied.

3. Launch once, pointing at a new evidence directory and that verified file:

   ```powershell
   python work/free-cli-2284-20261021/anthropic_openai_bridge.py --evidence-dir work/free-cli-2284-20261021/run-UNIQUE --source-ids-file work/free-cli-2284-20261021/verified-source-ids.json --stop-file client-finished.stop
   ```

The single stdout JSON record contains the ephemeral loopback port, base URL,
adapter SHA256 and session evidence path. Root supplies this base URL to its
separately guarded CLI process; any SDK authentication must be an explicit dummy
value, never a copied credential. The adapter cannot accept arbitrary hosts.

## Limits and evidence

- Only `POST /v1/messages` with no query or the exact observed `beta=true` query
  is forwarded; count-tokens is explicitly HTTP 501. Other queries are rejected.
- Text/system/custom JSON-schema tools only. Unsupported modalities, requested extended thinking,
  malformed/duplicate JSON arguments, unknown tools, incomplete tool cycles and
  unsupported request semantics fail closed.
- At most 16 upstream calls, 4096 output tokens/call, 180 seconds/call and 1200
  seconds total. At least 40 seconds elapse after each completion before another
  upstream start. Non-2xx, transport, protocol, quota or authentication failures
  permanently stop future calls; no fallback/retries are attempted.
- Provider streaming is disabled. An actual complete response is translated to
  Anthropic JSON or buffered Anthropic SSE, with real provider token usage.
  Provider `reasoning_effort` defaults to root-verified `low`; an observed
  `output_config.effort` of `low` or `high` maps directly to that provider field. Any
  returned reasoning remains verbatim in raw evidence and is never injected into
  the answer, tool calls or a plan.
  Responses, tests or tool results are never invented. Protocol event IDs and
  envelopes are adapter metadata, not model-generated output.
- Each round retains exact client and provider request bytes, observed provider
  response bytes, status/reason, ordered header pairs and SHA256 references. A
  timeout retains only bytes/status/headers observed before the bounded return;
  it is an incomplete exchange, never successful model output.
- Pre-provider rejected requests retain observed raw client bytes, their SHA256,
  error and detection time under `rejected-client-NN/`, without client headers.
  Evidence separately records zero upstream calls for that rejected request and
  the total upstream count already observed. An unread/rejected body is marked
  unavailable; it is never reconstructed from guessed request contents.
- Observed conversation `system` turns retain their order and text. Only the
  observed version-1, restricted Plan `dangerous_tool_use` safety envelope is
  accepted, with Read/Glob/Grep exposed and no additional allowed tools or network
  directories. Its original context is preserved as explicitly disclosed system
  metadata. **Anthropic's server-side classifier is not implemented** by this
  provider; local CLI permissions and root's independent path hook are required.
- The optional `--stop-file` must be a child path under the new evidence directory.
  Root creates it after CLI completion; the 1-second accept loop observes it and
  records `operator_client_completed` plus normal `closedAtUtc`. No HTTP shutdown
  endpoint is exposed. This does not interrupt a provider request in progress.
- A watchdog closes the upstream socket at the call deadline and stops all
  future calls. Remote server-side cancellation cannot be verified by a client;
  a daemon transport worker may finish unwinding after cancellation. Do not
  retry an uncertain result. Root should terminate the bridge after the CLI run.
- Before BaseHTTP parses an accepted connection, the server installs both an
  absolute remaining-session socket guard and a 10-second total header timer.
  The request body gets its own 10-second total phase timer. These interrupt
  trickle clients; individual socket read timeouts alone would be insufficient.
  Finishing headers/body cancels only the corresponding phase timer; the
  absolute session deadline remains armed throughout provider work and output.
- `session.json` binds the adapter hash and actual supplied source metadata. A
  provider quota header reaching zero allows the already received actual result
  but shuts down the bridge before another call.

The HTTP layer and real provider/CLI interoperability still require root's
execution check. Pure tests establish protocol/budget behavior with local
fixtures only; they are not live-provider or genuine CLI proof.
