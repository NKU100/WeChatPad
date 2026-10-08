import copy
import unittest
import json
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch
from scripts.ci.runtime_task import runtime_result, main


class RuntimeTaskTest(unittest.TestCase):
    def setUp(self):
        self.report = {'status': 'STATIC_VERIFIED_PENDING_RUNTIME',
                       'identity': {'versionName': '8.0.79', 'versionCode': 3200, 'apkSha256': 'a' * 64},
                       'suggestedProfile': {'identity': {'versionName': '8.0.79', 'versionCode': 3200, 'apkSha256': 'a' * 64},
                                            'verificationStatus': 'static-verified'}}
        self.report['sourceUrl'] = 'https://dldir1v6.qq.com/weixin/android/test.apk'
        self.smoke = {'status': 'RUNTIME_SMOKE_VERIFIED', 'baseline': 'NO_TABLET_ENTRY',
                      'hooks': 2, 'qrPage': 'LoginAsExDeviceUI',
                      'apkSha256': 'a' * 64}

    def test_success_promotes_only_matching_candidate_and_preserves_input(self):
        original = copy.deepcopy(self.report)
        result = runtime_result(self.report, self.smoke, 'success')
        self.assertEqual(result['status'], 'RUNTIME_VERIFIED')
        self.assertEqual(result['suggestedProfile']['verificationStatus'], 'runtime-verified-hosted')
        self.assertEqual(self.report, original)

    def test_failure_or_missing_evidence_cannot_promote(self):
        for evidence, conclusion in [(self.smoke, 'failure'), ({}, 'success'),
                                      (dict(self.smoke, qrPage='Splash'), 'success'),
                                      (dict(self.smoke, apkSha256='b' * 64), 'success')]:
            with self.subTest(evidence=evidence, conclusion=conclusion):
                result = runtime_result(self.report, evidence, conclusion)
                self.assertEqual(result['status'], 'RUNTIME_REJECTED')
                self.assertEqual(result['suggestedProfile']['verificationStatus'], 'static-verified')

    def test_publication_changes_only_manifest_on_the_tested_commit(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            origin = root / 'remote.git'
            checkout = root / 'checkout'
            subprocess.run(['git', 'init', '--bare', '-q', str(origin)], check=True)
            subprocess.run(['git', 'init', '-q', str(checkout)], check=True)
            def git(*args):
                return subprocess.check_output(['git', *args], cwd=checkout).decode().strip()
            git('config', 'user.name', 'test')
            git('config', 'user.email', 'test@example.com')
            git('remote', 'add', 'origin', str(origin))
            (checkout / 'compatibility').mkdir()
            before = {'identity': {'versionCode': 3040}, 'verificationStatus': 'runtime-verified-local'}
            manifest = checkout / 'compatibility/targets.json'
            manifest.write_text(json.dumps([before, self.report['suggestedProfile']]))
            (checkout / 'code.txt').write_text('tested module code')
            git('add', '.')
            git('commit', '-qm', 'test candidate')
            head = git('rev-parse', 'HEAD')
            git('push', '-q', 'origin', 'HEAD:refs/heads/adapt/test')
            directory = checkout / 'result'
            directory.mkdir()
            (directory / 'candidate-report.json').write_text(json.dumps(self.report))
            evidence = directory / 'smoke.json'
            evidence.write_text(json.dumps(self.smoke))
            env = {'GITHUB_REPOSITORY': 'owner/repo', 'GITHUB_RUN_ID': '1',
                   'GITHUB_OUTPUT': str(root / 'output'), 'GITHUB_STEP_SUMMARY': str(root / 'summary')}
            pr = {'headRefOid': head, 'headRefName': 'adapt/test', 'state': 'OPEN', 'body': 'Static checks passed'}
            previous = Path.cwd()
            try:
                os.chdir(checkout)
                with patch.dict(os.environ, env), patch('sys.argv', ['runtime_task', '--directory', str(directory),
                           '--smoke', str(evidence), '--conclusion', 'success', '--pr', 'https://github.com/owner/repo/pull/1',
                           '--head', head, '--issue', '2']), patch('scripts.ci.runtime_task.gh', side_effect=[json.dumps(pr), '', '']), patch('scripts.ci.runtime_task.write_issue'):
                    main()
            finally:
                os.chdir(previous)
            git('fetch', '-q', 'origin', 'adapt/test')
            promoted = json.loads(git('show', 'FETCH_HEAD:compatibility/targets.json'))
            self.assertEqual(promoted[0], before)
            self.assertEqual(promoted[1]['verificationStatus'], 'runtime-verified-hosted')
            self.assertEqual(git('diff', '--name-only', head, 'FETCH_HEAD'), 'compatibility/targets.json')
            self.assertEqual(git('rev-parse', 'FETCH_HEAD^'), head)

    def test_changed_pr_head_cannot_be_promoted(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'candidate-report.json').write_text(json.dumps(self.report))
            (root / 'smoke.json').write_text(json.dumps(self.smoke))
            pr = {'headRefOid': 'changed', 'headRefName': 'adapt/test', 'state': 'OPEN', 'body': ''}
            env = {'GITHUB_REPOSITORY': 'owner/repo', 'GITHUB_RUN_ID': '1'}
            with patch.dict(os.environ, env), patch('sys.argv', ['runtime_task', '--directory', str(root),
                      '--smoke', str(root / 'smoke.json'), '--conclusion', 'success', '--pr', '1',
                      '--head', 'tested', '--issue', '2']), patch('scripts.ci.runtime_task.gh', return_value=json.dumps(pr)), patch('scripts.ci.runtime_task.subprocess.run') as git:
                with self.assertRaisesRegex(ValueError, 'changed or closed'):
                    main()
                git.assert_not_called()

    def test_requires_static_verification(self):
        self.report['status'] = 'NEEDS_HOOK_REVIEW'
        with self.assertRaises(ValueError):
            runtime_result(self.report, self.smoke, 'success')
