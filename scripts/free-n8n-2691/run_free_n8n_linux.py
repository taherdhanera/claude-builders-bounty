"""One disclosed supplemental n8n-engine/model/local-sink integration attempt.

The submitted export stays immutable. Only a disposable copy's model URL changes.
This cannot establish Anthropic execution, real Discord delivery, acceptance or cash.
Root must review/test this prepared launcher before its single public-runner launch.
"""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import re
import signal
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import uuid


WORK = Path(__file__).resolve().parent
ROOT = WORK.parents[1]
SOURCE_HEAD = '2ebf8e4b861cde9b6e80529782f2353fff6d2a4a'
SOURCE_PATH = 'workflows/issue-5-weekly-dev-summary/weekly-github-claude-summary.workflow.json'
SOURCE_SHA256 = '690b25cbbea5f1861e669aedd9fe692cff8266695383e0d07c047fd6b114e081'
BRANCH = 'refs/heads/proof/n8n2691-anonymous-engine-20261021'
N8N_VERSION = '2.32.6'
CATALOG_URL = 'https://text.pollinations.ai/models'
PROVIDER_URL = 'https://text.pollinations.ai/openai'
DISCLOSURE = ('Actual n8n engine with a disclosed disposable model-URL substitution, '
              'anonymous Pollinations GPT-OSS20B/openai-fast and a loopback HTTP capture sink. '
              'Not execution against Anthropic, real Discord delivery, maintainer acceptance, '
              'payout entitlement or received cash.')


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=True)
        stream.write('\n')


def stop_group(process):
    if process is None:
        return
    for signum in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(process.pid, signum)
        except ProcessLookupError:
            break
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            continue
    if process.poll() is None:
        raise RuntimeError('Exact owned child did not stop within cleanup bounds.')


def command(args, cwd, env, evidence, label, timeout):
    out, err = evidence / (label + '-stdout.txt'), evidence / (label + '-stderr.txt')
    record = dict(command=[str(value) for value in args], cwd=str(cwd), startedAtUtc=now(), timeoutSeconds=timeout)
    process = None
    try:
        with out.open('xb') as stdout, err.open('xb') as stderr:
            process = subprocess.Popen(args, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                stdout=stdout, stderr=stderr, start_new_session=True)
            record['pid'] = process.pid
            try:
                record['exitCode'] = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                record['timedOut'] = True
    finally:
        stop_group(process)
        record.update(completedAtUtc=now(), stdoutSha256=sha(out.read_bytes()) if out.exists() else None,
                      stderrSha256=sha(err.read_bytes()) if err.exists() else None)
        save(evidence / (label + '-process.json'), record)
    if record.get('timedOut') or record.get('exitCode') != 0:
        raise RuntimeError(label + ' failed or exceeded its deadline; no retry/fallback.')
    return out.read_bytes()


def environment(home):
    env = {key: value for key, value in os.environ.items() if key in {'PATH', 'LANG', 'LC_ALL'}}
    home.mkdir(mode=0o700, parents=True, exist_ok=False)
    (home / 'tmp').mkdir(mode=0o700)
    env.update(HOME=str(home), TMPDIR=str(home / 'tmp'), XDG_CONFIG_HOME=str(home / '.config'),
        XDG_CACHE_HOME=str(home / '.cache'), CI='1', NO_COLOR='1',
        GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null', GIT_TERMINAL_PROMPT='0',
        NPM_CONFIG_USERCONFIG='/dev/null', NPM_CONFIG_AUDIT='false', NPM_CONFIG_FUND='false',
        NPM_CONFIG_REGISTRY='https://registry.npmjs.org/')
    return env


def evidence_path():
    run_id, attempt = os.environ.get('GITHUB_RUN_ID', ''), os.environ.get('GITHUB_RUN_ATTEMPT', '')
    if not run_id.isdecimal() or not attempt.isdecimal():
        raise RuntimeError('Actual GitHub run/attempt identifiers are required.')
    return Path(os.environ['RUNNER_TEMP']) / ('free-n8n-2691-evidence-' + run_id + '-' + attempt)


