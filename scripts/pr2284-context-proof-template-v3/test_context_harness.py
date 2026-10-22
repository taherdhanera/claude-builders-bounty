"""Offline regressions for the separate context task; no model/network/Git calls."""
import ast
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import native_http_recorder as recorder
import run_native_ollama_linux as runner
from guard_fixture_paths import check


EXACT_PROMPT = ('What project is this, and what conventions and constraints should you follow when working in it? '
                'Give a concise overview based on the project files.')
WORK = Path(__file__).resolve().parent


class ContextHarnessTests(unittest.TestCase):
    def test_exact_pinned_prompt_bytes_are_the_only_prompt_source(self):
        self.assertEqual(runner.load_context_prompt(), EXACT_PROMPT)
        self.assertEqual((WORK / runner.CONTEXT_PROMPT_FILE).read_bytes(), EXACT_PROMPT.encode('utf-8'))
        self.assertEqual(hashlib.sha256(EXACT_PROMPT.encode()).hexdigest(), runner.CONTEXT_PROMPT_SHA256)
        tree = ast.parse((WORK / 'run_native_ollama_linux.py').read_text())
        main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'main')
        assignments = [node for node in ast.walk(main) if isinstance(node, ast.Assign)
                       and any(isinstance(target, ast.Name) and target.id == 'prompt' for target in node.targets)]
        self.assertEqual(len(assignments), 1)
        self.assertIsInstance(assignments[0].value, ast.Call)
        self.assertEqual(assignments[0].value.func.id, 'load_context_prompt')
        command = [node for node in ast.walk(main) if isinstance(node, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id == 'command' for target in node.targets)]
        self.assertEqual(len(command), 1)
        self.assertEqual(command[0].value.func.id, 'build_cli_command')

    def test_missing_or_tampered_prompt_fails_closed_without_normalization(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            with self.assertRaisesRegex(RuntimeError, 'missing or nonregular'):
                runner.load_context_prompt(directory)
            for raw in [(EXACT_PROMPT + '\n').encode(), b'Build a billing page.', b'\xef\xbb\xbf' + EXACT_PROMPT.encode()]:
                with self.subTest(raw=raw):
                    (directory / runner.CONTEXT_PROMPT_FILE).write_bytes(raw)
                    with self.assertRaisesRegex(RuntimeError, 'SHA256 differs'):
                        runner.load_context_prompt(directory)

    def test_default_command_has_exact_prompt_and_no_system_appendage(self):
        command = runner.build_cli_command(Path('/private/claude'), Path('/evidence'), 'isolated-session', EXACT_PROMPT)
        self.assertEqual(command, [str(Path('/private/claude')), '--restricted', '--permission-mode', 'default',
            '--tools', 'Read,Glob,Grep', '--allowedTools', 'Read,Glob,Grep', '--strict-mcp-config',
            '--mcp-config', '{"mcpServers":{}}', '--settings', str(Path('/evidence') / 'cli-settings.json'),
            '--setting-sources', '', '--session-id', 'isolated-session', '--max-turns', '10', '--effort', 'low',
            '--output-format', 'stream-json', '--verbose', '-p', EXACT_PROMPT])
        self.assertFalse(any(arg.startswith(('--append-system-prompt', '--system-prompt')) for arg in command))
        self.assertEqual(command[-1].encode(), (WORK / 'context-prompt.txt').read_bytes())

    def test_command_builder_rejects_unpinned_hints(self):
        with self.assertRaisesRegex(RuntimeError, 'not the pinned context prompt'):
            runner.build_cli_command(Path('/cli'), Path('/evidence'), 'id', EXACT_PROMPT + ' Do not ask questions.')

    def test_branch_paths_and_workflow_share_separate_identity(self):
        workflow = (WORK / 'workflow-template.yml').read_text()
        self.assertEqual(runner.BRANCH, 'refs/heads/proof/claude2284-context-template-20261023')
        self.assertIn('branches: [proof/claude2284-context-template-20261023]', workflow)
        self.assertIn("github.ref == '" + runner.BRANCH + "'", workflow)
        self.assertIn(runner.SCRIPTS_PREFIX + '**', workflow)
        self.assertIn(runner.WORKFLOW_PATH, workflow)
        self.assertEqual(workflow.count('python3 -B ' + runner.SCRIPTS_PREFIX + 'run_native_ollama_linux.py'), 2)
        self.assertNotIn('ollama9b-45m-20261021', workflow)
        self.assertIn('persist-credentials: false', workflow)
        self.assertIn('github.run_attempt == 1', workflow)
        offline = 'python3 -B -m unittest -v test_native_boundaries test_context_harness test_resource_phases test_fixture_observation'
        launch = 'python3 -B ' + runner.SCRIPTS_PREFIX + 'run_native_ollama_linux.py'
        self.assertEqual(workflow.count(offline), 1)
        self.assertIn('working-directory: ' + runner.SCRIPTS_PREFIX.rstrip('/'), workflow)
        self.assertLess(workflow.index(offline), workflow.index(launch))

    def test_resource_runtime_model_and_source_pins_are_preserved(self):
        self.assertEqual(runner.SOURCE_HEAD, '84788f9ec4f713723671c792db985527b1411f27')
        self.assertEqual(runner.TEMPLATE_SHA256, '33653f02bf65e4195ce56c0a16e11be3380acbb906a8f431109fe7208cf37d0f')
        self.assertEqual(runner.CLI_VERSION, '2.1.296')
        self.assertEqual(runner.CNA_VERSION, '15.5.28')
        self.assertEqual(runner.OLLAMA_VERSION, '0.40.6')
        self.assertEqual(runner.ARCHIVE_SHA256, 'c164ab8b1b28e2a247c29719b8e404c423c5b83ae64c3ab4e59d50c7ff7fc5e0')
        self.assertEqual(runner.MODEL, 'qwen3.5:9b-q4_K_M')
        self.assertEqual(runner.MODEL, recorder.MODEL)
        self.assertEqual(runner.MODEL_DIGEST, '56671c2ab9385f9cfcb404638e32cd62d88e3501d44822208363c010179a3c90')
        self.assertEqual(runner.MODEL_BYTES, 6_550_813_952)
        self.assertEqual(runner.CONTEXT, 65536)
        self.assertEqual(recorder.MAX_CALLS, 16)
        self.assertEqual(recorder.MAX_BODY_BYTES, 8_000_000)
        self.assertEqual(runner.file_digest(WORK / 'guard_fixture_paths.py'),
                         '0b38ac71326185653d9e492cf8890fedb4181e0281c5c3d042835f6ce28092d8')

    def test_all_budgets_are_consistent_and_bounded(self):
        self.assertEqual(runner.CLI_SECONDS, 1800)
        self.assertEqual(recorder.MAX_SECONDS, runner.CLI_SECONDS + 60)
        self.assertEqual(runner.WHOLE_SECONDS, 2220)
        self.assertLess(runner.CLI_SECONDS + 30, runner.WHOLE_SECONDS)
        self.assertEqual(40 * 60 - runner.WHOLE_SECONDS, 180)
        self.assertIn('timeout-minutes: 40', (WORK / 'workflow-template.yml').read_text())

    def test_question_tool_failure_remains_failure_even_after_terminal_success(self):
        terminal = dict(type='result', subtype='success', is_error=False, stop_reason='end_turn')
        for name in ['AskUserQuestion', 'ask_question', 'Agent', 'Glob<|channel|>commentary']:
            with self.subTest(name=name):
                events = [dict(type='assistant', message=dict(content=[dict(type='tool_use', id='attempt', name=name, input={})])),
                          dict(type='user', message=dict(content=[dict(type='tool_result', tool_use_id='attempt', is_error=True,
                              content='Error: tool is unavailable')])), terminal]
                parsed = runner.parse_stream('\n'.join(map(json.dumps, events)))
                self.assertTrue(parsed['nonErrorCompleteResultObserved'])
                self.assertFalse(parsed['noUnexpectedToolAttemptsObserved'])
                self.assertEqual(parsed['unexpectedToolAttempts'][0]['name'], name)
                result = dict(processCompletedSuccessfully=True, fixtureUnchanged=True, fixtureSizesUnchanged=True, nativeHttpEvidenceComplete=True,
                              nonErrorCompleteResultObserved=True, noToolErrorsObserved=parsed['noToolErrorsObserved'],
                              noUnexpectedToolAttemptsObserved=parsed['noUnexpectedToolAttemptsObserved'])
                self.assertFalse(runner.structural_run_complete(result))
                if 'question' in name.lower():
                    self.assertEqual(len(parsed['clarificationToolAttempts']), 1)

    def test_structural_completion_cannot_prove_factual_or_no_question_success(self):
        events = [dict(type='assistant', message=dict(content=[dict(type='text', text='Which database should I use?')])),
                  dict(type='result', subtype='success', is_error=False, stop_reason='end_turn')]
        parsed = runner.parse_stream('\n'.join(map(json.dumps, events)))
        self.assertTrue(parsed['nonErrorCompleteResultObserved'])
        self.assertIn('unscored', parsed['naturalLanguageClarificationAssessment'])
        self.assertIn('independent context rubric', parsed['semanticAcceptance'])
        self.assertNotIn('semanticPass', parsed)

    def test_structural_gate_rejects_missing_or_failed_evidence(self):
        good = dict(processCompletedSuccessfully=True, fixtureUnchanged=True, fixtureSizesUnchanged=True, nonErrorCompleteResultObserved=True,
                    noUnexpectedToolAttemptsObserved=True, noToolErrorsObserved=True, nativeHttpEvidenceComplete=True)
        self.assertTrue(runner.structural_run_complete(good))
        for field in good:
            with self.subTest(field=field):
                self.assertFalse(runner.structural_run_complete({**good, field: None}))
        for field in ('error', 'resourceGuardFailure', 'cleanupErrors'):
            self.assertFalse(runner.structural_run_complete({**good, field: 'failure'}))

    def test_denied_read_remains_failure_even_after_terminal_success(self):
        events = [dict(type='assistant', message=dict(content=[dict(type='tool_use', id='denied', name='Read',
                      input=dict(file_path='/outside/secret'))])),
                  dict(type='user', message=dict(content=[dict(type='tool_result', tool_use_id='denied',
                      is_error=True, content='PreToolUse hook denied the out-of-fixture read')])),
                  dict(type='result', subtype='success', is_error=False, stop_reason='end_turn')]
        parsed = runner.parse_stream('\n'.join(map(json.dumps, events)))
        self.assertTrue(parsed['nonErrorCompleteResultObserved'])
        self.assertTrue(parsed['noUnexpectedToolAttemptsObserved'])
        self.assertFalse(parsed['noToolErrorsObserved'])
        self.assertEqual(len(parsed['toolErrors']), 1)
        self.assertFalse(runner.structural_run_complete(dict(processCompletedSuccessfully=True, fixtureUnchanged=True, fixtureSizesUnchanged=True,
            nonErrorCompleteResultObserved=True, noUnexpectedToolAttemptsObserved=True,
            noToolErrorsObserved=parsed['noToolErrorsObserved'], nativeHttpEvidenceComplete=True)))

    def test_default_mode_keeps_question_and_mutation_guarded(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Path(temporary)
            for tool in ('AskUserQuestion', 'Agent', 'Explore', 'Write', 'Edit', 'Bash', 'ExitPlanMode'):
                with self.subTest(tool=tool):
                    self.assertFalse(check(dict(tool_name=tool, tool_input={}), fixture))
            self.assertTrue(check(dict(tool_name='Read', tool_input=dict(file_path='CLAUDE.md')), fixture))
            self.assertFalse(check(dict(tool_name='Read', tool_input=dict(file_path='../outside')), fixture))


if __name__ == '__main__':
    unittest.main()
