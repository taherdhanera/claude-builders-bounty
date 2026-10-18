"""Import/runtime evidence only: never execute, publish, or activate a workflow."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import time
import urllib.request
import uuid

HEAD = "2ebf8e4b861cde9b6e80529782f2353fff6d2a4a"
SOURCE_PATH = "workflows/issue-5-weekly-dev-summary/weekly-github-claude-summary.workflow.json"
SOURCE_SHA256 = "690b25cbbea5f1861e669aedd9fe692cff8266695383e0d07c047fd6b114e081"
ROOT = Path(__file__).resolve().parents[1]
TEMP = Path(os.environ.get("RUNNER_TEMP", "/tmp"))
EVIDENCE = TEMP / "n8n2691-import-evidence"
RUNTIME = TEMP / "n8n2691-runtime"
PORT = 57691


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def save(name, value):
    (EVIDENCE / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def emit():
    token = uuid.uuid4().hex
    print(f"::stop-commands::{token}")
    if EVIDENCE.exists():
        for path in sorted(EVIDENCE.iterdir()):
            if path.is_file() and path.suffix in {".json", ".jsonl", ".txt", ".log"}:
                data = path.read_bytes()
                print(f"\n=== BEGIN EVIDENCE {path.name} SHA256 {digest(data)} ===")
                sys.stdout.write(data.decode("utf-8"))
                print(f"\n=== END EVIDENCE {path.name} ===")
    print(f"::{token}::")


def environment():
    # No provider keys, webhook URLs, repository tokens, proxy settings, or user
    # configuration are copied into npm, n8n, or the expression subprocesses.
    env = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL") if key in os.environ}
    isolated_home = RUNTIME / "home"
    isolated_home.mkdir()
    env.update({
        "HOME": str(isolated_home), "CI": "1", "NO_COLOR": "1",
        "npm_config_cache": str(RUNTIME / "npm-cache"),
        "N8N_USER_FOLDER": str(RUNTIME / "data"),
        "N8N_LISTEN_ADDRESS": "127.0.0.1", "N8N_HOST": "127.0.0.1",
        "N8N_PORT": str(PORT), "N8N_PROTOCOL": "http", "N8N_SECURE_COOKIE": "false",
        "N8N_DIAGNOSTICS_ENABLED": "false", "N8N_VERSION_NOTIFICATIONS_ENABLED": "false",
        "N8N_TEMPLATES_ENABLED": "false", "N8N_PERSONALIZATION_ENABLED": "false",
        "N8N_COMMUNITY_PACKAGES_ENABLED": "false", "N8N_LICENSE_AUTO_RENEW_ENABLED": "false",
        "N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS": "true",
    })
    return env


def compare_export(source, exported):
    if not isinstance(exported, list) or len(exported) != 1:
        raise ValueError("Expected exactly one exported workflow")
    restored = exported[0]
    for field in ("id", "name", "nodes", "connections", "settings"):
        if restored.get(field) != source.get(field):
            raise ValueError("Imported/exported configuration differs: " + field)
    if restored.get("active") is not False or restored.get("activeVersionId") is not None:
        raise ValueError("Exported workflow is active or published")
    if restored.get("pinData", {}) != source.get("pinData", {}):
        raise ValueError("Pinned data differs")
    return {"fullNodesEqual": True, "connectionsEqual": True, "settingsEqual": True,
            "pinDataEqual": True, "active": False, "activeVersionId": None,
            "nodeCount": len(restored["nodes"]), "id": restored["id"]}


EXPRESSION_PROBE = r'''
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { resolve } from 'node:path';
const [runtime, exportedPath] = process.argv.slice(1);
const requireN8n = createRequire(resolve(runtime, 'node_modules/n8n/package.json'));
const { Expression } = requireN8n('n8n-workflow');
const version = requireN8n('n8n-workflow/package.json').version;
assert.equal(version, '2.32.1');
const workflow = JSON.parse(readFileSync(exportedPath, 'utf8'))[0];
const fixtures = ['ordinary', '"Quoted"\nRenée 🚀', '{{ $env.UNUSED_TEST_SECRET }}', 'C:\\test\r\n\t'];
let passed = 0;
for (const [name, key] of [['Generate Claude Summary', 'prompt'], ['Send Discord Summary', 'message']]) {
  const node = workflow.nodes.find(n => n.name === name);
  assert.ok(node);
  assert.equal(node.parameters.method, 'POST');
  assert.equal(node.parameters.sendBody, true);
  assert.equal(node.parameters.specifyBody, 'json');
  for (const text of fixtures) {
    const actual = new Expression('UTC').resolveSimpleParameterValue(node.parameters.jsonBody, {$json:{[key]:text}});
    const expected = name === 'Generate Claude Summary'
      ? {model:'claude-sonnet-4-6', max_tokens:1200, temperature:0.3, messages:[{role:'user',content:text}]}
      : {content:text};
    assert.deepEqual(actual, expected);
    assert.deepEqual(JSON.parse(JSON.stringify(actual)), expected);
    passed++;
  }
}
console.log(JSON.stringify({resolverVersion:version, exportedBodyExpressionChecks:passed, noHttpRequests:true}));
'''


def main():
    EVIDENCE.mkdir(exist_ok=False)
    RUNTIME.mkdir(exist_ok=False)
    env = environment()
    commands = []
    server = None
    summary = {"startedAtUtc": now(), "originalPr": 2691, "originalHead": HEAD,
               "expectedSourceSha256": SOURCE_SHA256, "n8nVersionRequested": "2.32.6",
               "scope": "Exact-export import/export, expression resolver, and localhost runtime only",
               "workflowExecuted": False, "anthropicCallMade": False, "discordCallMade": False,
               "providerCredentialsProvisioned": False, "externalAccountCreated": False,
               "completeAcceptanceProof": False, "payoutOrReceivedCashProof": False,
               "runtimeVerificationPassed": False}

    def run(label, command, timeout=120):
        started = now()
        with (EVIDENCE / (label + ".log")).open("wb") as output:
            result = subprocess.run(command, cwd=ROOT, env=env, stdout=output,
                                    stderr=subprocess.STDOUT, timeout=timeout)
        commands.append({"label": label, "command": command, "startedAtUtc": started,
                         "completedAtUtc": now(), "exitCode": result.returncode})
        save("commands.json", commands)
        if result.returncode:
            raise RuntimeError(label + " failed with exit " + str(result.returncode))

    try:
        run("public-source-fetch", ["git", "-c", "credential.helper=", "fetch", "--no-tags", "--depth=1",
                                   "https://github.com/taherdhanera/claude-builders-bounty.git", HEAD])
        source_bytes = subprocess.check_output(["git", "show", HEAD + ":" + SOURCE_PATH], cwd=ROOT, env=env)
        if digest(source_bytes) != SOURCE_SHA256:
            raise ValueError("Exact Git source hash mismatch")
        source = json.loads(source_bytes)
        if source.get("active") is not False or source.get("pinData"):
            raise ValueError("Source is active or contains pinned payloads")
        if len(source["nodes"]) != 9 or any(node.get("credentials") for node in source["nodes"]):
            raise ValueError("Unexpected nodes or source credential bindings")
        (EVIDENCE / "source-workflow.json").write_bytes(source_bytes)
        summary["sourceSha256Verified"] = digest(source_bytes)
        summary["proofCommit"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, env=env).decode().strip()
        run("node-version", ["node", "--version"])
        run("npm-version", ["npm", "--version"])
        run("npm-install", ["npm", "install", "--prefix", str(RUNTIME), "--save-exact",
                            "--no-audit", "--no-fund", "n8n@2.32.6"], timeout=600)
        package = json.loads((RUNTIME / "node_modules/n8n/package.json").read_text())
        if package["version"] != "2.32.6":
            raise ValueError("Installed n8n version mismatch")
        cli = ["node", str(RUNTIME / "node_modules/n8n/bin/n8n")]
        run("n8n-version", cli + ["--version"])
        run("n8n-import", cli + ["import:workflow", "--input=" + str(EVIDENCE / "source-workflow.json")])
        exported = EVIDENCE / "exported-workflow.json"
        run("n8n-export", cli + ["export:workflow", "--id=" + source["id"], "--output=" + str(exported), "--pretty"])
        summary["roundTrip"] = compare_export(source, json.loads(exported.read_text()))
        (EVIDENCE / "expression-probe.txt").write_text(EXPRESSION_PROBE, encoding="utf-8")
        run("exported-expression-checks", ["node", "--input-type=module", "--eval", EXPRESSION_PROBE,
                                           str(RUNTIME), str(exported)])
        with (EVIDENCE / "n8n-server.log").open("wb") as output:
            server = subprocess.Popen(cli + ["start"], cwd=ROOT, env=env, stdout=output,
                                      stderr=subprocess.STDOUT, start_new_session=True)
        health = []
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for endpoint in ("/healthz", "/healthz/readiness"):
            url = "http://127.0.0.1:" + str(PORT) + endpoint
            for attempt in range(90):
                if server.poll() is not None:
                    raise RuntimeError("n8n exited before localhost readiness")
                try:
                    with opener.open(url, timeout=2) as response:
                        row = {"url": url, "status": response.status, "body": response.read().decode(), "observedAtUtc": now()}
                        if response.status != 200 or response.url != url:
                            raise ValueError("Unexpected localhost health response")
                    health.append(row)
                    break
                except OSError:
                    time.sleep(1)
            else:
                raise RuntimeError("Bounded localhost health check did not become ready")
        save("localhost-health.json", health)
        os.killpg(server.pid, signal.SIGTERM)
        server.wait(timeout=25)
        server = None
        databases = list((RUNTIME / "data").rglob("database.sqlite"))
        if len(databases) != 1:
            raise ValueError("Expected one isolated SQLite database")
        with sqlite3.connect(databases[0].resolve().as_uri() + "?mode=ro", uri=True) as db:
            workflows = db.execute('SELECT id, active, activeVersionId FROM workflow_entity').fetchall()
            counts = {table: db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
                      for table in ("execution_entity", "credentials_entity")}
        if workflows != [(source["id"], 0, None)] or any(counts.values()):
            raise ValueError("Unexpected active workflow, execution, or credential database state")
        save("isolated-database-check.json", {"workflows": workflows, "counts": counts,
                                             "scope": "No database or configuration secrets exported"})
        summary["runtimeVerificationPassed"] = True
    except Exception as error:
        summary["error"] = type(error).__name__ + ": " + str(error)
    finally:
        if server is not None and server.poll() is None:
            os.killpg(server.pid, signal.SIGTERM)
            try:
                server.wait(timeout=20)
            except subprocess.TimeoutExpired:
                os.killpg(server.pid, signal.SIGKILL)
                server.wait(timeout=10)
        summary["completedAtUtc"] = now()
        save("summary.json", summary)
    print(json.dumps(summary))
    return 0 if summary["runtimeVerificationPassed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--emit-only", action="store_true")
    args = parser.parse_args()
    if args.emit_only:
        emit()
    else:
        raise SystemExit(main())