def emit(evidence):
    if not evidence.is_dir():
        raise RuntimeError('No evidence directory exists; no success claim.')
    paths = sorted(path for path in evidence.rglob('*') if path.is_file() and not path.is_symlink())
    token = 'exact-evidence-' + uuid.uuid4().hex
    while any(token.encode() in path.read_bytes() for path in paths):
        token = 'exact-evidence-' + uuid.uuid4().hex
    print('::stop-commands::' + token, flush=True)
    try:
        for path in paths:
            data = path.read_bytes()
            print('BEGIN_EXACT_EVIDENCE ' + json.dumps(dict(path=path.relative_to(evidence).as_posix(),
                  size=len(data), sha256=sha(data), encoding='base64')), flush=True)
            encoded = base64.b64encode(data).decode('ascii')
            for offset in range(0, len(encoded), 8192):
                print(encoded[offset:offset + 8192], flush=True)
            print('END_EXACT_EVIDENCE', flush=True)
    finally:
        print('::' + token + '::', flush=True)


class CaptureServer(HTTPServer):
    """One loopback request to an unguessable test route; no remote Discord call."""
    def __init__(self, evidence):
        self.evidence = evidence
        self.route = '/capture/' + uuid.uuid4().hex
        self.attempts = 0
        self.capture = None
        self.failure = None
        self._timer_by_socket = {}
        super().__init__(('127.0.0.1', 0), CaptureHandler)

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(10)
        def expire():
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        timer = threading.Timer(10, expire)
        timer.daemon = True
        self._timer_by_socket[id(connection)] = timer
        timer.start()
        return connection, address

    def shutdown_request(self, request):
        timer = self._timer_by_socket.pop(id(request), None)
        if timer:
            timer.cancel()
        super().shutdown_request(request)


class CaptureHandler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    def log_message(self, *_args):
        pass

    def do_POST(self):
        server = self.server
        server.attempts += 1
        record = dict(observedAtUtc=now(), source='actual loopback HTTP request', method=self.command,
                      path=self.path, clientAddress=self.client_address[0], headers=list(self.headers.items()))
        raw = b''
        try:
            assert server.attempts == 1, 'Only one sink request is authorized.'
            assert self.client_address[0] == '127.0.0.1' and self.path == server.route
            assert not self.headers.get('Transfer-Encoding') and not self.headers.get('Origin')
            assert self.headers.get('Content-Type', '').split(';')[0].strip().lower() == 'application/json'
            lengths = self.headers.get_all('Content-Length', [])
            assert len(lengths) == 1 and lengths[0].isdigit() and 0 < int(lengths[0]) <= 1_048_576
            raw = self.rfile.read(int(lengths[0]))
            payload = validate_sink_body(raw, int(lengths[0]))
            record.update(bodyComplete=True, bodySha256=sha(raw), payload=payload, accepted=True,
                          responseStatus=204, disclosure='Local test sink, not Discord.')
            (server.evidence / 'sink-request-body.bin').write_bytes(raw)
            save(server.evidence / 'sink-request.json', record)
            server.capture = record
            self.send_response(204)
            self.send_header('Content-Length', '0')
            self.send_header('Connection', 'close')
            self.end_headers()
        except Exception as error:
            server.failure = type(error).__name__ + ': ' + str(error)
            record.update(accepted=False, error=server.failure, observedBodySha256=sha(raw))
            if not (server.evidence / 'sink-request-failure.json').exists():
                (server.evidence / 'sink-rejected-body.bin').write_bytes(raw)
                save(server.evidence / 'sink-request-failure.json', record)
            self.send_response(400)
            self.send_header('Content-Length', '0')
            self.send_header('Connection', 'close')
            self.end_headers()
        finally:
            self.close_connection = True

    def do_GET(self):
        self.server.attempts += 1
        self.server.failure = 'Unexpected HTTP method to the loopback sink.'
        self.send_response(405)
        self.send_header('Content-Length', '0')
        self.send_header('Connection', 'close')
        self.end_headers()
        self.close_connection = True
    do_PUT = do_DELETE = do_PATCH = do_GET


