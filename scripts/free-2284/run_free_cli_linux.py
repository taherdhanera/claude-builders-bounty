"""One Linux CI attempt using the official CLI and a disclosed anonymous model.

Preparation only until root executes the separately reviewed public workflow.
No semantic acceptance is inferred from an exit code. Evidence stays in logs.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import time
import uuid


WORK = Path(__file__).resolve().parent
ROOT = WORK.parents[1]
SOURCE_HEAD = '26994b38341d36692b81291d689b0e3adad0cff2'
SOURCE_TEMPLATE = 'templates/nextjs-sqlite-saas/CLAUDE.md'
SOURCE_PROTOCOL = 'templates/nextjs-sqlite-saas/verification/claude-code-greenfield-smoke.md'
TEMPLATE_SHA256 = '252b4d86c2d6c432fe0c92ec90c7c249495dfa2ab5ff29c341ba7894221b7261'
BRANCH = 'refs/heads/proof/claude2284-anonymous-recovery-20261021'
CLI_VERSION = '2.1.296'
CNA_VERSION = '15.5.28'
CATALOG_URL = 'https://text.pollinations.ai/models'
PROVIDER_URL = 'https://text.pollinations.ai/openai'
POLICY_URLS = ['https://enter.pollinations.ai/privacy', 'https://enter.pollinations.ai/terms']
DISCLOSURE = ('Official Claude Code CLI with anonymous Pollinations openai-fast/GPT-OSS20B '
              'through a disclosed loopback protocol adapter. Not Anthropic inference, '
              'sponsor acceptance, entitlement, or received cash.')


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=True)
        stream.write('\n')


def evidence_path():
    run_id = os.environ.get('GITHUB_RUN_ID', '')
    attempt = os.environ.get('GITHUB_RUN_ATTEMPT', '')
    if not run_id.isdecimal() or not attempt.isdecimal():
        raise RuntimeError('An actual GitHub run identity is required.')
    return Path(os.environ['RUNNER_TEMP']) / ('free-2284-evidence-' + run_id + '-' + attempt)


def clean_environment(home):
    # Do not forward GitHub, cloud, npm, API credentials, proxy settings, or user config.
    env = {key: value for key, value in os.environ.items() if key in {'PATH', 'LANG', 'LC_ALL'}}
    home.mkdir(mode=0o700, parents=True, exist_ok=False)
    temporary = home / 'tmp'
    temporary.mkdir(mode=0o700)
    env.update(HOME=str(home), XDG_CONFIG_HOME=str(home / '.config'),
               XDG_CACHE_HOME=str(home / '.cache'), TMPDIR=str(temporary),
               CI='1', NO_COLOR='1', GIT_CONFIG_NOSYSTEM='1',
               GIT_CONFIG_GLOBAL='/dev/null', GIT_TERMINAL_PROMPT='0',
               NPM_CONFIG_USERCONFIG='/dev/null', NPM_CONFIG_AUDIT='false',
               NPM_CONFIG_FUND='false', NPM_CONFIG_REGISTRY='https://registry.npmjs.org/',
               NEXT_TELEMETRY_DISABLED='1')
    return env


def stop_group(process):
    if process is None:
        return
    # Every child starts a new session; only this task's exact process group is signalled.
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
        record['completedAtUtc'] = now()
        record['stdoutSha256'] = digest(stdout_path.read_bytes()) if stdout_path.exists() else None
        record['stderrSha256'] = digest(stderr_path.read_bytes()) if stderr_path.exists() else None
        write_json(directory / (name + '-process.json'), record)
    if record.get('timedOut') or record.get('exitCode') != 0:
        raise RuntimeError(name + ' failed or timed out; no retry/fallback.')
    return stdout_path.read_bytes()


def fixture_files(fixture):
    result = {}
    for path in sorted(fixture.rglob('*')):
        relative = path.relative_to(fixture)
        if '.git' in relative.parts:
            continue
        if path.is_symlink():
            raise RuntimeError('Unexpected fixture symlink: ' + str(relative))
        if path.is_file():
            result[relative.as_posix()] = digest(path.read_bytes())
    return result


def emit_only(directory):
    # Emit every actual evidence byte, not a reconstructed/truncated summary.
    # Select the random workflow-command stop token only after outputs are complete.
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
    assert sys.platform.startswith('linux'), 'This launcher requires the isolated Linux runner.'
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    assert os.environ.get('GITHUB_REPOSITORY') == 'taherdhanera/claude-builders-bounty'
    assert os.environ.get('GITHUB_REF') == BRANCH
    assert os.environ.get('GITHUB_RUN_ATTEMPT') == '1', 'Never repeat an identical run.'
    evidence.mkdir(mode=0o700, parents=False, exist_ok=False)
    private = Path(os.environ['RUNNER_TEMP']) / ('free-2284-private-' + os.environ['GITHUB_RUN_ID'])
    private.mkdir(mode=0o700, exist_ok=False)
    setup_env = clean_environment(private / 'setup-home')
    cli_env = clean_environment(private / 'cli-home')
    bridge_env = clean_environment(private / 'bridge-home')
    fixture_parent = private / 'fixture'
    fixture_parent.mkdir(mode=0o700)
    fixture = fixture_parent / 'acme-saas'
    runtime = private / 'official-cli'
    result = dict(startedAtUtc=now(), disclosure=DISCLOSURE, cliExecuted=False,
                  successfulAcceptanceVerified=False, semanticAssessment='pending human review',
                  inferenceProbeRepeated=False, ambiguousDoNotRetry=False)
    overall_deadline = time.monotonic() + 1320
    bridge = client = None
    bridge_handles = []
    before = None
    stop_file = evidence / 'live-model-bridge/operator-stop.json'
    def bounded(seconds):
        remaining = int(overall_deadline - time.monotonic())
        if remaining < 1:
            raise RuntimeError('Overall launcher deadline expired; no further command.')
        return min(seconds, remaining)
    def git(*arguments, cwd=ROOT):
        return subprocess.check_output(['git', *arguments], cwd=cwd, env=setup_env, timeout=15)
    try:
        parents = git('rev-list', '--parents', '-n', '1', 'HEAD').decode().split()
        assert len(parents) == 2 and parents[1] == SOURCE_HEAD, 'Proof commit must be a direct child of the exact PR head.'
        assert git('status', '--porcelain=v1').decode() == ''
        template = git('show', SOURCE_HEAD + ':' + SOURCE_TEMPLATE)
        protocol_bytes = git('show', SOURCE_HEAD + ':' + SOURCE_PROTOCOL)
        assert digest(template) == TEMPLATE_SHA256
        protocol = protocol_bytes.decode('utf-8')
        prompt_section = protocol.split('## Exact first prompt\n', 1)[1].split('\n## ', 1)[0].strip()
        prompt = '\n'.join(line[2:] if line.startswith('> ') else line for line in prompt_section.splitlines())
        assert prompt and not prompt.startswith('>')
        (evidence / 'exact-first-prompt.txt').write_bytes(prompt.encode('utf-8'))
        (evidence / 'exact-source-protocol.md').write_bytes(protocol_bytes)
        (evidence / 'exact-source-CLAUDE.md').write_bytes(template)
        copied_scripts = {path.name: digest(path.read_bytes()) for path in sorted(WORK.glob('*')) if path.is_file()}
        write_json(evidence / 'source-identity.json', dict(sourceHead=SOURCE_HEAD, proofCommit=parents[0],
            proofParent=parents[1], sourceTemplatePath=SOURCE_TEMPLATE, templateCanonicalSha256=digest(template),
            protocolSha256=digest(protocol_bytes), promptSha256=digest(prompt.encode('utf-8')),
            scripts=copied_scripts, runId=os.environ['GITHUB_RUN_ID'], runAttempt=1,
            runUrl='https://github.com/taherdhanera/claude-builders-bounty/actions/runs/' + os.environ['GITHUB_RUN_ID']))

        # One metadata request only. No authorization, redirects, proxy, inference probe, or retries.
        catalog_body = evidence / 'model-catalog-response.bin'
        catalog_headers = evidence / 'model-catalog-response-headers.txt'
        status = run_command(['curl', '--silent', '--show-error', '--noproxy', '*', '--proto', '=https',
            '--max-time', '25', '--max-redirs', '0', '--max-filesize', '2097152',
            '--dump-header', str(catalog_headers), '--output', str(catalog_body),
            '--write-out', '%{http_code}', CATALOG_URL], ROOT, setup_env, evidence, 'catalog', bounded(30)).decode().strip()
        assert status == '200', 'Metadata request was not HTTP 200; no inference attempt.'
        catalog = json.loads(catalog_body.read_bytes())
        assert isinstance(catalog, list)
        models = [model for model in catalog if isinstance(model, dict) and model.get('name') == 'openai-fast']
        assert len(models) == 1 and models[0].get('tier') == 'anonymous' and models[0].get('tools') is True
        source_ids = dict(verifiedAtUtc=now(), sourceHead=SOURCE_HEAD,
            templateCanonicalSha256=digest(template), modelCatalog=dict(url=CATALOG_URL, httpStatus=200,
                sha256=digest(catalog_body.read_bytes()), headersSha256=digest(catalog_headers.read_bytes()), selectedEntry=models[0]),
            policies=POLICY_URLS, providerEndpoint=PROVIDER_URL,
            previousExternalProbe=dict(disclosure='Root observed anonymous HTTP 200 GPT-OSS20B before this runner. That external probe is not re-executed or asserted as runner inference evidence.',
                publicSourceIds=[CATALOG_URL, PROVIDER_URL], actualResponseSha256='aab1a7f42c106b0bb39c3f04bb9ed183f83955f1d0ec72ea909ebe10e31c4c42'),
            actualInferenceDisclosure=DISCLOSURE)
        write_json(evidence / 'verified-source-ids.json', source_ids)

        run_command(['npm', 'install', '--prefix', str(runtime), '--no-audit', '--no-fund',
                     '@anthropic-ai/claude-code@' + CLI_VERSION], ROOT, setup_env, evidence, 'official-cli-install', bounded(180))
        cli = runtime / 'node_modules/.bin/claude'
        cli_package = json.loads((runtime / 'node_modules/@anthropic-ai/claude-code/package.json').read_text())
        assert cli_package['version'] == CLI_VERSION
        run_command(['npx', '--yes', 'create-next-app@' + CNA_VERSION, 'acme-saas', '--ts', '--eslint',
            '--app', '--no-tailwind', '--use-npm', '--skip-install', '--disable-git', '--no-src-dir',
            '--import-alias', '@/*', '--yes'], fixture_parent, setup_env, evidence, 'fresh-starter-create', bounded(180))
        assert fixture.is_dir() and not (fixture / 'node_modules').exists()
        assert not (fixture / 'src').exists() and not (fixture / 'CLAUDE.md').exists()
        package = json.loads((fixture / 'package.json').read_text())
        assert package['dependencies']['next'] == CNA_VERSION
        (fixture / 'CLAUDE.md').write_bytes(template)
        git('init', '-q', cwd=fixture)
        git('add', '.', cwd=fixture)
        git('-c', 'user.name=Disposable Execution Proof', '-c', 'user.email=proof@localhost',
            'commit', '-qm', 'Disposable generated starter baseline', cwd=fixture)
        assert git('status', '--porcelain=v1', cwd=fixture).decode() == ''
        before = fixture_files(fixture)
        write_json(evidence / 'fixture-before.json', before)
        write_json(evidence / 'fixture-package.json', package)
        versions = dict(node=run_command(['node', '--version'], fixture, setup_env, evidence, 'node-version', bounded(15)).decode().strip(),
            npm=run_command(['npm', '--version'], fixture, setup_env, evidence, 'npm-version', bounded(15)).decode().strip(),
            claude=run_command([str(cli), '--version'], fixture, cli_env, evidence, 'claude-version', bounded(15)).decode().strip(),
            claudePackageVersion=cli_package['version'], createNextAppVersion=CNA_VERSION,
            nextVersion=package['dependencies']['next'], dependenciesInstalled=False)
        assert versions['node'].startswith('v22.') and versions['claude'].startswith(CLI_VERSION)
        write_json(evidence / 'versions.json', versions)

        guard_path = WORK / 'guard_fixture_paths.py'
        spec = importlib.util.spec_from_file_location('runner_fixture_guard', guard_path)
        guard = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(guard)
        assert guard.check(dict(tool_name='Read', tool_input=dict(file_path=str(fixture / 'CLAUDE.md'))), fixture)
        assert guard.check(dict(tool_name='Grep', tool_input=dict(pattern='next')), fixture)
        assert not guard.check(dict(tool_name='Read', tool_input=dict(file_path=str(ROOT / 'README.md'))), fixture)
        assert not guard.check(dict(tool_name='Glob', tool_input=dict(pattern='../**')), fixture)
        assert not guard.check(dict(tool_name='Write', tool_input=dict(file_path=str(fixture / 'x'))), fixture)
        hook_command = shlex.join([sys.executable, str(guard_path), '--root', str(fixture),
                                   '--log', str(evidence / 'tool-path-guard.jsonl')])
        settings = dict(hooks=dict(PreToolUse=[dict(matcher='Read|Glob|Grep', hooks=[dict(type='command', command=hook_command, timeout=5)])]))
        write_json(evidence / 'cli-settings.json', settings)
        # Test the actual CLI boundary offline first. The saved provider fixture
        # is replay evidence only; no tool result is manufactured or model called.
        from offline_unknown_tool_probe import run_probe
        probe_env = clean_environment(private / 'offline-probe-home')
        probe = run_probe(cli, fixture, probe_env, evidence / 'cli-settings.json', prompt,
            WORK / 'recorded-malformed-provider-response.json', evidence / 'offline-unknown-tool-probe')
        result['offlineUnknownToolProbePassed'] = probe.get('probePassed') is True
        if not result['offlineUnknownToolProbePassed']:
            raise RuntimeError('Actual CLI offline unknown-tool boundary was not verified; no live provider call.')
        bridge_source = (WORK / 'anthropic_openai_bridge.py').read_text()
        assert '--stop-file' in bridge_source, 'Require reviewed stop-file-aware bridge revision.'
        assert time.monotonic() + 930 < overall_deadline, 'Do not begin a partial CLI time budget.'
        bridge_directory = evidence / 'live-model-bridge'
        for name in ('bridge-stdout.txt', 'bridge-stderr.txt', 'claude-output.jsonl', 'claude-stderr.txt'):
            bridge_handles.append((evidence / name).open('xb'))
        bridge = subprocess.Popen([sys.executable, str(WORK / 'anthropic_openai_bridge.py'),
            '--evidence-dir', str(bridge_directory), '--source-ids-file', str(evidence / 'verified-source-ids.json'),
            '--stop-file', str(stop_file)], cwd=ROOT, env=bridge_env, stdin=subprocess.DEVNULL,
            stdout=bridge_handles[0], stderr=bridge_handles[1], start_new_session=True)
        startup_deadline = time.monotonic() + 20
        session = None
        while time.monotonic() < startup_deadline:
            path = bridge_directory / 'session.json'
            if path.exists():
                try:
                    candidate = json.loads(path.read_bytes())
                    if candidate.get('listenHost') == '127.0.0.1' and isinstance(candidate.get('listenPort'), int):
                        session = candidate
                        break
                except (OSError, ValueError):
                    pass
            if bridge.poll() is not None:
                raise RuntimeError('Bridge exited before readiness; no CLI launch.')
            time.sleep(0.1)
        if not session:
            raise RuntimeError('Bridge readiness deadline exceeded; no CLI launch.')
        cli_env.update(ANTHROPIC_BASE_URL='http://127.0.0.1:' + str(session['listenPort']),
            ANTHROPIC_AUTH_TOKEN='anonymous-local-bridge', ANTHROPIC_API_KEY='', ANTHROPIC_MODEL='openai-fast',
            ANTHROPIC_SMALL_FAST_MODEL='openai-fast', ANTHROPIC_DEFAULT_HAIKU_MODEL='openai-fast',
            ANTHROPIC_DEFAULT_SONNET_MODEL='openai-fast', ANTHROPIC_DEFAULT_OPUS_MODEL='openai-fast',
            CLAUDE_CODE_SUBAGENT_MODEL='openai-fast', CLAUDE_CONFIG_DIR=str(private / 'cli-home/.claude'),
            DISABLE_AUTOUPDATER='1', DISABLE_TELEMETRY='1', DISABLE_ERROR_REPORTING='1',
            CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC='1', CLAUDE_CODE_MAX_RETRIES='0',
            CLAUDE_CODE_MAX_OUTPUT_TOKENS='4096', MAX_THINKING_TOKENS='0', API_TIMEOUT_MS='240000')
        command = [str(cli), '--restricted', '--permission-mode', 'plan', '--tools', 'Read,Glob,Grep',
            '--allowedTools', 'Read,Glob,Grep', '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}',
            '--settings', str(evidence / 'cli-settings.json'), '--setting-sources', '', '--session-id', str(uuid.uuid4()),
            '--max-turns', '10', '--effort', 'low', '--output-format', 'stream-json', '--verbose', '-p', prompt]
        write_json(evidence / 'live-cli-intent.json', dict(startedAtUtc=now(), sourceHead=SOURCE_HEAD,
            command=command, templateSha256=digest(template), promptSha256=digest(prompt.encode('utf-8')),
            adapterSha256=digest((WORK / 'anthropic_openai_bridge.py').read_bytes()), guardSha256=digest(guard_path.read_bytes()),
            cliBudgetSeconds=900, bridgeBudgetSeconds=1200, maximumProviderCalls=16, providerSpacingSeconds=40,
            apiTimeoutMilliseconds=240000, disclosure=DISCLOSURE, semanticAcceptance='Not automatically assessed'))
        client = subprocess.Popen(command, cwd=fixture, env=cli_env, stdin=subprocess.DEVNULL,
            stdout=bridge_handles[2], stderr=bridge_handles[3], start_new_session=True)
        result.update(cliExecuted=True, cliPid=client.pid, bridgePid=bridge.pid, cliStartedAtUtc=now())
        try:
            result['cliExitCode'] = client.wait(timeout=900)
        except subprocess.TimeoutExpired:
            result.update(cliTimedOut=True, ambiguousDoNotRetry=True)
        finally:
            stop_group(client)
            write_json(stop_file, dict(atUtc=now(), reason='client_completed_or_deadline', noRetry=True))
        try:
            bridge.wait(timeout=5)
        except subprocess.TimeoutExpired:
            result['bridgeForcedCleanupRequired'] = True
        result['processCompletedSuccessfully'] = result.get('cliExitCode') == 0
    except Exception as error:
        result.update(error=type(error).__name__ + ': ' + str(error), ambiguousDoNotRetry=result['cliExecuted'])
    finally:
        if bridge is not None and stop_file.parent.is_dir() and not stop_file.exists():
            write_json(stop_file, dict(atUtc=now(), reason='operator_cleanup', noRetry=True))
        for process in (client, bridge):
            try:
                stop_group(process)
            except Exception as error:
                result.setdefault('cleanupErrors', []).append(str(error))
        for handle in bridge_handles:
            handle.close()
        if before is not None:
            try:
                after = fixture_files(fixture)
                write_json(evidence / 'fixture-after.json', after)
                result.update(fixtureUnchanged=before == after,
                    fixtureGitStatus=git('status', '--porcelain=v1', cwd=fixture).decode())
            except Exception as error:
                result['fixtureVerificationError'] = str(error)
        result.update(completedAtUtc=now(), noAutomaticSemanticPass=True,
                      successfulAcceptanceVerified=False, sponsorAcceptanceVerified=False,
                      receivedCashVerified=False)
        write_json(evidence / 'live-cli-result.json', result)
        files = {path.relative_to(evidence).as_posix(): dict(size=path.stat().st_size, sha256=digest(path.read_bytes()))
                 for path in sorted(evidence.rglob('*')) if path.is_file() and not path.is_symlink()}
        write_json(evidence / 'evidence-manifest.json', dict(createdAtUtc=now(), files=files, disclosure=DISCLOSURE))
    print(json.dumps(dict(evidence=str(evidence), cliExecuted=result['cliExecuted'],
        cliExitCode=result.get('cliExitCode'), fixtureUnchanged=result.get('fixtureUnchanged'),
        semanticAcceptance='pending human review', receivedCashVerified=False)), flush=True)
    return 0 if result.get('processCompletedSuccessfully') and result.get('fixtureUnchanged') and not result.get('error') and not result.get('cleanupErrors') else 1


if __name__ == '__main__':
    raise SystemExit(main())
