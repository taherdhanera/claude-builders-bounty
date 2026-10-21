# Preparation history

## v2 — 2026-10-21, separate manifest-revision folder

Preserves all v1 preparation files and public run 39617185522. That run stopped before CLI/inference at an unsupported hardcoded local manifest path/hash assumption. This revision fetches the exact official registry manifest once with HTTP/SHA256 pinning, then verifies every exact installed blob's byte count and SHA256 plus independent exact API/tags identity. A bounded local-layout/hash/semantic-JSON inventory is diagnostic only. Model, fixture, prompt, resource boundaries and one native CLI budget remain unchanged. `/api/show` uses verbose false; setup failures have explicit stage messages. New isolated branch/workflow: `proof/claude2284-ollama9b-manifest-20261021`. No code/test/model execution, network or Git operation by the revision author.

## v1 — 2026-10-21

New native Ollama route, separate from all Pollinations adapter attempts. Reuses the current exact PR head/template/protocol, fresh starter, official CLI pin, path guard and exact evidence framing. Pins Ollama 0.40.6 and `qwen3.5:9b-q4_K_M` manifest/layers. Adds measured RAM/disk gates, actual native CPU/context checks, absolute budgets, no retries and a transparent raw native-HTTP recorder. Authoring agent performed no execution, tests, inference, network or Git operations.
