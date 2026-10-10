import concurrent.futures
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('engine', ROOT / 'bin/engine.py')
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)


class Hooks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, MODEL_DECIDER_HOME=self.tmp.name)
        self.env.start()
        self.addCleanup(self.env.stop)

    def call(self, event, platform='codex', **fields):
        p = {'session_id': 's', 'cwd': '/project', 'hook_event_name': event,
             'model': 'gpt-6.1-sol' if platform == 'codex' else 'claude-sonnet-5-5', **fields}
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            engine.hook(p, platform)
        return json.loads(out.getvalue()) if out.getvalue() else None

    def rows(self):
        return list(engine.read_jsonl(Path(self.tmp.name) / 'log.jsonl'))

    def begin(self, rid='r', platform='codex', prompt='implement a feature'):
        self.call('UserPromptSubmit', platform, prompt=prompt,
                  **({'turn_id': rid} if platform == 'codex' else {'prompt_id': rid}))

    def agent(self, call_id='a', role='deep', platform='codex', **fields):
        config = engine.MODELS[platform][role]
        i = {'model': config['model'], 'description': '[architecture] Work',
             'message': '[architecture] Work', 'reasoning_effort': 'medium', **fields}
        if platform == 'claude':
            i['subagent_type'] = config['agent']
        return self.call('PreToolUse', platform, tool_name='spawn_agent' if platform == 'codex' else 'Agent',
                         tool_use_id=call_id, tool_input=i)

    def test_profiles_and_aliases(self):
        for name, role in engine.ALIASES.items():
            self.assertEqual(engine.tier(name), role)
        for platform in ('claude', 'codex'):
            r = self.call('SessionStart', platform)
            context = r['hookSpecificOutput']['additionalContext']
            self.assertIn(engine.MODELS[platform]['balanced']['model'], context)
            self.assertIn('Current session ID: s', context)

    def test_limit_reset_and_duplicate_calls(self):
        for platform in ('codex', 'claude'):
            self.begin(platform=platform)
            self.assertIsNone(self.agent(platform=platform))
            self.assertIsNone(self.agent(platform=platform))  # Same tool ID is idempotent.
            r = self.agent('b', platform=platform)
            self.assertEqual(r['hookSpecificOutput']['permissionDecision'], 'deny')
            self.begin('r2', platform)
            self.assertIsNone(self.agent('c', platform=platform))

    def test_parallel_deep_launches(self):
        self.begin()
        def launch(n):
            p = {'session_id': 's', 'cwd': '/project', 'turn_id': 'r',
                 'hook_event_name': 'PreToolUse', 'tool_name': 'spawn_agent',
                 'tool_use_id': str(n), 'tool_input': {'model': 'gpt-6-astra',
                 'reasoning_effort': 'medium', 'message': '[hard debugging] Find cause'}}
            return subprocess.run(['python3', str(ROOT / 'bin/engine.py'), 'hook', 'codex'],
                                  input=json.dumps(p), capture_output=True, text=True, check=True).stdout
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(launch, range(6)))
        self.assertEqual(sum(not r for r in results), 1)
        self.assertEqual(sum('deny' in r for r in results), 5)

    def test_override_and_effort_are_one_shot(self):
        self.begin(prompt='/tier astra high redesign the cache')
        self.assertIsNone(self.agent(reasoning_effort='high'))
        self.assertIsNone(self.agent('b', reasoning_effort='high'))
        wrong = self.agent('c', 'fast', reasoning_effort='high')
        self.assertIn('Explicit /tier', wrong['hookSpecificOutput']['permissionDecisionReason'])
        self.call('Stop', turn_id='r')
        self.begin('r2')
        wrong = self.agent('d', reasoning_effort='high')
        self.assertIn('medium', wrong['hookSpecificOutput']['permissionDecisionReason'])
        self.assertIsNone(self.agent('e'))  # Failed effort validation consumes no budget.
        self.assertIn('deny', json.dumps(self.agent('f')))

    def test_invalid_command_and_rate(self):
        self.begin(prompt='/tier deep')
        self.assertFalse(any(r['event'] == 'override' for r in self.rows()))
        self.begin('r2')
        self.agent(role='fast')
        self.call('PostToolUse', tool_use_id='a', tool_response={'agent_id': 'child', 'model': 'gpt-6-luna'})
        rated = self.call('UserPromptSubmit', prompt='/rate should-be luna', turn_id='rating')
        self.assertEqual(rated['decision'], 'block')
        self.assertEqual(self.rows()[-1]['verdict'], 'ok')
        self.call('UserPromptSubmit', prompt='/rate should-be deep', turn_id='rating2')
        self.assertEqual(self.rows()[-1]['should_be'], 'deep')

    def test_claude_command_expansion_is_idempotent(self):
        self.begin(platform='claude', prompt='/tier opus redesign')
        self.call('UserPromptExpansion', 'claude', command_name='model-decider:tier', command_args='opus redesign')
        self.assertEqual(sum(r['event'] == 'override' for r in self.rows()), 1)
        self.assertIsNone(self.agent(platform='claude'))
        self.assertIsNone(self.agent('b', platform='claude'))

    def test_main_model_and_deduplicated_usage(self):
        self.begin(platform='claude')
        tp = Path(self.tmp.name) / 'transcript.jsonl'
        messages = [{'type': 'user', 'promptId': 'r', 'message': {'content': 'request'}}]
        for content in ('thinking', 'text'):
            messages.append({'type': 'assistant', 'message': {'id': 'm', 'model': 'claude-sonnet-5-5',
                             'content': [{'type': content}], 'usage': {'output_tokens': 12}}})
        messages.append({'type': 'user', 'promptId': 'r', 'message': {'content': [{'type': 'tool_result'}]}})
        tp.write_text('\n'.join(json.dumps(m) for m in messages))
        self.call('Stop', 'claude', prompt_id='r', transcript_path=str(tp))
        self.call('Stop', 'claude', prompt_id='r', transcript_path=str(tp))
        picks = [r for r in self.rows() if r['event'] == 'pick']
        self.assertEqual(len(picks), 1)
        self.assertEqual(picks[0]['tier'], 'balanced')
        self.assertEqual(picks[0]['usage']['output_tokens'], 12)

    def test_no_fabricated_usage_and_stale_stop(self):
        self.begin('r2')
        self.call('Stop', turn_id='r1')
        self.assertEqual(self.rows(), [])
        self.call('Stop', turn_id='r2')
        self.assertIsNone(self.rows()[-1]['usage'])
        self.assertEqual(self.rows()[-1]['model'], 'gpt-6.1-sol')

    def test_nested_claude_ignored(self):
        self.begin(platform='claude')
        self.call('PreToolUse', 'claude', agent_id='child', tool_name='Agent', tool_use_id='x', tool_input={'model': 'opus'})
        self.assertEqual(self.rows(), [])

    def test_resolution_and_platform_separation(self):
        for platform in ('claude', 'codex'):
            self.begin(platform=platform)
            self.agent(role='fast', platform=platform)
        self.call('PostToolUse', 'claude', tool_use_id='a', tool_response={'resolvedModel': 'claude-haiku-5-5'})
        self.call('PostToolUse', tool_use_id='a', tool_response={'content': [{'type': 'text', 'text': '{"agent_id":"kid"}'}]})
        self.call('SubagentStop', agent_id='kid', turn_id='r', model='gpt-6-luna')
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            engine.report('7d')
        text = out.getvalue()
        self.assertIn('| claude | /project | 1 | 0 | 0 | 0 | 0 |', text)
        self.assertIn('| codex | /project | 1 | 0 | 0 | 0 | 0 |', text)
        self.assertNotIn('small opus', text)

    def test_unknown_model_stays_unresolved(self):
        self.begin()
        self.agent(role='fast')
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            engine.report('7d')
        self.assertIn('| codex | /project | 0 | 0 | 0 | 0 | 1 |', out.getvalue())

    def test_failure_and_balanced_fallback(self):
        self.begin()
        self.agent(role='fast')
        self.call('PostToolUse', tool_use_id='a', tool_response={'isError': True, 'error': 'model unavailable'})
        self.agent('fallback', role='balanced')
        self.assertTrue(any(r['event'] == 'failure' and r['tier'] == 'fast' for r in self.rows()))
        self.assertTrue(any(r['event'] == 'fallback' and r['to_tier'] == 'balanced' for r in self.rows()))

    def test_explicit_main_model_is_preserved(self):
        self.begin()
        self.call('Stop', turn_id='r', model='gpt-6-astra')
        self.assertEqual(self.rows()[-1]['tier'], 'deep')
        self.assertEqual(self.rows()[-1]['model'], 'gpt-6-astra')

    def test_no_silent_older_model_substitution(self):
        self.begin()
        denied = self.agent(model='gpt-5.6-sol')
        self.assertIn('Older model substitution', denied['hookSpecificOutput']['permissionDecisionReason'])
        self.assertEqual(self.rows(), [])

    def test_background_completion_preserves_request_budget(self):
        self.begin()
        self.agent()
        self.call('Stop', turn_id='r')
        self.call('UserPromptSubmit', turn_id='notification', prompt='<task-notification>completed</task-notification>')
        self.assertIn('deny', json.dumps(self.agent('retry')))
        blocked = self.rows()[-1]
        self.assertEqual(blocked['request_id'], 'r')
        self.call('Stop', turn_id='notification')
        self.begin('next-user')
        self.assertIsNone(self.agent('next'))


if __name__ == '__main__':
    unittest.main()