def validate_sink_body(raw, expected_length):
    """Pure validation of the actual captured bytes, with no synthetic payloads."""
    if not isinstance(raw, bytes) or type(expected_length) is not int or not 0 < expected_length <= 1_048_576:
        raise ValueError('Invalid sink body framing.')
    if len(raw) != expected_length:
        raise ValueError('Incomplete sink request body.')
    payload = json.loads(raw)
    if not isinstance(payload, dict) or set(payload) != {'content'}:
        raise ValueError('Expected only the actual content field.')
    if not isinstance(payload['content'], str) or not 0 < len(payload['content']) <= 1900:
        raise ValueError('Missing or oversized sink message.')
    return payload


def raw_engine_data(stdout):
    """Keep stdout intact; accept only an actual complete JSON runData object."""
    try:
        text = stdout.decode('utf-8')
    except (AttributeError, UnicodeDecodeError) as error:
        raise RuntimeError('Raw engine output is not complete UTF-8 bytes.') from error
    decoder, found, consumed_until = json.JSONDecoder(), [], -1
    for match in re.finditer(r'(?m)^\s*(?=\{)', text):
        if match.end() < consumed_until:
            continue  # Nested pretty-printed objects belong to their parsed outer document.
        try:
            value, consumed_until = decoder.raw_decode(text, match.end())
        except json.JSONDecodeError as error:
            raise RuntimeError('Incomplete JSON-looking engine output; do not extract nested fragments.') from error
        if not isinstance(value, dict):
            continue
        candidates = [value, value.get('data')]
        for candidate in candidates:
            result_data = candidate.get('resultData') if isinstance(candidate, dict) else None
            if isinstance(result_data, dict) and isinstance(result_data.get('runData'), dict):
                found.append(candidate)
    if len(found) != 1:
        raise RuntimeError('Raw CLI output did not contain exactly one verified full runData object; preserve it without reconstruction.')
    return found[0]


