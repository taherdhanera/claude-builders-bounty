# Adapter change record

All changes below were authored without running the adapter, tests, processes,
or network calls. Root retains the source hash/snapshot used for each execution.

- **v1**: initial adapter, 20-second provider spacing, fixed `reasoning_effort=low`,
  raw provider reasoning retained without forwarding. Root reported that its 22
  local tests passed; author did not independently execute them.
- **v2**: rejected client requests retain exact observed raw bytes and SHA256,
  error/time and distinct zero-per-rejection versus observed-total call counts.
  Handler initializes `raw=None`, then `body_complete=False`, setting completeness
  only after the declared request bytes have actually been read. Added two local
  evidence regressions. No claim of execution is made for this revision.
- **v3**: `BoundedHTTPServer.get_request` installs `AcceptedSocketGuard` before
  HTTP parsing; absolute whole-session and 10-second header/body phase timers
  interrupt slow trickle clients. Added two fake-socket/fake-timer regressions.
  No provider payload/query compatibility was relaxed. No claim of execution is
  made for this revision.

The operator must bind the final source SHA256 in each new session.json and keep
prior run directories/source snapshots. Do not rewrite an already used source
snapshot, test report, provider exchange or CLI transcript as a later revision.

- **v4**: compatibility is limited to root's actual offline CLI capture: exact
  `beta=true` query, ordered `system` conversation turns, `output_config.effort`
  low/high mapping, and original restricted Plan safeguards preserved as disclosed
  non-classifier context with Read/Glob/Grep only. Adds evidence-child stop-file
  shutdown. Root authorized a 180-second per-provider cap before the first full
  run; total 1200 seconds, 16 calls, 20-second spacing and 4096 output-token bounds
  remain unchanged. Author inspected captured JSON but executed no adapter/tests
  or network calls. Root must test/hash this revision before the single CI run.

- **v5**: changes only the minimum between-call completion/start gap from 20 to
  40 seconds, plus its test expectation and current README budget. Root reported
  actual CI run `39609407469`: the first provider exchange returned HTTP 200 and
  a real `Read` call for `CLAUDE.md`; the second returned HTTP 402 `FREE_LIMIT`,
  stating one reply per 30 seconds per IP and `Retry-After: 4`. The recorded
  between-call gap was 20.0004 seconds. The failed run made no retry. The new
  40-second minimum is a conservative response to that observed provider limit;
  it does not establish a guaranteed free quota or successful subsequent run.
  The public v4 commit/run remains immutable. Author executed no tests, network
  calls or run attempts for v5; root owns cooldown, testing and any new attempt.

- **v6**: root reported a real provider tool name
  `Glob<|channel|>commentary`. Exactly `Read`, `Glob` or `Grep` plus that literal
  suffix may now pass through as an UNKNOWN raw name only when its canonical
  base is already declared. Names are never stripped, normalized or renamed.
  Matching history requires `tool_result.is_error=true`; a forged successful
  result is rejected. Other unknown names, duplicates and malformed arguments
  remain rejected. Session/round evidence discloses the diagnostic. Three new
  local regressions cover exact raw error roundtrip and rejection boundaries.
  Author executed no code or network. Root owns offline actual-CLI rejection
  and unchanged-fixture checks before any separately gated live attempt.
