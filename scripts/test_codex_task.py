import unittest
import json
import os
import tempfile
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from scripts.ci.codex_task import existing_attempt, retry_allowed, claim


def record(status='NEEDS_HOOK_REVIEW', label='impad-adaptation', marker='impad-adaptation'):
    return {'number': 3, 'state': 'closed', 'user': {'login': 'github-actions[bot]', 'type': 'Bot'},
            'labels': [{'name': label}],
            'body': f'<!-- {marker}:3200-abc -->\nStatus: `{status}`'}


def candidate_report():
    return {'appId': 'wechat', 'identity': {'packageName': 'com.tencent.mm', 'versionName': '8.0.79'}}


class CodexTaskTest(unittest.TestCase):
    def test_issue_copy_uses_the_selected_application_display_name(self):
        from scripts.ci import codex_task
        from scripts.ci import app_policy
        policy = replace(codex_task.get_policy(), app_id='qq', display_name='QQ')
        report = {'appId': 'qq', 'identity': {'packageName': policy.package_name, 'abi': policy.supported_abis[0],
                                                'versionName': '9.1', 'versionCode': 91, 'apkSha256': 'a' * 64},
                  'sourceUrl': 'https://example.invalid/qq.apk'}
        with patch.dict(app_policy.POLICIES, {'qq': policy}):
            body = codex_task.issue_body(report, 'ADAPTATION_RUNNING', 'https://example.invalid/run')
        self.assertIn('QQ 9.1 (91)', body)
        self.assertNotIn('WeChat 9.1', body)

    def test_closed_failed_attempt_prevents_automatic_retry(self):
        issue = record()
        self.assertEqual(issue, existing_attempt([issue], '3200-abc'))

    def test_legacy_label_and_marker_still_match_the_full_candidate_key(self):
        issue = record(label='wechatpad-adaptation', marker='wechatpad-adaptation')
        self.assertEqual(issue, existing_attempt([issue], '3200-abc'))
        self.assertIsNone(existing_attempt([issue], '3200-ab'))

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
        self.assertTrue(retry_allowed(record('WAITING_RUNTIME'), None))
        self.assertTrue(retry_allowed(record('RUNTIME_REJECTED'), None))
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
                    claim('owner/repo', candidate_report(), [], Path(root), 'run', retry=retry)
                self.assertIn('claimed=' + str(retry).lower(), output.read_text())
                self.assertFalse(any(call[:2] == ('issue', 'create') for call in calls))
                self.assertEqual(retry, any(call[:2] == ('issue', 'reopen') for call in calls))

    def test_legacy_attempt_is_reused_without_automatic_model_run(self):
        issue = record(label='wechatpad-adaptation', marker='wechatpad-adaptation')
        calls = []
        def fake_gh(*args):
            calls.append(args)
            return json.dumps([[issue]]) if args[:2] == ('api', '--paginate') else ''
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / 'output'
            with patch('scripts.ci.codex_task.eligible_candidate', return_value=True), \
                    patch('scripts.ci.codex_task.candidate_key', return_value='3200-abc'), \
                    patch('scripts.ci.codex_task.gh', side_effect=fake_gh), \
                    patch.dict(os.environ, {'GITHUB_OUTPUT': str(output)}):
                claim('owner/repo', candidate_report(), [], Path(root), 'run', retry=False)
            self.assertIn('claimed=false', output.read_text())
            self.assertIn('issue=3', output.read_text())
            self.assertFalse(any(call[:2] == ('issue', 'create') for call in calls))

    def test_explicit_retry_reuses_legacy_attempt_and_keeps_retry_policy(self):
        issue = record(status='WAITING_RUNTIME', label='wechatpad-adaptation', marker='wechatpad-adaptation')
        calls = []
        def fake_gh(*args):
            calls.append(args)
            return json.dumps([[issue]]) if args[:2] == ('api', '--paginate') else ''
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / 'output'
            with patch('scripts.ci.codex_task.eligible_candidate', return_value=True), \
                    patch('scripts.ci.codex_task.candidate_key', return_value='3200-abc'), \
                    patch('scripts.ci.codex_task.gh', side_effect=fake_gh), \
                    patch('scripts.ci.codex_task.issue_body', return_value='running'), \
                    patch.dict(os.environ, {'GITHUB_OUTPUT': str(output)}):
                claim('owner/repo', candidate_report(), [], Path(root), 'run', retry=True)
            self.assertIn('claimed=true', output.read_text())
            self.assertTrue(any(call[:2] == ('issue', 'edit') for call in calls))
            self.assertFalse(any(call[:2] == ('issue', 'create') for call in calls))

    def test_renamed_repo_accepts_failed_run_url_from_legacy_repo(self):
        issue = record(status='ADAPTATION_RUNNING', label='wechatpad-adaptation', marker='wechatpad-adaptation')
        issue['body'] += '\nRun: https://github.com/NKU100/WeChatPad/actions/runs/12345\n'
        calls = []
        def fake_gh(*args):
            calls.append(args)
            if args[:2] == ('api', '--paginate'):
                return json.dumps([[issue]])
            if args[:2] == ('api', 'repos/NKU100/ImPad/actions/runs/12345'):
                return json.dumps({'status': 'completed', 'conclusion': 'failure'})
            return ''
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / 'output'
            with patch('scripts.ci.codex_task.eligible_candidate', return_value=True), \
                    patch('scripts.ci.codex_task.candidate_key', return_value='3200-abc'), \
                    patch('scripts.ci.codex_task.gh', side_effect=fake_gh), \
                    patch('scripts.ci.codex_task.issue_body', return_value='running'), \
                    patch.dict(os.environ, {'GITHUB_OUTPUT': str(output)}):
                claim('NKU100/ImPad', candidate_report(), [], Path(root), 'run', retry=True)
            self.assertIn('claimed=true', output.read_text())
            self.assertTrue(any(call[:2] == ('api', 'repos/NKU100/ImPad/actions/runs/12345') for call in calls))
            self.assertTrue(any(call[:2] == ('issue', 'reopen') for call in calls))
            self.assertFalse(any(call[:2] == ('issue', 'create') for call in calls))

    def test_retry_rejects_action_run_url_from_unrelated_repository(self):
        issue = record(status='ADAPTATION_RUNNING', label='wechatpad-adaptation', marker='wechatpad-adaptation')
        issue['body'] += '\nRun: https://github.com/Other/WeChatPad/actions/runs/12345\n'
        calls = []
        def fake_gh(*args):
            calls.append(args)
            return json.dumps([[issue]]) if args[:2] == ('api', '--paginate') else ''
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / 'output'
            with patch('scripts.ci.codex_task.eligible_candidate', return_value=True), \
                    patch('scripts.ci.codex_task.candidate_key', return_value='3200-abc'), \
                    patch('scripts.ci.codex_task.gh', side_effect=fake_gh), \
                    patch('scripts.ci.codex_task.issue_body', return_value='running'), \
                    patch.dict(os.environ, {'GITHUB_OUTPUT': str(output)}):
                claim('NKU100/ImPad', candidate_report(), [], Path(root), 'run', retry=True)
            self.assertIn('claimed=false', output.read_text())
            self.assertFalse(any(call[:2] == ('api', 'repos/NKU100/ImPad/actions/runs/12345') for call in calls))
            self.assertFalse(any(call[:2] == ('issue', 'create') or call[:2] == ('issue', 'reopen') for call in calls))

    def test_conflicting_legacy_and_current_records_fail_closed(self):
        issues = [record(), record(label='wechatpad-adaptation', marker='wechatpad-adaptation')]
        calls = []
        def fake_gh(*args):
            calls.append(args)
            return json.dumps([issues]) if args[:2] == ('api', '--paginate') else ''
        with tempfile.TemporaryDirectory() as root:
            with patch('scripts.ci.codex_task.eligible_candidate', return_value=True), \
                    patch('scripts.ci.codex_task.candidate_key', return_value='3200-abc'), \
                    patch('scripts.ci.codex_task.gh', side_effect=fake_gh), \
                    patch.dict(os.environ, {'GITHUB_OUTPUT': str(Path(root) / 'output')}), \
                    self.assertRaisesRegex(ValueError, 'Multiple trusted adaptation records'):
                claim('owner/repo', candidate_report(), [], Path(root), 'run')
        self.assertFalse(any(call[:2] == ('issue', 'create') or call[:2] == ('label', 'create') for call in calls))

    def test_pending_pr_explicit_retry_starts_new_attempt(self):
        issue = record('WAITING_RUNTIME')
        issue['body'] += '\nAdaptation PR: https://github.com/owner/repo/pull/7'
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / 'output'
            def fake_gh(*args):
                return json.dumps([[issue]]) if args[:2] == ('api', '--paginate') else ''
            with patch('scripts.ci.codex_task.eligible_candidate', return_value=True), patch('scripts.ci.codex_task.candidate_key', return_value='3200-abc'), patch('scripts.ci.codex_task.gh', side_effect=fake_gh), patch('scripts.ci.codex_task.issue_body', return_value='running'), patch.dict(os.environ, {'GITHUB_OUTPUT': str(output)}):
                claim('owner/repo', candidate_report(), [], Path(root), 'run', retry=True)
            self.assertIn('claimed=true', output.read_text())

    def test_current_running_attempt_cannot_retry_using_historical_failure(self):
        issue = record('ADAPTATION_RUNNING')
        issue['body'] += '\nPrevious attempt:\nStatus: `NEEDS_HOOK_REVIEW`'
        self.assertFalse(retry_allowed(issue, {'status': 'in_progress', 'conclusion': None}))

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
            report = candidate_report()
            with patch('scripts.ci.codex_task.eligible_candidate', return_value=True), patch('scripts.ci.codex_task.candidate_key', return_value='3200-abc'), patch('scripts.ci.codex_task.issue_body', return_value='running'), patch('scripts.ci.codex_task.gh', side_effect=fake_gh), patch('scripts.ci.codex_task.issue_body', return_value='running'), patch.dict(os.environ, {'GITHUB_OUTPUT': str(output)}):
                claim('owner/repo', report, [], Path(root), 'run')
            self.assertIn('claimed=true', output.read_text())
            self.assertIn('issue=4', output.read_text())
            self.assertTrue(any(call[:2] == ('issue', 'create') and '--label' in call for call in calls))


if __name__ == '__main__':
    unittest.main()
