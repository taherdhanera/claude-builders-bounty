# Separate PR #2284 context-comprehension proof

This is a prepared, separate supplemental test. It has not executed a model. It preserves the original feature-design stress test, its results and its failures. It uses the same canonical CLAUDE.md and disposable project fixture with a new, explicitly disclosed context question. It does not claim to pass the earlier feature-design test.

Stage this folder as `scripts/pr2284-context-proof/` and `workflow-template.yml` as `.github/workflows/claude2284-context-20261023.yml`. The sole proof commit must directly parent PR head `26994b38341d36692b81291d689b0e3adad0cff2`, on `proof/claude2284-context-20261023`. Only the new scripts prefix and workflow may differ. The runtime checks the exact branch, public owned repository and attempt 1. This preparation creates no commit, push or workflow run.

## Exact input and provenance

The UTF-8 `context-prompt.txt` is the sole prompt source, with no trailing newline or preprocessing. Its SHA256 is `501f52017a265951855123041c1214083140c378a0c26802b5ed7b11f55ae8c8`:

> What project is this, and what conventions and constraints should you follow when working in it? Give a concise overview based on the project files.

The prompt has no supplied answers, anti-question hints or appended system instructions. Its exact bytes and hash are recorded. The original source protocol is fetched from the exact source head and retained as `original-feature-design-protocol-reference.md`; its hash is named separately and it is explicitly not executed. The model only sees the fresh project fixture and the question, not an independent reviewer rubric or prior answer.

The template remains `templates/nextjs-sqlite-saas/CLAUDE.md`, SHA256 `252b4d86c2d6c432fe0c92ec90c7c249495dfa2ab5ff29c341ba7894221b7261`. Raw source and fixture manifests establish identity. The native source protocol, previous stress-test artifacts and original preparation files are unchanged.

## Execution boundaries

Official Claude Code `2.1.296`, create-next-app `15.5.28`, Ollama `0.40.6`, native `qwen3.5:9b-q4_K_M`, archive/model hashes, 65536 context, CPU-only setup, full blob verification, resource gates and the raw native HTTP recorder are retained. This is real local open-model inference only if the future run succeeds. It is **not Anthropic inference**. It supplies no credentials, uses no paid service and disables Ollama cloud.

The CLI uses `--permission-mode default`, `--restricted`, Read/Glob/Grep only, empty MCP, no inherited settings and at most 10 turns. The existing byte-identical PreToolUse path guard permits only the disposable fixture. Unknown tools, mutation tools, subagents and question tools remain unavailable and denied; any attempt is retained, not erased. Default mode removes the conflicting built-in Plan workflow that demanded unavailable planning tools. It does not instruct the model to avoid questions or conceal attempts.

One pull and one CLI invocation are permitted; no retries, resume, fallback model, cloud provider or ambiguous restart. The CLI budget is 1800 seconds, recorder 1860 seconds, launcher 2220 seconds and workflow 40 minutes. Setup reserves the complete CLI budget before starting. Resource sampling, low-memory/paging termination, process cleanup, exact fixture before/after hashes, raw request/response/CLI/hook logs and evidence manifest remain mandatory. The final three workflow minutes are reserved for exact hash-framed evidence output.

## Success must be independently scored

A successful exit means only: a successful terminal `end_turn` result, complete native HTTP evidence, unchanged fixture, no unexpected tool attempts, no tool errors and no resource/cleanup failure. A denied Read with `is_error: true` fails this gate even though Read is an allowed tool name. It does **not** certify factual context comprehension, no clarification in prose, sponsor acceptance, payment eligibility or received cash. Those fields remain explicitly unverified.

An independent reviewer must inspect the complete CLI text, tool calls/results, hook log and native responses against the project files and the separately preregistered rubric. Required outcome: an accurate concise project overview, applicable conventions and constraints, a terminal response, and **no clarification attempts anywhere**. An unavailable or denied AskUserQuestion call is a failure even if a later response finishes. Natural-language questions in earlier or final assistant text also require explicit review; they are never hidden by a tool restriction or treated as success merely because the transport completed. No automatic semantic pass is generated. Preserve partial, wrong, questioning, interrupted and failed output without laundering it into proof.

## Offline checks

From this folder run `python -B -m unittest -v test_native_boundaries test_context_harness`. The tests use only local fixtures and mocks. They cover exact prompt sourcing/tamper rejection, the complete default-mode command with no appended hints, workflow identity and budgets, runtime/model/source pins, readonly path boundaries, unavailable-question failure propagation and honest structural-versus-semantic reporting. They do not run Git, a model, HTTP requests or a workflow. See `test-receipt.json` for actual test results after preparation.
