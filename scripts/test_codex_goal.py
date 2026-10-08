import tempfile
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts.ci.codex_goal import run_goal, redact, write_diagnostics


class FakeClient:
    def __init__(self, status='active'):
        self.calls = []
        self.status = status
        self.turn = 0
    def request(self, method, params):
        self.calls.append((method, params))
        if method == 'command/exec':
            return {'exitCode': 0, 'stdout': 'sandbox ready', 'stderr': ''}
        if method == 'thread/start':
            return {'thread': {'id': 'thread-1'}}
        if method == 'turn/start':
            self.turn += 1
            return {'turn': {'id': str(self.turn)}}
        if method == 'thread/goal/get':
            return {'goal': {'status': self.status, 'tokensUsed': self.turn * 100, 'tokenBudget': 10000}}
        if method == 'thread/read':
            return {'thread': {'turns': []}}
        return {}
    def wait_turn(self, thread, turn):
        return {'status': 'completed'}
    def pause(self, thread):
        self.request('thread/goal/set', {'threadId': thread, 'status': 'paused'})


class GoalTest(unittest.TestCase):
    def test_failed_validation_is_fed_back_to_same_thread(self):
        client = FakeClient()
        with tempfile.TemporaryDirectory() as root, patch('scripts.ci.codex_goal.write_diagnostics'):
            with patch('scripts.ci.codex_goal.verify', side_effect=[ValueError('missing profile'), None]) as verify:
                run_goal(client, Path(root), 'adapt', 10000)
            self.assertEqual(2, verify.call_count)
        turns = [p for m,p in client.calls if m == 'turn/start']
        self.assertEqual(['thread-1', 'thread-1'], [p['threadId'] for p in turns])
        self.assertIn('missing profile', turns[1]['input'][0]['text'])

    def test_model_completion_does_not_bypass_independent_validation(self):
        with tempfile.TemporaryDirectory() as root, patch('scripts.ci.codex_goal.write_diagnostics'), patch('scripts.ci.codex_goal.verify', side_effect=ValueError('missing profile')):
            with self.assertRaisesRegex(RuntimeError, 'three'):
                run_goal(FakeClient('complete'), Path(root), 'adapt', 10000)

    def test_budget_limit_stops_without_another_turn(self):
        client = FakeClient('budgetLimited')
        with tempfile.TemporaryDirectory() as root, patch('scripts.ci.codex_goal.write_diagnostics'), patch('scripts.ci.codex_goal.verify', side_effect=ValueError('missing profile')):
            with self.assertRaisesRegex(RuntimeError, 'budgetLimited'):
                run_goal(client, Path(root), 'adapt', 10000)
        self.assertEqual(1, client.turn)

    def test_sandbox_failure_stops_before_creating_goal_or_spending_tokens(self):
        client = FakeClient()
        def request(method, params):
            client.calls.append((method, params))
            if method == 'command/exec':
                return {'exitCode': 1, 'stderr': 'bwrap: loopback: Operation not permitted'}
            self.fail('A failed sandbox must stop before creating a thread')
        client.request = request
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(RuntimeError, 'Sandbox preflight failed'):
                run_goal(client, Path(root), 'adapt', 10000)
        self.assertEqual(0, client.turn)

    def test_failed_turn_is_not_verified_or_retried(self):
        client = FakeClient()
        with tempfile.TemporaryDirectory() as root, patch('scripts.ci.codex_goal.write_diagnostics'), patch('scripts.ci.codex_goal.verify') as verify, patch.object(client, 'wait_turn', return_value={'status': 'failed', 'error': {'message': 'tool unavailable'}}):
            with self.assertRaisesRegex(RuntimeError, 'turn failed'):
                run_goal(client, Path(root), 'adapt', 10000)
            verify.assert_not_called()
        self.assertEqual(1, client.turn)

    def test_diagnostics_remain_valid_json_after_redaction(self):
        client = FakeClient()
        client.secrets = ['secret-value']
        client.messages = ['Bearer secret-value', 'access_token=secret-value']
        with tempfile.TemporaryDirectory() as root, patch('scripts.ci.codex_goal.auth_secrets', return_value=[]):
            write_diagnostics(Path(root), [{'error': 'secret-value'}], client)
            text = (Path(root) / 'goal-diagnostics.json').read_text()
            report = json.loads(text)
            self.assertNotIn('secret-value', text)
            self.assertEqual('[REDACTED]', report['iterations'][0]['error'])

    def test_known_credentials_and_jwt_are_redacted(self):
        jwt = 'eyJhbGciOiJIUzI1NiJ9.abcdefghijklmno.abcdefghijklmno'
        result = redact('token secret-value ' + jwt, ['secret-value'])
        self.assertNotIn('secret-value', result)
        self.assertNotIn(jwt, result)