def first_json(runs, name):
    entries = runs[name]
    branches = entries[-1].get('data', {}).get('main', [])
    items = [item for branch in branches if branch for item in branch]
    if len(items) != 1 or not isinstance(items[0].get('json'), dict):
        raise RuntimeError('Expected one actual output item for ' + name)
    return items[0]['json']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--emit-only', action='store_true')
    args = parser.parse_args()
    evidence = evidence_path()
    if args.emit_only:
        emit(evidence)
        return 0
    assert sys.platform.startswith('linux') and os.environ.get('GITHUB_ACTIONS') == 'true'
    assert os.environ.get('GITHUB_REPOSITORY') == 'taherdhanera/claude-builders-bounty'
    assert os.environ.get('GITHUB_REF') == BRANCH and os.environ.get('GITHUB_RUN_ATTEMPT') == '1'
    evidence.mkdir(mode=0o700, exist_ok=False)
    private = Path(os.environ['RUNNER_TEMP']) / ('free-n8n-2691-private-' + os.environ['GITHUB_RUN_ID'])
    private.mkdir(mode=0o700, exist_ok=False)
    runtime = private / 'runtime'
    env, bridge_env = environment(private / 'n8n-home'), environment(private / 'bridge-home')
    env.update(N8N_USER_FOLDER=str(private / 'data'), N8N_DIAGNOSTICS_ENABLED='false',
        N8N_LISTEN_ADDRESS='127.0.0.1', N8N_HOST='127.0.0.1',
        N8N_SSRF_PROTECTION_ENABLED='true', N8N_SSRF_ALLOWED_IP_RANGES='127.0.0.1/32',
        N8N_VERSION_NOTIFICATIONS_ENABLED='false', N8N_TEMPLATES_ENABLED='false',
        N8N_PERSONALIZATION_ENABLED='false', N8N_COMMUNITY_PACKAGES_ENABLED='false',
        N8N_LICENSE_AUTO_RENEW_ENABLED='false', N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS='true',
        N8N_BLOCK_ENV_ACCESS_IN_NODE='false', N8N_RUNNERS_ENABLED='true', N8N_RUNNERS_MODE='internal',
        EXECUTIONS_DATA_SAVE_ON_SUCCESS='all', EXECUTIONS_DATA_SAVE_ON_ERROR='all',
        EXECUTIONS_DATA_SAVE_MANUAL_EXECUTIONS='true', EXECUTIONS_TIMEOUT='300',
        GITHUB_REPO_OWNER='taherdhanera', GITHUB_REPO_NAME='claude-builders-bounty',
        GITHUB_TOKEN='', ANTHROPIC_API_KEY='anonymous-local-bridge-dummy', SUMMARY_LANGUAGE='EN')
    result = dict(startedAtUtc=now(), disclosure=DISCLOSURE, engineExecuted=False,
        integrationFlowVerified=False, actualAnthropicExecution=False, actualDiscordDelivery=False,
        maintainerAcceptanceVerified=False, receivedCashVerified=False, noAutomaticSemanticPass=True)
    overall_deadline = time.monotonic() + 1320
    bridge = sink = sink_thread = None
    source_working_sha = None
    handles = []
    stop_file = evidence / 'anonymous-bridge/operator-stop.json'
    def bounded(seconds):
        remaining = int(overall_deadline - time.monotonic())
        if remaining < 1:
            raise RuntimeError('Overall deadline expired; no further child launch.')
        return min(seconds, remaining)
    def git(*arguments):
        return subprocess.check_output(['git', *arguments], cwd=ROOT, env=env, timeout=15)
    try:
        parents = git('rev-list', '--parents', '-n', '1', 'HEAD').decode().split()
        assert len(parents) == 2 and parents[1] == SOURCE_HEAD
        assert git('status', '--porcelain=v1').decode() == ''
        source_bytes = git('show', SOURCE_HEAD + ':' + SOURCE_PATH)
        assert sha(source_bytes) == SOURCE_SHA256
        source_working_sha = sha((ROOT / SOURCE_PATH).read_bytes())
        assert json.loads((ROOT / SOURCE_PATH).read_bytes()) == json.loads(source_bytes)
        source = json.loads(source_bytes)
        assert source.get('active') is False and not source.get('pinData') and len(source['nodes']) == 9
        assert all(not node.get('credentials') for node in source['nodes'])
        (evidence / 'original-source-workflow.json').write_bytes(source_bytes)
        save(evidence / 'source-identity.json', dict(sourceHead=SOURCE_HEAD, sourcePath=SOURCE_PATH,
            sourceSha256=sha(source_bytes), sourceWorkingFileSha256=source_working_sha,
            proofCommit=parents[0], proofParent=parents[1],
            runId=os.environ['GITHUB_RUN_ID'], runAttempt=1,
            scripts={path.name: sha(path.read_bytes()) for path in sorted(WORK.glob('*')) if path.is_file()}))
        node_version = command(['node', '--version'], ROOT, env, evidence, 'node-version', bounded(15)).decode().strip()
        assert node_version.startswith('v22.')
        command(['npm', 'install', '--prefix', str(runtime), '--save-exact', '--no-audit', '--no-fund',
                 'n8n@' + N8N_VERSION], ROOT, env, evidence, 'n8n-install', bounded(600))
        assert json.loads((runtime / 'node_modules/n8n/package.json').read_text())['version'] == N8N_VERSION
        cli = ['node', str(runtime / 'node_modules/n8n/bin/n8n')]
        version = command(cli + ['--version'], ROOT, env, evidence, 'n8n-version', bounded(30)).decode().strip()
        assert version == N8N_VERSION
        help_text = command(cli + ['execute', '--help'], ROOT, env, evidence, 'execute-help', bounded(45)).decode()
        if not re.search(r'--id(?:[ =\[]|\b)', help_text) or not re.search(r'--rawOutput\b', help_text):
            raise RuntimeError('Installed execute help does not verify both --id and --rawOutput; no bridge/model launch.')
        save(evidence / 'execute-command-preflight.json', dict(observedHelpSha256=sha(help_text.encode()),
            requiredFlagsActuallyListed=['--id', '--rawOutput'], candidateCommand=cli + ['execute', '--id=' + source['id'], '--rawOutput'],
            rawOutputShape='Must be verified from actual runData; never inferred from help or exit code.'))
        catalog_body, catalog_headers = evidence / 'catalog-response.bin', evidence / 'catalog-headers.txt'
        status = command(['curl', '--silent', '--show-error', '--noproxy', '*', '--proto', '=https',
            '--max-time', '25', '--max-redirs', '0', '--max-filesize', '2097152',
            '--dump-header', str(catalog_headers), '--output', str(catalog_body),
            '--write-out', '%{http_code}', CATALOG_URL], ROOT, env, evidence, 'catalog', bounded(30)).decode().strip()
        assert status == '200'
        catalog = json.loads(catalog_body.read_bytes())
        assert isinstance(catalog, list)
        models = [entry for entry in catalog if isinstance(entry, dict) and entry.get('name') == 'openai-fast']
        assert len(models) == 1 and models[0].get('tier') == 'anonymous'
        save(evidence / 'verified-source-ids.json', dict(verifiedAtUtc=now(), sourceHead=SOURCE_HEAD,
            sourceSha256=SOURCE_SHA256, catalog=dict(url=CATALOG_URL, status=200, sha256=sha(catalog_body.read_bytes()),
                headersSha256=sha(catalog_headers.read_bytes()), selectedEntry=models[0]),
            providerEndpoint=PROVIDER_URL, policies=['https://enter.pollinations.ai/privacy', 'https://enter.pollinations.ai/terms'],
            disclosure=DISCLOSURE, inferenceProbeRepeated=False))
        adapter = WORK / 'anthropic_openai_bridge.py'
        adapter_source = adapter.read_text()
        assert '--stop-file' in adapter_source
        # Reduce the reviewed bridge's runtime call budget from 16 to 1, without modifying its source.
        wrapper = '''import importlib.util, sys
path = sys.argv[1]
spec = importlib.util.spec_from_file_location("one_call_anonymous_bridge", path)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
assert module.MAX_CALLS == 16 and module.CALL_SECONDS == 180.0
assert module.MIN_GAP_SECONDS >= 40.0 and module.LIFETIME_SECONDS == 1200.0
module.MAX_CALLS = 1
sys.argv = [path] + sys.argv[2:]
module.main()
'''
        (evidence / 'single-call-bridge-wrapper.py').write_text(wrapper)
        handles = [(evidence / name).open('xb') for name in ('bridge-stdout.txt', 'bridge-stderr.txt')]
        bridge = subprocess.Popen([sys.executable, str(evidence / 'single-call-bridge-wrapper.py'), str(adapter),
            '--evidence-dir', str(stop_file.parent), '--source-ids-file', str(evidence / 'verified-source-ids.json'),
            '--stop-file', str(stop_file)], cwd=ROOT, env=bridge_env, stdin=subprocess.DEVNULL,
            stdout=handles[0], stderr=handles[1], start_new_session=True)
        startup = time.monotonic() + 20
        session = None
        while time.monotonic() < startup:
            if (stop_file.parent / 'session.json').exists():
                try:
                    candidate = json.loads((stop_file.parent / 'session.json').read_bytes())
                    if candidate.get('listenHost') == '127.0.0.1' and isinstance(candidate.get('listenPort'), int):
                        session = candidate
                        break
                except (OSError, ValueError):
                    pass
            if bridge.poll() is not None:
                raise RuntimeError('Bridge exited before readiness; inspect its exact stderr.')
            time.sleep(0.1)
        if not session:
            raise RuntimeError('Bridge startup timed out; no engine execution.')
        sink = CaptureServer(evidence)
        sink_thread = threading.Thread(target=sink.serve_forever, kwargs={'poll_interval': 0.1}, daemon=True)
        sink_thread.start()
        sink_url = 'http://127.0.0.1:' + str(sink.server_port) + sink.route
        env['WEEKLY_SUMMARY_DISCORD_WEBHOOK_URL'] = sink_url
        variant = json.loads(source_bytes)
        index = next(i for i, node in enumerate(variant['nodes']) if node['name'] == 'Generate Claude Summary')
        original_url = variant['nodes'][index]['parameters']['url']
        assert original_url == 'https://api.anthropic.com/v1/messages'
        model_url = 'http://127.0.0.1:' + str(session['listenPort']) + '/v1/messages'
        variant['nodes'][index]['parameters']['url'] = model_url
        reverse = json.loads(json.dumps(variant))
        reverse['nodes'][index]['parameters']['url'] = original_url
        assert reverse == source, 'Only one disposable URL substitution is authorized.'
        variant_bytes = (json.dumps(variant, indent=2) + '\n').encode()
        (evidence / 'disposable-variant-workflow.json').write_bytes(variant_bytes)
        save(evidence / 'variant-diff.json', dict(originalSha256=sha(source_bytes), variantSha256=sha(variant_bytes),
            changes=[dict(op='replace', path='/nodes/' + str(index) + '/parameters/url', old=original_url, value=model_url)],
            allOtherSourceValuesEqual=True, existingEnvironmentConfiguration=dict(GITHUB_REPO_OWNER='taherdhanera',
                GITHUB_REPO_NAME='claude-builders-bounty', GITHUB_TOKEN='', SUMMARY_LANGUAGE='EN',
                ANTHROPIC_API_KEY='nonsecret dummy for local adapter only', WEEKLY_SUMMARY_DISCORD_WEBHOOK_URL=sink_url),
            originalGitHubReadRetryPolicyPreserved=True, modelRetryEnabled=False,
            runtimeBridgeCallBudgetReducedTo=1, disclosure=DISCLOSURE))
        command(cli + ['import:workflow', '--input=' + str(evidence / 'disposable-variant-workflow.json')],
                ROOT, env, evidence, 'variant-import', bounded(60))
        exported = evidence / 'variant-import-export.json'
        command(cli + ['export:workflow', '--id=' + source['id'], '--output=' + str(exported), '--pretty'],
                ROOT, env, evidence, 'variant-export', bounded(60))
        restored = json.loads(exported.read_bytes())
        assert isinstance(restored, list) and len(restored) == 1
        for field in ('id', 'name', 'nodes', 'connections', 'settings'):
            assert restored[0].get(field) == variant.get(field), 'Round trip changed ' + field
        assert restored[0].get('active') is False and restored[0].get('activeVersionId') is None
        assert time.monotonic() + 380 < overall_deadline, 'Do not start an incomplete engine budget.'
        save(evidence / 'engine-execution-intent.json', dict(atUtc=now(), sourceHead=SOURCE_HEAD,
            sourceSha256=SOURCE_SHA256, variantSha256=sha(variant_bytes), workflowId=source['id'],
            n8nVersion=version, nodeVersion=node_version, adapterSha256=sha(adapter.read_bytes()),
            modelRequestsMaximum=1, providerCallTimeoutSeconds=180, engineChildDeadlineSeconds=360,
            scheduleActive=False, modelRetry=False, sinkMaximumRequests=1, disclosure=DISCLOSURE))
        result['engineExecuted'] = True
        engine_stdout = command(cli + ['execute', '--id=' + source['id'], '--rawOutput'],
                                ROOT, env, evidence, 'actual-engine-execute', 360)
        data = raw_engine_data(engine_stdout)
        save(evidence / 'extracted-actual-engine-data.json', data)
        assert not data['resultData'].get('error')
        runs = data['resultData']['runData']
        expected_names = {node['name'] for node in variant['nodes']}
        assert set(runs) == expected_names, 'Actual runData must contain all nine exact nodes.'
        for name in expected_names:
            assert runs[name] and all(entry.get('executionStatus') == 'success' and not entry.get('error') for entry in runs[name]), name
        prompt_output = first_json(runs, 'Build Claude Prompt')
        model_output = first_json(runs, 'Generate Claude Summary')
        prepared = first_json(runs, 'Prepare Discord Message')
        assert any(part.get('type') == 'text' and part.get('text', '').strip() for part in model_output.get('content', []))
        assert sink.attempts == 1 and not sink.failure and sink.capture is not None
        assert sink.capture['payload'] == {'content': prepared['message']}
        exchange_path = stop_file.parent / 'round-01/exchange.json'
        exchange = json.loads(exchange_path.read_bytes())
        assert exchange.get('translationVerified') is True and exchange.get('providerComplete') is True
        assert 200 <= exchange.get('providerStatus', 0) < 300 and not exchange.get('adapterError')
        assert len(list(stop_file.parent.glob('round-*'))) == 1
        original_request = json.loads((stop_file.parent / 'round-01/client-request.json').read_bytes())
        actual_response = json.loads((stop_file.parent / 'round-01/anthropic-response.json').read_bytes())
        assert original_request['messages'] == [{'role': 'user', 'content': prompt_output['prompt']}]
        assert actual_response == model_output
        result.update(integrationFlowVerified=True, expectedNodeNames=sorted(expected_names),
            nodeExecutionStatuses={name: [entry['executionStatus'] for entry in runs[name]] for name in sorted(expected_names)},
            modelRequestCount=1, localSinkRequestCount=1, localSinkMatchesPreparedEngineOutput=True,
            providerActualModel=json.loads((stop_file.parent / 'round-01/provider-response.bin').read_bytes()).get('model'),
            semanticContentReview='pending; no automatic factual-summary or acceptance claim')
    except Exception as error:
        result.update(error=type(error).__name__ + ': ' + str(error), noRetry=True,
                      ambiguousDoNotRetry=result['engineExecuted'])
    finally:
        if bridge is not None and stop_file.parent.is_dir() and not stop_file.exists():
            save(stop_file, dict(atUtc=now(), reason='one_engine_attempt_terminal', noRetry=True))
            try:
                bridge.wait(timeout=5)
            except subprocess.TimeoutExpired:
                result['bridgeForcedCleanupRequired'] = True
        try:
            stop_group(bridge)
        except Exception as error:
            result['cleanupError'] = str(error)
        for handle in handles:
            handle.close()
        if sink is not None:
            if sink_thread is not None and sink_thread.is_alive():
                sink.shutdown()
            sink.server_close()
            if sink_thread:
                sink_thread.join(timeout=2)
            result.update(sinkObservedAttempts=sink.attempts, sinkFailure=sink.failure)
        try:
            result['originalCanonicalSourceHashUnchanged'] = sha(git('show', SOURCE_HEAD + ':' + SOURCE_PATH)) == SOURCE_SHA256
            result['sourceWorkingFileAfterSha256'] = sha((ROOT / SOURCE_PATH).read_bytes())
            result['originalSourceHashUnchanged'] = (result['originalCanonicalSourceHashUnchanged'] and
                source_working_sha is not None and result['sourceWorkingFileAfterSha256'] == source_working_sha)
            databases = list((private / 'data').rglob('database.sqlite'))
            if len(databases) == 1:
                with sqlite3.connect(databases[0].resolve().as_uri() + '?mode=ro', uri=True) as database:
                    database.row_factory = sqlite3.Row
                    tables = {row[0] for row in database.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                    observed = {}
                    for table in ('workflow_entity', 'execution_entity', 'execution_data', 'credentials_entity'):
                        if table in tables:
                            # Fresh isolated DB only; never export encryption/config files or credentials.
                            if table == 'credentials_entity':
                                observed['credentialsCount'] = database.execute('SELECT COUNT(*) FROM credentials_entity').fetchone()[0]
                            else:
                                observed[table] = [dict(row) for row in database.execute('SELECT * FROM ' + table)]
                    save(evidence / 'actual-isolated-database-rows.json', observed)
                    if observed.get('credentialsCount', 0) != 0:
                        result.update(integrationFlowVerified=False, unexpectedCredentialRows=True)
        except Exception as error:
            result['databaseOrSourceObservationError'] = str(error)
        result['completedAtUtc'] = now()
        save(evidence / 'result.json', result)
        manifest = {path.relative_to(evidence).as_posix(): dict(size=path.stat().st_size, sha256=sha(path.read_bytes()))
                    for path in sorted(evidence.rglob('*')) if path.is_file() and not path.is_symlink()}
        save(evidence / 'manifest.json', dict(createdAtUtc=now(), files=manifest, disclosure=DISCLOSURE))
    print(json.dumps(dict(engineExecuted=result['engineExecuted'], integrationFlowVerified=result['integrationFlowVerified'],
        actualAnthropicExecution=False, actualDiscordDelivery=False, receivedCashVerified=False, evidence=str(evidence))), flush=True)
    return 0 if result['integrationFlowVerified'] and result.get('originalSourceHashUnchanged') and not result.get('cleanupError') else 1


if __name__ == '__main__':
    raise SystemExit(main())
