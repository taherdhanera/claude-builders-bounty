"""One supplemental real CLI/local-model attempt; never certify bounty acceptance."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone

ORIGINAL_HEAD = "8f9aec6dc55f4c10b4c1581c1da52d4e6ddfca9c"
TEMPLATE_PATH = "templates/nextjs-sqlite-saas/CLAUDE.md"
PROTOCOL_PATH = "templates/nextjs-sqlite-saas/verification/claude-code-greenfield-smoke.md"
# Canonical LF Git blob. The preserved Windows fixture has mixed CRLF/LF bytes
# and a different byte hash; normalizing only CRLF produces this exact blob.
TEMPLATE_SHA256 = "4e4deac8329413770235df143c745613b27aa92dca0cc0fc7d0e76492c6efd08"
MODEL = "qwen3.5:2b"
DELIVERY_INSTRUCTIONS = (
    "This is a read-only headless Plan-mode verification. The available tools are "
    "Read, Glob and Grep. Do not call unavailable tools or create a plan file. "
    "After inspecting the starter, return the complete plan directly as final text. "
    "Questions remain governed by the exact first prompt's essential-safety rule. "
    "These delivery instructions supply no technical decisions and change no rubric."
)
BASE_URL = "http://127.0.0.1:11434"
ROOT = Path(__file__).resolve().parents[1]
RUNNER_TEMP = Path(os.environ.get("RUNNER_TEMP", "/tmp"))
EVIDENCE = RUNNER_TEMP / "open-model-evidence"
FIXTURE = RUNNER_TEMP / "claude2284-fresh-fixture" / "acme-saas"


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def save(name, data):
    (EVIDENCE / name).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def snapshot():
    return {str(path.relative_to(FIXTURE)): digest(path.read_bytes())
            for path in sorted(FIXTURE.rglob("*"))
            if path.is_file() and ".git" not in path.relative_to(FIXTURE).parts}


def clean_environment():
    # All credentials, billing/provider switches, proxies and repository tokens are
    # discarded rather than copied and selectively redacted. No secrets are read.
    env = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL", "TERM") if key in os.environ}
    isolated_home = RUNNER_TEMP / "claude2284-isolated-home"
    isolated_home.mkdir(exist_ok=False)
    env.update({
        "HOME": str(isolated_home), "CI": "1", "NO_COLOR": "1",
        "CLAUDE_CONFIG_DIR": str(isolated_home / ".claude"),
        "ANTHROPIC_BASE_URL": BASE_URL, "ANTHROPIC_AUTH_TOKEN": "ollama",
        "ANTHROPIC_API_KEY": "", "ANTHROPIC_MODEL": MODEL,
        "ANTHROPIC_SMALL_FAST_MODEL": MODEL,
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": MODEL,
        "ANTHROPIC_DEFAULT_SONNET_MODEL": MODEL,
        "ANTHROPIC_DEFAULT_OPUS_MODEL": MODEL,
        "CLAUDE_CODE_SUBAGENT_MODEL": MODEL,
        "DISABLE_AUTOUPDATER": "1", "DISABLE_TELEMETRY": "1",
        "DISABLE_ERROR_REPORTING": "1",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        "CLAUDE_CODE_MAX_RETRIES": "0", "CLAUDE_CODE_MAX_OUTPUT_TOKENS": "2048",
        "CLAUDE_CODE_MAX_CONTEXT_TOKENS": "65536", "MAX_THINKING_TOKENS": "0",
        # The CPU needs over five minutes to prefill the unchanged template
        # after Read returns it. Keep a bounded 15-minute per-request allowance;
        # the independent process deadline below still caps the entire session.
        "API_TIMEOUT_MS": "900000", "API_FORCE_IDLE_TIMEOUT": "0",
        "CLAUDE_STREAM_FIRST_BYTE_TIMEOUT_MS": "900000",
        "CLAUDE_STREAM_IDLE_TIMEOUT_MS": "900000",
        "CLAUDE_BYTE_STREAM_IDLE_TIMEOUT_MS": "900000",
        "OLLAMA_HOST": "127.0.0.1:11434", "OLLAMA_NO_CLOUD": "1",
        "OLLAMA_CONTEXT_LENGTH": "65536", "OLLAMA_NUM_PARALLEL": "1",
    })
    return env


def run(command, *, cwd=ROOT, env=None, timeout=60):
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {command[0]}: "
                           + result.stderr.decode("utf-8", errors="replace"))
    return result.stdout


def api(path, body=None):
    parsed = urllib.parse.urlsplit(BASE_URL)
    if (parsed.scheme, parsed.hostname, parsed.port) != ("http", "127.0.0.1", 11434):
        raise RuntimeError("Only the designated local endpoint is allowed")
    request = urllib.request.Request(BASE_URL + path,
        data=None if body is None else json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    # Disable proxy inheritance even for the local metadata requests.
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=30) as response:
        return json.load(response)


def emit_evidence():
    print("::stop-commands::claude2284-raw-evidence")
    # Do not truncate the raw CLI stream or stderr. Only server/download logs have
    # tails: they are operational diagnostics, not acceptance-session transcripts.
    for path in sorted(EVIDENCE.glob("*")):
        if not path.is_file() or path.suffix == ".pid":
            continue
        print(f"\n=== BEGIN EVIDENCE {path.name} SHA256 {digest(path.read_bytes())} ===", flush=True)
        raw = path.read_bytes()
        if path.name in ("ollama-server.log", "ollama-pull.log"):
            raw = b"[OPERATIONAL LOG TAIL; SESSION FILES ARE UNTRUNCATED]\n" + b"\n".join(raw.splitlines()[-100:])
        sys.stdout.flush()
        sys.stdout.buffer.write(raw)
        sys.stdout.buffer.write(b"\n")
        sys.stdout.flush()
        print(f"=== END EVIDENCE {path.name} ===", flush=True)
    print("::claude2284-raw-evidence::", flush=True)


def execute():
    summary = {
        "startedAtUtc": now(), "originalPr": 2284, "originalHead": ORIGINAL_HEAD,
        "sourceTemplateSha256": TEMPLATE_SHA256, "provider": "local Ollama",
        "modelTag": MODEL, "requestedModelContext": 65536,
        "requestedPermissionMode": "plan", "sessionId": str(uuid.uuid4()),
        "observedExecution": False, "successProofVerified": False,
        "rubricReviewRequired": True, "bountyAcceptanceVerified": False,
        "financialEvidence": False,
        "limitations": ["Official Claude Code client with an open Qwen model, not an Anthropic Claude model",
                        "Supplemental context-understanding evidence only; maintainer decides acceptability",
                        "MAX_THINKING_TOKENS=0 is a request; it does not prove local model thinking is disabled"],
    }
    before = None
    exit_code = 1
    try:
        if (EVIDENCE / "attempt.json").exists():
            raise RuntimeError("An attempt record exists; never automatically repeat the model session")
        save("attempt.json", summary)
        if os.environ.get("GITHUB_REPOSITORY") != "taherdhanera/claude-builders-bounty":
            raise RuntimeError("This proof is restricted to the owned public fork")
        if os.environ.get("GITHUB_REF") != "refs/heads/proof/claude2284-open-model-20261018":
            raise RuntimeError("Unexpected branch; original PR branch must never be modified")
        summary["proofCommit"] = run(["git", "rev-parse", "HEAD"]).decode().strip()
        run(["git", "merge-base", "--is-ancestor", ORIGINAL_HEAD, "HEAD"])
        allowed = {".github/workflows/claude2284-open-model-proof.yml", "scripts/run_claude2284_open_model_proof.py"}
        changed = set(run(["git", "diff", "--name-only", ORIGINAL_HEAD, "HEAD"]).decode().splitlines())
        if not changed.issubset(allowed):
            raise RuntimeError("Proof commit contains changes outside the isolated proof files")
        template = run(["git", "show", f"{ORIGINAL_HEAD}:{TEMPLATE_PATH}"])
        protocol = run(["git", "show", f"{ORIGINAL_HEAD}:{PROTOCOL_PATH}"])
        if digest(template) != TEMPLATE_SHA256 or (ROOT / TEMPLATE_PATH).read_bytes() != template:
            raise RuntimeError("Exact original template mismatch")
        if (ROOT / PROTOCOL_PATH).read_bytes() != protocol:
            raise RuntimeError("Exact original acceptance protocol mismatch")
        match = re.search(r"## Exact first prompt\s*\n\s*> ([^\n]+)", protocol.decode("utf-8"))
        if not match:
            raise RuntimeError("Could not unambiguously parse the protocol prompt")
        prompt = match.group(1)
        (EVIDENCE / "exact-prompt.txt").write_text(prompt + "\n", encoding="utf-8")
        summary["exactPromptSha256"] = digest((prompt + "\n").encode())
        env = clean_environment()
        versions = {key: run(command, env=env).decode().strip() for key, command in {
            "node": ["node", "--version"], "npm": ["npm", "--version"],
            "claude": ["claude", "--version"], "ollama": ["ollama", "--version"]}.items()}
        if not versions["node"].startswith("v22.") or "2.1.296" not in versions["claude"]:
            raise RuntimeError("Unexpected pinned CLI or Node.js major")
        save("runtime-versions.json", versions)
        tags = api("/api/tags")
        save("ollama-tags.json", tags)
        matching_models = [model for model in tags.get("models", []) if model.get("name") == MODEL]
        if len(matching_models) != 1 or not matching_models[0].get("digest"):
            raise RuntimeError("Exact pulled public model digest is missing or ambiguous")
        summary["modelDigest"] = matching_models[0]["digest"]
        save("ollama-show.json", api("/api/show", {"model": MODEL, "verbose": True}))
        FIXTURE.parent.mkdir(exist_ok=False)
        fixture_command = ["npx", "--yes", "create-next-app@15.5.26", "acme-saas", "--ts", "--eslint", "--app", "--no-tailwind", "--use-npm", "--skip-install", "--disable-git", "--no-src-dir", "--import-alias", "@/*", "--yes"]
        (EVIDENCE / "fixture-generation.log").write_bytes(run(fixture_command, cwd=FIXTURE.parent, env=env, timeout=180))
        package = json.loads((FIXTURE / "package.json").read_text())
        if package.get("dependencies", {}).get("next") != "15.5.26" or (FIXTURE / "node_modules").exists():
            raise RuntimeError("Fixture is not the required fresh Next.js 15.5.26 skip-install starter")
        (FIXTURE / "CLAUDE.md").write_bytes(template)
        run(["git", "init", "--quiet"], cwd=FIXTURE, env=env)
        run(["git", "add", "."], cwd=FIXTURE, env=env)
        run(["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", "-c", "user.name=Public proof fixture", "-c", "user.email=proof@example.invalid", "commit", "-qm", "Fresh disposable starter baseline"], cwd=FIXTURE, env=env)
        before = snapshot()
        save("fixture-before.json", before)
        save("fixture-package.json", package)
        command = ["claude", "--restricted", "--permission-mode", "plan", "--permission-prompts", "none", "--tools", "Read,Glob,Grep", "--allowedTools", "Read,Glob,Grep", "--disallowedTools", "mcp__*", "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}', "--setting-sources", "", "--disable-slash-commands", "--no-chrome", "--session-id", summary["sessionId"], "--no-session-persistence", "--model", MODEL, "--append-system-prompt", DELIVERY_INSTRUCTIONS, "--output-format", "stream-json", "--verbose", "-p", prompt]
        save("invocation.json", {"command": command, "cwd": str(FIXTURE), "timeoutSeconds": 1200, "credentialsInherited": False, "localDummyAuthOnly": True})
        summary["sessionStartedAtUtc"] = now()
        with (EVIDENCE / "claude-plan-output.jsonl").open("wb") as output, (EVIDENCE / "claude-plan-stderr.log").open("wb") as error:
            process = subprocess.Popen(command, cwd=FIXTURE, env=env, stdin=subprocess.DEVNULL, stdout=output, stderr=error, start_new_session=True)
            summary["observedExecution"] = True
            try:
                exit_code = process.wait(timeout=1200)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                exit_code = 124
                summary["timedOut"] = True
        summary["sessionExitCode"] = exit_code
        tool_calls, invalid_lines, result_events = [], [], []
        for number, line in enumerate((EVIDENCE / "claude-plan-output.jsonl").read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                invalid_lines.append(number)
                continue
            if event.get("type") == "result":
                result_events.append(event)
            for block in event.get("message", {}).get("content", []):
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    tool_calls.append({"streamLine": number, **block})
        save("observed-tool-calls.json", tool_calls)
        save("result-events.json", result_events)
        summary.update(rawStreamInvalidJsonLines=invalid_lines, observedToolCallCount=len(tool_calls), observedResultEventCount=len(result_events))
        if invalid_lines or not result_events:
            summary["sessionCoverageIncomplete"] = True
    except Exception as error:
        summary["error"] = f"{type(error).__name__}: {error}"
    finally:
        if before is not None:
            after = snapshot()
            save("fixture-after.json", after)
            summary["fixtureUnchanged"] = before == after
            status = subprocess.run(["git", "status", "--short"], cwd=FIXTURE, capture_output=True)
            (EVIDENCE / "fixture-final-git-status.txt").write_bytes(status.stdout + status.stderr)
            summary["fixtureGitStatusExitCode"] = status.returncode
            summary["fixtureGitClean"] = status.returncode == 0 and not status.stdout
        summary["completedAtUtc"] = now()
        summary["successProofVerified"] = False
        summary["rubricReviewRequired"] = True
        save("summary.json", summary)
    if summary.get("error") or not summary.get("fixtureUnchanged"):
        return 1
    return exit_code


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--emit-only", action="store_true")
    options = parser.parse_args()
    EVIDENCE.mkdir(exist_ok=True)
    if options.emit_only:
        emit_evidence()
    else:
        raise SystemExit(execute())
