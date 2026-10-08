import unittest
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch
from scripts.ci.codex_task import existing_attempt, retry_allowed, claim


def record(status='NEEDS_HOOK_REVIEW'):
    return {'number': 3, 'state': 'closed', 'user': {'login': 'github-actions[bot]', 'type': 'Bot'},
            'labels': [{'name': 'wechatpad-adaptation'}],
            'body': '<!-- wechatpad-adaptation:3200-abc -->\nStatus: `' + status + '`'}


class CodexTaskTest(unittest.TestCase):
    def test_closed_failed_attempt_prevents_automatic_retry(self):
        issue = record()
        self.assertEqual(issue, existing_attempt([issue], '3200-abc'))

    def test_untrusted_author_missing_label_and_pr_are_ignored(self):
        for change in [{'user': {'login': 'stranger', 'type': 'User'}}, {'labels': []}, {'pull_request': {}}]:
            issue = record()
            issue.update(change)
            self.assertIsNone(existing_attempt([issue], '3200-abc'))

    def test_other_build_or_partial_hash_does_not_block_candidate(self):
        self.assertIsNone(existing_attempt([record()], '3200-ab'))

    def test_retry_requires_failed_or_inconclusive_attempt(self):
        self.assertTrue(retry_allowed(record(), None))
        self.assertTrue(retry_allowed(record('ADAPTATION_RUNNING'), {'status': 'completed', 'conclusion': 'cancelled'}))
        self.assertFalse(retry_allowed(record('ADAPTATION_RUNNING'), {'status': 'in_progress', 'conclusion': None}))
        self.assertFalse(retry_allowed(record('WAITING_RUNTIME'), {'status': 'completed', 'conclusion': 'failure'}))
        self.assertFalse(retry_allowed(record('RUNTIME_VERIFIED'), None))

    def test_manual_retry_reuses_issue_and_automatic_run_does_not_restart(self):
        for retry in [False, True]:
            issue = record()
            calls = []
            def fake_gh(*args):
                calls.append(args)
                if args[:2] == ('api', '--paginate'):
                    return json.dumps([[issue]])
                return ''
            with tempfile.TemporaryDirectory() as root:
                output = Path(root) / 'output'
                with patch('scripts.ci.codex_task.eligible_candidate', return_value=True), patch('scripts.ci.codex_task.candidate_key', return_value='3200-abc'), patch('scripts.ci.codex_task.gh', side_effect=fake_gh), patch('scripts.ci.codex_task.issue_body', return_value='running'), patch.dict(os.environ, {'GITHUB_OUTPUT': str(output)}):
                    claim('owner/repo', {}, [], Path(root), 'run', retry=retry)
                self.assertIn('claimed=' + str(retry).lower(), output.read_text())
                self.assertFalse(any(call[:2] == ('issue', 'create') for call in calls))
                self.assertEqual(retry, any(call[:2] == ('issue', 'reopen') for call in calls))

    def test_pending_pr_never_starts_another_model_attempt(self):
        issue = record('WAITING_RUNTIME')
        issue['body'] += '\nAdaptation PR: https://github.com/owner/repo/pull/7'
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / 'output'
            def fake_gh(*args):
                return json.dumps([[issue]]) if args[:2] == ('api', '--paginate') else ''
            with patch('scripts.ci.codex_task.eligible_candidate', return_value=True), patch('scripts.ci.codex_task.candidate_key', return_value='3200-abc'), patch('scripts.ci.codex_task.gh', side_effect=fake_gh), patch.dict(os.environ, {'GITHUB_OUTPUT': str(output)}):
                claim('owner/repo', {}, [], Path(root), 'run', retry=True)
            self.assertIn('claimed=false', output.read_text())

    def test_public_issue_cannot_claim_the_build(self):
        issue = record()
        issue['user'] = {'login': 'stranger', 'type': 'User'}
        calls = []
        def fake_gh(*args):
            calls.append(args)
            if args[:2] == ('api', '--paginate'):
                return json.dumps([[issue]])
            if args[:2] == ('issue', 'create'):
                return 'https://github.com/owner/repo/issues/4'
            return ''
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / 'output'
            report = {'identity': {'versionName': '8.0.79'}}
            with patch('scripts.ci.codex_task.eligible_candidate', return_value=True), patch('scripts.ci.codex_task.candidate_key', return_value='3200-abc'), patch('scripts.ci.codex_task.issue_body', return_value='running'), patch('scripts.ci.codex_task.gh', side_effect=fake_gh), patch.dict(os.environ, {'GITHUB_OUTPUT': str(output)}):
                claim('owner/repo', report, [], Path(root), 'run')
            self.assertIn('claimed=true', output.read_text())
            self.assertIn('issue=4', output.read_text())
            self.assertTrue(any(call[:2] == ('issue', 'create') and '--label' in call for call in calls))


if __name__ == '__main__':
    unittest.main()
