"""One bounded free Linux CLI attempt against pinned native local Ollama.

Preparation only until root reviews and executes the isolated public workflow.
Real inference, a complete CLI session, semantic acceptance, and cash are separate.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import http.client
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import uuid

WORK = Path(__file__).resolve().parent
ROOT = WORK.parents[1]
SOURCE_HEAD = '26994b38341d36692b81291d689b0e3adad0cff2'
SOURCE_TEMPLATE = 'templates/nextjs-sqlite-saas/CLAUDE.md'
SOURCE_PROTOCOL = 'templates/nextjs-sqlite-saas/verification/claude-code-greenfield-smoke.md'
TEMPLATE_SHA256 = '252b4d86c2d6c432fe0c92ec90c7c249495dfa2ab5ff29c341ba7894221b7261'
BRANCH = 'refs/heads/proof/claude2284-ollama9b-manifest-20261021'
CLI_VERSION = '2.1.296'
CNA_VERSION = '15.5.28'
OLLAMA_VERSION = '0.40.6'
ARCHIVE_URL = 'https://github.com/ollama/ollama/releases/download/v0.40.6/ollama-linux-amd64.tar.zst'
ARCHIVE_SHA256 = 'c164ab8b1b28e2a247c29719b8e404c423c5b83ae64c3ab4e59d50c7ff7fc5e0'
MODEL = 'qwen3.5:9b-q4_K_M'
MODEL_DIGEST = '56671c2ab9385f9cfcb404638e32cd62d88e3501d44822208363c010179a3c90'
MODEL_MANIFEST_URL = 'https://registry.ollama.ai/v2/library/qwen3.5/manifests/9b-q4_K_M'
MODEL_BYTES = 6_550_813_952  # Published text weights + projector; actual pulled tag size is checked below.
CONTEXT = 65536
CLI_SECONDS = 1800
WHOLE_SECONDS = 2520  # 42 minutes leaves three minutes of the 45-minute job for exact evidence emission.
GIB = 1024 ** 3
DISCLOSURE = ('Official Claude Code 2.1.296 with pinned local Qwen3.5 9B through Ollama native '
    'Anthropic compatibility. The loopback recorder forwards application bytes unchanged. '
    'No Anthropic model or Anthropic server safety classifier is implemented. Supplemental '
    'execution evidence only; semantic acceptance, sponsor approval, payout eligibility, and cash are unverified.')
SOURCES = [
    'https://ollama.com/library/qwen3.5:9b-q4_K_M',
    'https://registry.ollama.ai/v2/library/qwen3.5/manifests/9b-q4_K_M',
    'https://github.com/ollama/ollama/releases/tag/v0.40.6',
    'https://github.com/ollama/ollama/releases/expanded_assets/v0.40.6',
    'https://docs.ollama.com/integrations/claude-code',
    'https://docs.ollama.com/api/anthropic-compatibility',
    'https://docs.ollama.com/context-length',
    'https://docs.ollama.com/faq',
]


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def write_json(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=True)
        stream.write('\n')


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def parse_pinned_registry_manifest(raw):
    require(digest(raw) == MODEL_DIGEST, 'Official registry manifest SHA256 differs from the pinned model digest; no load or fallback.')
    manifest = json.loads(raw)
    require(isinstance(manifest, dict) and manifest.get('schemaVersion') == 2,
            'Pinned registry manifest is not a supported schemaVersion 2 object.')
    require(isinstance(manifest.get('config'), dict) and isinstance(manifest.get('layers'), list) and manifest['layers'],
            'Pinned registry manifest is missing config or nonempty layers.')
    seen = set()
    for layer in [manifest['config'], *manifest['layers']]:
        require(isinstance(layer, dict), 'Pinned manifest contains a non-object layer descriptor.')
        value = layer.get('digest')
        require(isinstance(value, str) and value.startswith('sha256:') and len(value) == 71
                and all(char in '0123456789abcdef' for char in value[7:]),
                'Pinned manifest contains an invalid or non-SHA256 blob digest.')
        require(value not in seen, 'Pinned manifest repeats a blob descriptor unexpectedly.')
        seen.add(value)
        require(type(layer.get('size')) is int and layer['size'] > 0, 'Pinned manifest contains an invalid blob size.')
    return manifest


def inspect_local_manifests(model_store, authority):
    """Bounded diagnostic only; local filenames/serialization never establish identity."""
    base = model_store / 'manifests'
    result = dict(authoritative=False, authority='exact pinned official registry response + API/tags + installed blob hashes',
                  relativeBase='manifests', baseExists=base.exists(), maxDirectories=100, maxFiles=20,
                  maxReadBytesPerFile=1_048_576, directoriesObserved=0, files=[], truncated=False)
    if not base.is_dir() or base.is_symlink():
        result['baseIsSymlink'] = base.is_symlink()
        return result
    try:
        for directory, names, files in os.walk(base, followlinks=False):
            result['directoriesObserved'] += 1
            if result['directoriesObserved'] > result['maxDirectories']:
                result['truncated'] = True
                break
            names[:] = sorted(name for name in names if not (Path(directory) / name).is_symlink())
            for name in sorted(files):
                if len(result['files']) >= result['maxFiles']:
                    result['truncated'] = True
                    return result
                path = Path(directory) / name
                item = dict(relativePath=path.relative_to(model_store).as_posix(), isSymlink=path.is_symlink())
                if not item['isSymlink'] and path.is_file():
                    item['size'] = path.stat().st_size
                    if item['size'] <= result['maxReadBytesPerFile']:
                        raw = path.read_bytes()
                        item.update(sha256=digest(raw), exactRegistryBytesMatch=digest(raw) == MODEL_DIGEST)
                        try:
                            item['semanticRegistryJsonMatch'] = json.loads(raw) == authority
                        except (ValueError, UnicodeError):
                            item['semanticRegistryJsonMatch'] = False
                    else:
                        item['contentReadSkipped'] = 'diagnostic size bound'
                result['files'].append(item)
    except OSError as error:
        result['diagnosticError'] = type(error).__name__ + ': ' + str(error)
    return result


def verify_installed_blobs(model_store, manifest, receipt_path):
    blobs = model_store / 'blobs'
    require(blobs.is_dir() and not blobs.is_symlink(), 'Owned model store has no regular blobs directory; no model load.')
    checks = []
    try:
        for layer in [manifest['config'], *manifest['layers']]:
            expected = layer['digest']
            blob = blobs / expected.replace(':', '-')
            item = dict(digest=expected, expectedSize=layer['size'], relativePath=blob.relative_to(model_store).as_posix(),
                        exists=blob.exists(), isSymlink=blob.is_symlink(), matched=False)
            checks.append(item)
            require(blob.is_file() and not blob.is_symlink() and blob.resolve().parent == blobs.resolve(),
                    'Pinned installed blob is missing, nonregular, or outside the owned store: ' + expected)
            item['actualSize'] = blob.stat().st_size
            require(item['actualSize'] == layer['size'], 'Pinned installed blob byte count differs: ' + expected)
            item['actualSha256'] = file_digest(blob)
            item['matched'] = item['actualSha256'] == expected[7:]
            require(item['matched'], 'Pinned installed blob SHA256 differs: ' + expected)
    finally:
        write_json(receipt_path, dict(authority='pinned official registry manifest', expectedManifestSha256=MODEL_DIGEST,
            checkedAtUtc=now(), expectedBlobCount=1 + len(manifest['layers']), checkedBlobCount=len(checks),
            allMatched=len(checks) == 1 + len(manifest['layers']) and all(item['matched'] for item in checks), blobs=checks))
    return checks


def evidence_path():
    run_id, attempt = os.environ.get('GITHUB_RUN_ID', ''), os.environ.get('GITHUB_RUN_ATTEMPT', '')
    if not run_id.isdecimal() or not attempt.isdecimal():
        raise RuntimeError('An actual GitHub run identity is required.')
    return Path(os.environ['RUNNER_TEMP']) / ('native-ollama-2284-evidence-' + run_id + '-' + attempt)


def clean_environment(home):
    # No user/cloud/GitHub/npm credentials, inherited proxy, or user config is copied.
    env = {key: value for key, value in os.environ.items() if key in {'PATH', 'LANG', 'LC_ALL'}}
    home.mkdir(mode=0o700, parents=True, exist_ok=False)
    temporary = home / 'tmp'
    temporary.mkdir(mode=0o700)
    env.update(HOME=str(home), XDG_CONFIG_HOME=str(home / '.config'), XDG_CACHE_HOME=str(home / '.cache'),
        TMPDIR=str(temporary), CI='1', NO_COLOR='1', GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null',
        GIT_TERMINAL_PROMPT='0', NPM_CONFIG_USERCONFIG='/dev/null', NPM_CONFIG_AUDIT='false',
        NPM_CONFIG_FUND='false', NPM_CONFIG_REGISTRY='https://registry.npmjs.org/', NPM_CONFIG_FETCH_RETRIES='0',
        NEXT_TELEMETRY_DISABLED='1')
    return env


def stop_group(process):
    if process is None:
        return
    # Only groups explicitly created by this launcher are eligible for cleanup.
    for sig, grace in ((signal.SIGTERM, 3), (signal.SIGKILL, 3)):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            break
        try:
            process.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            continue
    if process.poll() is None:
        raise RuntimeError('Exact owned child did not exit after bounded cleanup.')


def run_command(args, cwd, env, directory, name, seconds):
    stdout_path, stderr_path = directory / (name + '-stdout.txt'), directory / (name + '-stderr.txt')
    record = dict(command=[str(arg) for arg in args], cwd=str(cwd), startedAtUtc=now(), timeoutSeconds=seconds)
    process = None
    try:
        with stdout_path.open('xb') as stdout, stderr_path.open('xb') as stderr:
            process = subprocess.Popen(args, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                stdout=stdout, stderr=stderr, start_new_session=True)
            record['pid'] = process.pid
            try:
                record['exitCode'] = process.wait(timeout=seconds)
            except subprocess.TimeoutExpired:
                record['timedOut'] = True
    finally:
        stop_group(process)
        record.update(completedAtUtc=now(), stdoutSha256=file_digest(stdout_path) if stdout_path.exists() else None,
                      stderrSha256=file_digest(stderr_path) if stderr_path.exists() else None)
        write_json(directory / (name + '-process.json'), record)
    if record.get('timedOut') or record.get('exitCode') != 0:
        raise RuntimeError(name + ' failed or timed out; no retry/fallback.')
    return stdout_path.read_bytes()


def resources(path):
    memory = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        key, value = line.split(':', 1)
        if key in ('MemTotal', 'MemAvailable', 'SwapTotal', 'SwapFree'):
            memory[key + 'Bytes'] = int(value.split()[0]) * 1024
    paging = {}
    for line in Path('/proc/vmstat').read_text().splitlines():
        key, value = line.split()
        if key in ('pswpin', 'pswpout'):
            paging[key] = int(value)
    return dict(atUtc=now(), memory=memory, pagingPages=paging, pageBytes=os.sysconf('SC_PAGE_SIZE'),
                diskFreeBytes=shutil.disk_usage(path).free, cpuCount=os.cpu_count(), loadAverage=os.getloadavg())


def gate_resources(sample, disk_needed, available_needed=11 * GIB):
    if sample['memory']['MemTotalBytes'] < 15 * GIB or sample['cpuCount'] < 4:
        raise RuntimeError('Measured runner is smaller than the intended 16-GB/4-CPU runner.')
    if sample['memory']['MemAvailableBytes'] < available_needed:
        raise RuntimeError('Measured available RAM is insufficient; no model load/pull retry.')
    if sample['diskFreeBytes'] < disk_needed:
        raise RuntimeError('Measured free disk cannot cover the next stage plus evidence reserve.')


class ResourceWatch:
    def __init__(self, directory, private, server):
        self.directory, self.private, self.server = directory, private, server
        self.stop = threading.Event()
        self.failed = None
        self.baseline = resources(private)
        self.thread = threading.Thread(target=self.monitor, name='owned-resource-watch', daemon=True)

    def monitor(self):
        try:
            with (self.directory / 'model-resource-samples.jsonl').open('x', encoding='utf-8') as stream:
                while not self.stop.is_set():
                    sample = resources(self.private)
                    stream.write(json.dumps(sample) + '\n')
                    stream.flush()
                    moved_pages = sum(max(0, sample['pagingPages'][key] - self.baseline['pagingPages'][key])
                                      for key in ('pswpin', 'pswpout'))
                    if sample['memory']['MemAvailableBytes'] < 768 * 1024 ** 2 or moved_pages * sample['pageBytes'] > 64 * 1024 ** 2:
                        self.failed = dict(atUtc=now(), reason='RAM floor or material paging reached', sample=sample)
                        break
                    self.stop.wait(5)
        except Exception as error:
            self.failed = dict(atUtc=now(), reason='Resource monitoring unavailable', error=type(error).__name__ + ': ' + str(error))
        if self.failed:
            try:
                write_json(self.directory / 'resource-stop.json', self.failed)
            finally:
                # Stop only this launcher's model server and its own runner group.
                try:
                    os.killpg(self.server.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass

    def start(self):
        self.thread.start()

    def close(self):
        self.stop.set()
        self.thread.join(timeout=6)


def api(port, path, directory, name, body=None, seconds=30):
    # Direct loopback HTTPConnection does not consult proxies or external hosts.
    raw = None if body is None else json.dumps(body, separators=(',', ':')).encode()
    if raw is not None:
        (directory / (name + '-request.bin')).write_bytes(raw)
    record = dict(startedAtUtc=now(), host='127.0.0.1', port=port, path=path,
                  method='GET' if raw is None else 'POST', requestSha256=digest(raw) if raw is not None else None)
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=seconds)
    connected_socket = None
    def abort_socket():
        for current in (connected_socket, getattr(connection, 'sock', None)):
            if current is not None:
                try:
                    current.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                current.close()
    timer = threading.Timer(seconds, abort_socket)
    timer.daemon = True
    timer.start()
    try:
        connection.request(record['method'], path, body=raw, headers={} if raw is None else {'Content-Type': 'application/json'})
        connected_socket = connection.sock
        response = connection.getresponse()
        record.update(status=response.status, responseHeaders=response.getheaders())
        payload = response.read()
        (directory / (name + '-response.bin')).write_bytes(payload)
        record.update(responseSha256=digest(payload), responseBytes=len(payload))
        if response.status != 200:
            raise RuntimeError('Local metadata/load HTTP error; no retry.')
        return json.loads(payload)
    except Exception as error:
        record['error'] = type(error).__name__ + ': ' + str(error)
        raise
    finally:
        timer.cancel()
        connection.close()
        record['completedAtUtc'] = now()
        write_json(directory / (name + '-receipt.json'), record)


def fixture_files(fixture):
    result = {}
    for path in sorted(fixture.rglob('*')):
        relative = path.relative_to(fixture)
        if '.git' in relative.parts:
            continue
        if path.is_symlink():
            raise RuntimeError('Unexpected fixture symlink: ' + str(relative))
        if path.is_file():
            result[relative.as_posix()] = file_digest(path)
    return result


def parse_stream(text):
    result_events, calls, results, invalid, shapes = [], [], [], [], []
    last_type = None
    for number, line in enumerate(text.splitlines(), 1):
        try:
            event = json.loads(line)
        except ValueError:
            invalid.append(number)
            continue
        if not isinstance(event, dict):
            shapes.append(dict(line=number, type=type(event).__name__))
            continue
        last_type = event.get('type')
        if last_type == 'result':
            result_events.append(event)
        message = event.get('message')
        if message is None or isinstance(message, str):
            continue  # Actual CLI system notices can be strings; preserve original JSONL regardless.
        if not isinstance(message, dict):
            shapes.append(dict(line=number, field='message', type=type(message).__name__))
            continue
        content = message.get('content')
        if content is None or isinstance(content, str):
            continue
        if not isinstance(content, list):
            shapes.append(dict(line=number, field='content', type=type(content).__name__))
            continue
        for block in content:
            if not isinstance(block, dict):
                shapes.append(dict(line=number, field='content_block', type=type(block).__name__))
            elif block.get('type') == 'tool_use':
                calls.append({**block, 'streamLine': number})
            elif block.get('type') == 'tool_result':
                results.append({**block, 'streamLine': number})
    complete = (len(result_events) == 1 and result_events[0].get('subtype') == 'success'
                and result_events[0].get('is_error') is False and result_events[0].get('stop_reason') == 'end_turn'
                and last_type == 'result' and not invalid and not shapes)
    return dict(resultEvents=result_events, toolCalls=calls, toolResults=results,
                invalidJsonLines=invalid, shapeIssues=shapes, nonErrorCompleteResultObserved=complete,
                semanticAcceptance='unscored; independent rubric review required')


def emit_only(directory):
    import base64
    if not directory.is_dir():
        raise RuntimeError('No evidence directory exists; no completion claim.')
    paths = sorted(path for path in directory.rglob('*') if path.is_file() and not path.is_symlink())
    token = 'evidence-' + uuid.uuid4().hex
    while any(token.encode() in path.read_bytes() for path in paths):
        token = 'evidence-' + uuid.uuid4().hex
    print('::stop-commands::' + token, flush=True)
    try:
        for path in paths:
            data = path.read_bytes()
            print('BEGIN_EXACT_EVIDENCE ' + json.dumps(dict(path=path.relative_to(directory).as_posix(),
                size=len(data), sha256=digest(data), encoding='base64')), flush=True)
            encoded = base64.b64encode(data).decode('ascii')
            for offset in range(0, len(encoded), 8192):
                print(encoded[offset:offset + 8192], flush=True)
            print('END_EXACT_EVIDENCE', flush=True)
    finally:
        print('::' + token + '::', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--emit-only', action='store_true')
    args = parser.parse_args()
    evidence = evidence_path()
    if args.emit_only:
        emit_only(evidence)
        return 0
    require(sys.platform.startswith('linux') and os.environ.get('GITHUB_ACTIONS') == 'true', 'This attempt requires the isolated Linux GitHub runner.')
    require(os.environ.get('GITHUB_REPOSITORY') == 'taherdhanera/claude-builders-bounty', 'Unexpected repository; only the owned public fork is authorized.')
    require(os.environ.get('GITHUB_REF') == BRANCH and os.environ.get('GITHUB_RUN_ATTEMPT') == '1', 'Unexpected proof branch or repeated workflow attempt.')
    evidence.mkdir(mode=0o700, parents=False, exist_ok=False)
    private = Path(os.environ['RUNNER_TEMP']) / ('native-ollama-2284-private-' + os.environ['GITHUB_RUN_ID'])
    private.mkdir(mode=0o700, exist_ok=False)
    setup_env = clean_environment(private / 'setup-home')
    cli_env = clean_environment(private / 'cli-home')
    server_env = clean_environment(private / 'ollama-home')
    recorder_env = clean_environment(private / 'recorder-home')
    fixture_parent = private / 'fixture'
    fixture_parent.mkdir(mode=0o700)
    fixture = fixture_parent / 'acme-saas'
    runtime, ollama_root = private / 'official-cli', private / 'ollama-runtime'
    result = dict(startedAtUtc=now(), disclosure=DISCLOSURE, cliExecuted=False, modelPulled=False,
        successfulAcceptanceVerified=False, semanticAssessment='pending independent review',
        inferenceProbeRepeated=False, ambiguousDoNotRetry=False, receivedCashVerified=False)
    deadline = time.monotonic() + WHOLE_SECONDS
    server = recorder = client = watch = None
    handles = []
    before = None
    stop_file = evidence / 'native-http/operator-stop.json'

    def bounded(seconds, reserve=0):
        remaining = int(deadline - time.monotonic()) - reserve
        if remaining < 1:
            raise RuntimeError('Absolute stage budget expired; no further attempt.')
        return min(seconds, remaining)

    def setup_seconds(seconds):
        return bounded(seconds, CLI_SECONDS + 30)

    def git(*arguments, cwd=ROOT):
        return subprocess.check_output(['git', *arguments], cwd=cwd, env=setup_env, timeout=15)

    try:
        parents = git('rev-list', '--parents', '-n', '1', 'HEAD').decode().split()
        require(len(parents) == 2 and parents[1] == SOURCE_HEAD, 'Proof must be a direct child of the exact PR head.')
        require(git('status', '--porcelain=v1').decode() == '', 'Proof checkout must be clean before setup.')
        changed = git('diff', '--name-only', SOURCE_HEAD, 'HEAD').decode().splitlines()
        require(changed and all(path.startswith('scripts/free-ollama-2284/') or path == '.github/workflows/claude2284-ollama9b-manifest-20261021.yml' for path in changed),
                'Proof diff must contain only the new native scripts and matching manifest-revision workflow.')
        template, protocol_bytes = git('show', SOURCE_HEAD + ':' + SOURCE_TEMPLATE), git('show', SOURCE_HEAD + ':' + SOURCE_PROTOCOL)
        require(digest(template) == TEMPLATE_SHA256, 'Canonical current CLAUDE.md SHA256 differs; no fixture or inference.')
        section = protocol_bytes.decode().split('## Exact first prompt\n', 1)[1].split('\n## ', 1)[0].strip()
        prompt = '\n'.join(line[2:] if line.startswith('> ') else line for line in section.splitlines())
        require(prompt and not prompt.startswith('>'), 'Exact current source prompt could not be extracted unambiguously.')
        (evidence / 'exact-first-prompt.txt').write_bytes(prompt.encode())
        (evidence / 'exact-source-protocol.md').write_bytes(protocol_bytes)
        (evidence / 'exact-source-CLAUDE.md').write_bytes(template)
        write_json(evidence / 'source-identity.json', dict(sourceHead=SOURCE_HEAD, proofCommit=parents[0], proofParent=parents[1],
            templateSha256=digest(template), protocolSha256=digest(protocol_bytes), promptSha256=digest(prompt.encode()),
            scripts={path.name: file_digest(path) for path in WORK.glob('*') if path.is_file()},
            runUrl='https://github.com/taherdhanera/claude-builders-bounty/actions/runs/' + os.environ['GITHUB_RUN_ID'],
            runAttempt=1, model=MODEL, expectedModelDigest=MODEL_DIGEST, pinnedRuntimeSha256=ARCHIVE_SHA256,
            primarySourceUrls=SOURCES, sourcesVerifiedByParentBeforePreparation=True, disclosure=DISCLOSURE))
        sample = resources(private)
        write_json(evidence / 'resources-before-install.json', sample)
        gate_resources(sample, 12 * GIB)
        ollama_root.mkdir(mode=0o700)
        archive = private / 'ollama-linux-amd64.tar.zst'
        # One download; no curl retry, alternate host, credentials, or ambiguous restart.
        run_command(['curl', '--fail', '--silent', '--show-error', '--location', '--noproxy', '*', '--proto', '=https',
            '--proto-redir', '=https', '--max-time', str(setup_seconds(180)), '--max-redirs', '3',
            '--dump-header', str(evidence / 'ollama-archive-response-headers.txt'), '--output', str(archive), ARCHIVE_URL],
            ROOT, setup_env, evidence, 'ollama-archive-download', setup_seconds(185))
        actual_archive_sha = file_digest(archive)
        write_json(evidence / 'ollama-archive-integrity.json', dict(url=ARCHIVE_URL, size=archive.stat().st_size,
            expectedSha256=ARCHIVE_SHA256, observedSha256=actual_archive_sha, matched=actual_archive_sha == ARCHIVE_SHA256))
        require(actual_archive_sha == ARCHIVE_SHA256, 'Downloaded Ollama runtime archive SHA256 differs; no extraction or server start.')
        run_command(['tar', '--zstd', '-xf', str(archive), '-C', str(ollama_root)], ROOT, setup_env, evidence,
                    'ollama-archive-extract', setup_seconds(90))
        # Exact new task-owned verified archive only. Raw headers/hash remain in evidence.
        require(archive.parent == private and archive.name == 'ollama-linux-amd64.tar.zst', 'Archive cleanup target is not the exact new owned archive.')
        archive.unlink()
        ollama = ollama_root / 'bin/ollama'
        require(ollama.is_file() and os.access(ollama, os.X_OK), 'Verified archive did not produce an executable bin/ollama.')
        run_command(['npm', 'install', '--prefix', str(runtime), '--no-audit', '--no-fund',
            '@anthropic-ai/claude-code@' + CLI_VERSION], ROOT, setup_env, evidence, 'official-cli-install', setup_seconds(180))
        cli = runtime / 'node_modules/.bin/claude'
        cli_package = json.loads((runtime / 'node_modules/@anthropic-ai/claude-code/package.json').read_text())
        require(cli_package['version'] == CLI_VERSION, 'Installed official CLI package version differs from its pin.')
        run_command(['npx', '--yes', 'create-next-app@' + CNA_VERSION, 'acme-saas', '--ts', '--eslint', '--app',
            '--no-tailwind', '--use-npm', '--skip-install', '--disable-git', '--no-src-dir', '--import-alias', '@/*', '--yes'],
            fixture_parent, setup_env, evidence, 'fresh-starter-create', setup_seconds(180))
        require(fixture.is_dir() and not (fixture / 'node_modules').exists() and not (fixture / 'src').exists(), 'Generated starter is not the required fresh skip-install no-src fixture.')
        require(not (fixture / 'CLAUDE.md').exists(), 'Fresh starter unexpectedly already contains CLAUDE.md.')
        package = json.loads((fixture / 'package.json').read_text())
        require(package['dependencies']['next'] == CNA_VERSION, 'Fresh starter Next.js version differs from the current fixture pin.')
        (fixture / 'CLAUDE.md').write_bytes(template)
        git('init', '-q', cwd=fixture)
        git('add', '.', cwd=fixture)
        git('-c', 'user.name=Disposable Execution Proof', '-c', 'user.email=proof@localhost',
            'commit', '-qm', 'Disposable generated starter baseline', cwd=fixture)
        require(git('status', '--porcelain=v1', cwd=fixture).decode() == '', 'Disposable fixture baseline was not committed cleanly.')
        before = fixture_files(fixture)
        write_json(evidence / 'fixture-before.json', before)
        write_json(evidence / 'fixture-package.json', package)
        versions = dict(node=run_command(['node', '--version'], fixture, setup_env, evidence, 'node-version', setup_seconds(15)).decode().strip(),
            npm=run_command(['npm', '--version'], fixture, setup_env, evidence, 'npm-version', setup_seconds(15)).decode().strip(),
            claude=run_command([str(cli), '--version'], fixture, cli_env, evidence, 'claude-version', setup_seconds(15)).decode().strip(),
            claudePackageVersion=cli_package['version'], createNextAppVersion=CNA_VERSION,
            nextVersion=package['dependencies']['next'], dependenciesInstalled=False)
        require(versions['node'].startswith('v22.') and versions['claude'].startswith(CLI_VERSION), 'Actual Node.js/Claude CLI runtime versions differ from their pins.')

        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1', 0))
            port = reservation.getsockname()[1]
        model_store = private / 'ollama-models'
        model_store.mkdir(mode=0o700)
        server_env.update(OLLAMA_HOST='127.0.0.1:' + str(port), OLLAMA_MODELS=str(model_store),
            OLLAMA_NO_CLOUD='1', OLLAMA_CONTEXT_LENGTH=str(CONTEXT), OLLAMA_NUM_GPU='0',
            OLLAMA_NUM_PARALLEL='1', OLLAMA_MAX_LOADED_MODELS='1', OLLAMA_KEEP_ALIVE='35m',
            OLLAMA_MAX_QUEUE='1', CUDA_VISIBLE_DEVICES='-1', HIP_VISIBLE_DEVICES='-1', ROCR_VISIBLE_DEVICES='-1')
        for name in ('ollama-server-stdout.txt', 'ollama-server-stderr.txt', 'recorder-stdout.txt', 'recorder-stderr.txt',
                     'claude-output.jsonl', 'claude-stderr.txt'):
            handles.append((evidence / name).open('xb'))
        server = subprocess.Popen([str(ollama), 'serve'], cwd=private, env=server_env, stdin=subprocess.DEVNULL,
            stdout=handles[0], stderr=handles[1], start_new_session=True)
        write_json(evidence / 'ollama-server-intent.json', dict(startedAtUtc=now(), pid=server.pid,
            host='127.0.0.1', port=port, executableSha256=file_digest(ollama), settings={key: value for key, value in server_env.items()
            if key.startswith('OLLAMA_') or key in ('CUDA_VISIBLE_DEVICES', 'HIP_VISIBLE_DEVICES', 'ROCR_VISIBLE_DEVICES')},
            inheritedCredentials=False, noRestart=True))
        ready_deadline = time.monotonic() + setup_seconds(20)
        while True:
            if server.poll() is not None:
                raise RuntimeError('Owned Ollama server exited before readiness; no restart.')
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=0.5):
                    break
            except OSError:
                if time.monotonic() >= ready_deadline:
                    raise RuntimeError('Owned Ollama readiness deadline exceeded; no restart.')
                time.sleep(0.2)
        versions['ollamaServer'] = api(port, '/api/version', evidence, 'ollama-version', seconds=setup_seconds(15))
        require(versions['ollamaServer'].get('version') == OLLAMA_VERSION, 'Actual native Ollama server version differs from 0.40.6.')
        write_json(evidence / 'versions.json', versions)
        initial_tags = api(port, '/api/tags', evidence, 'ollama-tags-before-pull', seconds=setup_seconds(15))
        require(initial_tags.get('models') == [], 'The isolated model store must start empty.')
        sample = resources(private)
        write_json(evidence / 'resources-before-model-pull.json', sample)
        gate_resources(sample, MODEL_BYTES + 2 * GIB)
        run_command([str(ollama), 'pull', MODEL], private, server_env, evidence, 'ollama-model-pull', setup_seconds(480))
        result['modelPulled'] = True
        tags = api(port, '/api/tags', evidence, 'ollama-tags-after-pull', seconds=setup_seconds(15))
        matches = [item for item in tags.get('models', []) if item.get('name') == MODEL]
        require(len(tags.get('models', [])) == 1 and len(matches) == 1, 'Post-pull API/tags did not report exactly one pinned model.')
        pulled = matches[0]
        require(isinstance(pulled.get('digest'), str) and pulled['digest'].removeprefix('sha256:') == MODEL_DIGEST,
                'Post-pull API/tags model digest differs from the pinned registry digest; no alternate model.')
        require(type(pulled.get('size')) is int and MODEL_BYTES <= pulled['size'] <= MODEL_BYTES + 2_000_000,
                'Post-pull API/tags byte size is outside the pinned model range.')
        show = api(port, '/api/show', evidence, 'ollama-show', dict(model=MODEL, verbose=False), seconds=setup_seconds(30))
        require('tools' in show.get('capabilities', []), 'Actual pinned native model metadata does not advertise tools.')
        registry_body = evidence / 'official-registry-manifest-response.bin'
        registry_headers = evidence / 'official-registry-manifest-response-headers.txt'
        registry_status = run_command(['curl', '--fail', '--silent', '--show-error', '--noproxy', '*', '--proto', '=https',
            '--max-time', '25', '--max-redirs', '0', '--max-filesize', '1048576', '--dump-header', str(registry_headers),
            '--output', str(registry_body), '--write-out', '%{http_code}', MODEL_MANIFEST_URL],
            ROOT, setup_env, evidence, 'official-registry-manifest-fetch', setup_seconds(30)).decode().strip()
        registry_raw = registry_body.read_bytes()
        write_json(evidence / 'official-registry-manifest-integrity.json', dict(fetchedAtUtc=now(), url=MODEL_MANIFEST_URL,
            httpStatus=registry_status, responseBytes=len(registry_raw), observedSha256=digest(registry_raw),
            expectedSha256=MODEL_DIGEST, matched=registry_status == '200' and digest(registry_raw) == MODEL_DIGEST,
            headersSha256=file_digest(registry_headers), requestCount=1, retries=0))
        require(registry_status == '200', 'The one official registry manifest GET was not HTTP 200; no inference or retry.')
        manifest_body = parse_pinned_registry_manifest(registry_raw)
        write_json(evidence / 'local-manifest-layout-diagnostic.json', inspect_local_manifests(model_store, manifest_body))
        verify_installed_blobs(model_store, manifest_body, evidence / 'installed-model-layer-integrity.json')
        sample = resources(private)
        write_json(evidence / 'resources-before-model-load.json', sample)
        gate_resources(sample, 2 * GIB)
        watch = ResourceWatch(evidence, private, server)
        watch.start()
        # Explicit empty-prompt preload is disclosed separately, never counted as acceptance execution.
        preload = api(port, '/api/generate', evidence, 'ollama-empty-prompt-preload',
            dict(model=MODEL, prompt='', stream=False, keep_alive='35m', options=dict(num_ctx=CONTEXT, num_gpu=0, num_predict=0)),
            seconds=setup_seconds(180))
        require(preload.get('done') is True and preload.get('response', '') == '', 'Empty-prompt preload did not complete without generated text.')
        require(not watch.failed, 'Resource guard stopped the native preload; no CLI execution.')
        loaded = api(port, '/api/ps', evidence, 'ollama-loaded-before-cli', seconds=setup_seconds(15))
        loaded_models = loaded.get('models', [])
        require(len(loaded_models) == 1, 'Native /api/ps did not report exactly one loaded model after preload.')
        active = loaded_models[0]
        require(active.get('name') == MODEL and isinstance(active.get('digest'), str)
                and active['digest'].removeprefix('sha256:') == MODEL_DIGEST, 'Native loaded model identity differs from the pin.')
        require(active.get('context_length') == CONTEXT and active.get('size_vram') == 0,
                'Native model allocation is not the actual requested 65536 context with zero GPU VRAM.')
        require(type(active.get('size')) is int and active['size'] > 0, 'Native /api/ps did not report a valid actual model allocation size.')
        sample = resources(private)
        write_json(evidence / 'resources-after-model-load.json', sample)
        gate_resources(sample, 2 * GIB, available_needed=2 * GIB)
        result.update(modelDigest=pulled['digest'], actualLoadedContext=active['context_length'], actualSizeVram=active['size_vram'])

        guard_path = WORK / 'guard_fixture_paths.py'
        spec = importlib.util.spec_from_file_location('native_fixture_guard', guard_path)
        guard = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(guard)
        require(guard.check(dict(tool_name='Read', tool_input=dict(file_path=str(fixture / 'CLAUDE.md'))), fixture), 'Fixture hook rejected its authorized CLAUDE.md Read self-check.')
        require(guard.check(dict(tool_name='Grep', tool_input=dict(pattern='next')), fixture), 'Fixture hook rejected its authorized Grep self-check.')
        require(not guard.check(dict(tool_name='Read', tool_input=dict(file_path=str(ROOT / 'README.md'))), fixture), 'Fixture hook failed to reject an out-of-fixture Read.')
        require(not guard.check(dict(tool_name='Glob', tool_input=dict(pattern='../**')), fixture), 'Fixture hook failed to reject a Glob path escape.')
        require(not guard.check(dict(tool_name='Write', tool_input=dict(file_path=str(fixture / 'x'))), fixture), 'Fixture hook failed to reject a mutating Write.')
        hook = shlex.join([sys.executable, str(guard_path), '--root', str(fixture), '--log', str(evidence / 'tool-path-guard.jsonl')])
        # Match every tool attempt so plan writes and unknown names are explicitly denied as well.
        settings = dict(hooks=dict(PreToolUse=[dict(matcher='.*', hooks=[dict(type='command', command=hook, timeout=5)])]))
        write_json(evidence / 'cli-settings.json', settings)
        require(bounded(CLI_SECONDS + 20) == CLI_SECONDS + 20, 'Insufficient remaining absolute budget for a complete CLI session; no partial launch.')
        recorder = subprocess.Popen([sys.executable, '-B', str(WORK / 'native_http_recorder.py'), '--upstream-port', str(port),
            '--evidence-dir', str(evidence / 'native-http'), '--stop-file', str(stop_file)], cwd=ROOT, env=recorder_env,
            stdin=subprocess.DEVNULL, stdout=handles[2], stderr=handles[3], start_new_session=True)
        ready_deadline = time.monotonic() + 10
        session_path = evidence / 'native-http/session.json'
        while not session_path.exists():
            if recorder.poll() is not None or time.monotonic() >= ready_deadline:
                raise RuntimeError('Native recorder readiness failed; no model retry.')
            time.sleep(0.1)
        session = json.loads(session_path.read_bytes())
        require(session['listenHost'] == '127.0.0.1' and session['upstreamPort'] == port, 'Native recorder readiness identity differs from the exact owned loopback server.')
        cli_env.update(ANTHROPIC_BASE_URL='http://127.0.0.1:' + str(session['listenPort']), ANTHROPIC_AUTH_TOKEN='ollama',
            ANTHROPIC_API_KEY='', ANTHROPIC_MODEL=MODEL, ANTHROPIC_SMALL_FAST_MODEL=MODEL,
            ANTHROPIC_DEFAULT_HAIKU_MODEL=MODEL, ANTHROPIC_DEFAULT_SONNET_MODEL=MODEL, ANTHROPIC_DEFAULT_OPUS_MODEL=MODEL,
            CLAUDE_CODE_SUBAGENT_MODEL=MODEL, CLAUDE_CONFIG_DIR=str(private / 'cli-home/.claude'),
            DISABLE_AUTOUPDATER='1', DISABLE_TELEMETRY='1', DISABLE_ERROR_REPORTING='1',
            CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC='1', CLAUDE_CODE_MAX_RETRIES='0',
            CLAUDE_CODE_MAX_OUTPUT_TOKENS='4096', CLAUDE_CODE_MAX_CONTEXT_TOKENS=str(CONTEXT),
            MAX_THINKING_TOKENS='0', API_TIMEOUT_MS='1800000', API_FORCE_IDLE_TIMEOUT='0',
            CLAUDE_STREAM_FIRST_BYTE_TIMEOUT_MS='1800000', CLAUDE_STREAM_IDLE_TIMEOUT_MS='1800000',
            CLAUDE_BYTE_STREAM_IDLE_TIMEOUT_MS='1800000')
        command = [str(cli), '--restricted', '--permission-mode', 'plan', '--tools', 'Read,Glob,Grep',
            '--allowedTools', 'Read,Glob,Grep', '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}',
            '--settings', str(evidence / 'cli-settings.json'), '--setting-sources', '', '--session-id', str(uuid.uuid4()),
            '--max-turns', '10', '--effort', 'low', '--output-format', 'stream-json', '--verbose', '-p', prompt]
        write_json(evidence / 'live-cli-intent.json', dict(atUtc=now(), command=command, sourceHead=SOURCE_HEAD,
            templateSha256=digest(template), promptSha256=digest(prompt.encode()), model=MODEL,
            modelDigest=MODEL_DIGEST, nativeApi=True, protocolAdapter=False, recorderSha256=file_digest(WORK / 'native_http_recorder.py'),
            guardSha256=file_digest(guard_path), cliBudgetSeconds=CLI_SECONDS, launcherBudgetSeconds=WHOLE_SECONDS,
            maximumNativeCalls=16, requestedContext=CONTEXT, requestedMaxOutputTokens=4096, requestedCpuOnly=True,
            maxThinkingTokensZeroIsClientRequestOnly=True, anthropicServerClassifierImplemented=False, disclosure=DISCLOSURE))
        client = subprocess.Popen(command, cwd=fixture, env=cli_env, stdin=subprocess.DEVNULL,
            stdout=handles[4], stderr=handles[5], start_new_session=True)
        result.update(cliExecuted=True, cliStartedAtUtc=now(), cliPid=client.pid, serverPid=server.pid, recorderPid=recorder.pid)
        cli_deadline = time.monotonic() + CLI_SECONDS
        while client.poll() is None:
            if watch.failed or server.poll() is not None or time.monotonic() >= cli_deadline or time.monotonic() >= deadline:
                result.update(cliTimedOut=time.monotonic() >= cli_deadline, resourceStopped=bool(watch.failed), ambiguousDoNotRetry=True)
                break
            time.sleep(1)
        if client.poll() is not None:
            result['cliExitCode'] = client.returncode
        stop_group(client)
        write_json(stop_file, dict(atUtc=now(), reason='client_completed_or_deadline', noRetry=True))
        try:
            recorder.wait(timeout=5)
        except subprocess.TimeoutExpired:
            result['recorderForcedCleanupRequired'] = True
        if not watch.failed and server.poll() is None:
            api(port, '/api/ps', evidence, 'ollama-loaded-after-cli', seconds=bounded(15))
        result['processCompletedSuccessfully'] = result.get('cliExitCode') == 0
    except Exception as error:
        result.update(error=type(error).__name__ + ': ' + str(error), ambiguousDoNotRetry=result['cliExecuted'] or result['modelPulled'])
    finally:
        if recorder is not None and stop_file.parent.is_dir() and not stop_file.exists():
            write_json(stop_file, dict(atUtc=now(), reason='operator_cleanup', noRetry=True))
        if watch is not None:
            watch.close()
            result['resourceGuardFailure'] = watch.failed
        for process in (client, recorder, server):
            try:
                stop_group(process)
            except Exception as error:
                result.setdefault('cleanupErrors', []).append(str(error))
        for handle in handles:
            handle.close()
        if before is not None:
            try:
                after = fixture_files(fixture)
                write_json(evidence / 'fixture-after.json', after)
                result.update(fixtureUnchanged=before == after, fixtureGitStatus=git('status', '--porcelain=v1', cwd=fixture).decode())
            except Exception as error:
                result['fixtureVerificationError'] = str(error)
        if (evidence / 'claude-output.jsonl').exists():
            parsed = parse_stream((evidence / 'claude-output.jsonl').read_text(errors='replace'))
            write_json(evidence / 'cli-structural-observations.json', parsed)
            result['nonErrorCompleteResultObserved'] = parsed['nonErrorCompleteResultObserved']
        if (evidence / 'native-http').is_dir():
            receipts = [json.loads(path.read_bytes()) for path in sorted((evidence / 'native-http').glob('request-*-receipt.json'))]
            closed_path = evidence / 'native-http/closed.json'
            closed = json.loads(closed_path.read_bytes()) if closed_path.exists() else None
            result['nativeHttpEvidenceComplete'] = bool(receipts and closed and not closed.get('stopped')
                and closed.get('upstreamCalls') == len(receipts)
                and all(item.get('upstreamCallsMade') == 1 and item.get('status') == 200
                        and item.get('responseComplete') is True and not item.get('error') for item in receipts))
        result.update(completedAtUtc=now(), noAutomaticSemanticPass=True, successfulAcceptanceVerified=False,
            sponsorAcceptanceVerified=False, receivedCashVerified=False)
        write_json(evidence / 'live-cli-result.json', result)
        files = {path.relative_to(evidence).as_posix(): dict(size=path.stat().st_size, sha256=file_digest(path))
            for path in sorted(evidence.rglob('*')) if path.is_file() and not path.is_symlink()}
        write_json(evidence / 'evidence-manifest.json', dict(createdAtUtc=now(), files=files, disclosure=DISCLOSURE))
    print(json.dumps(dict(evidence=str(evidence), cliExecuted=result['cliExecuted'], cliExitCode=result.get('cliExitCode'),
        fixtureUnchanged=result.get('fixtureUnchanged'), semanticAcceptance='pending independent review', receivedCashVerified=False)), flush=True)
    return 0 if (result.get('processCompletedSuccessfully') and result.get('fixtureUnchanged')
                 and result.get('nonErrorCompleteResultObserved') and result.get('nativeHttpEvidenceComplete') and not result.get('error')
                 and not result.get('resourceGuardFailure') and not result.get('cleanupErrors')) else 1


if __name__ == '__main__':
    raise SystemExit(main())
