import copy
import json
import subprocess
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

from scripts.ci.codex_adaptation import candidate_key, eligible_candidate, validate_profiles, validate_paths, run_bounded, validate_existing_tests, sha256


class CodexAdaptationTest(unittest.TestCase):
    def setUp(self):
        self.targets = json.loads(Path('compatibility/targets.json').read_text())
        self.identity = dict(self.targets[-1]['identity'], versionName='8.0.80', versionCode=3220, apkSha256='a' * 64)
        self.report = {'identity': self.identity, 'status': 'NEEDS_HOOK_REVIEW',
                       'sourceUrl': 'https://dldir1v6.qq.com/weixin/android/weixin8080android3220_arm64.apk'}
        self.profile = copy.deepcopy(self.targets[-1])
        self.profile.update(identity=self.identity, sourceUrl=self.report['sourceUrl'], verificationStatus='static-verified')

    def test_unknown_verified_candidate_can_run_even_when_static_inference_passed(self):
        self.assertTrue(eligible_candidate(self.report, self.targets))
        self.report['status'] = 'STATIC_VERIFIED_PENDING_RUNTIME'
        self.assertTrue(eligible_candidate(self.report, self.targets))
        self.assertEqual('3220-' + 'a' * 64, candidate_key(self.report))

    def test_older_unknown_build_cannot_bypass_the_latest_only_gate(self):
        self.report['identity'].update(versionName='8.0.78', versionCode=3180)
        self.report['manualSelection'] = True
        with self.assertRaisesRegex(ValueError, 'newer'):
            eligible_candidate(self.report, self.targets)

    def test_hosted_verified_profile_is_a_trusted_baseline(self):
        self.targets[-1]['verificationStatus'] = 'runtime-verified-hosted'
        self.assertTrue(eligible_candidate(self.report, self.targets))

    def test_known_version_or_rejected_identity_does_not_consume_model_usage(self):
        self.report['identity'] = self.targets[-1]['identity']
        self.assertFalse(eligible_candidate(self.report, self.targets))
        self.report['identity'] = self.identity
        self.report['status'] = 'IDENTITY_REJECTED'
        self.assertFalse(eligible_candidate(self.report, self.targets))

    def test_eligibility_rechecks_package_signer_and_source(self):
        for field, value in [('packageName', 'other.app'), ('signerSha256', 'b' * 64), ('abi', 'x86_64')]:
            report = copy.deepcopy(self.report)
            report['identity'][field] = value
            with self.assertRaises(ValueError):
                eligible_candidate(report, self.targets)
        self.report['sourceUrl'] = 'https://example.com/app.apk'
        with self.assertRaises(ValueError):
            eligible_candidate(self.report, self.targets)

    def test_candidate_profile_is_static_only_and_preserves_every_old_profile(self):
        validate_profiles(self.targets, self.targets + [self.profile], self.report)
        changed = copy.deepcopy(self.targets + [self.profile])
        changed[0]['hooks'][0]['expectedDescriptor'] = 'changed'
        with self.assertRaisesRegex(ValueError, 'existing'):
            validate_profiles(self.targets, changed, self.report)
        self.profile['verificationStatus'] = 'runtime-verified-local'
        with self.assertRaisesRegex(ValueError, 'static-verified'):
            validate_profiles(self.targets, self.targets + [self.profile], self.report)

    def test_agent_cannot_register_wrong_identity_or_change_validators(self):
        self.profile['identity'] = dict(self.identity, apkSha256='c' * 64)
        with self.assertRaisesRegex(ValueError, 'identity'):
            validate_profiles(self.targets, self.targets + [self.profile], self.report)
        validate_paths(['compatibility/targets.json', 'compat-core/src/main/kotlin/Hook.kt'])
        for path in ['.github/workflows/build.yml', 'scripts/ci/codex_adaptation.py', 'gradle.properties', 'compat-checker/src/main/kotlin/Main.kt']:
            with self.assertRaisesRegex(ValueError, 'allowed'):
                validate_paths([path])

    def test_model_has_no_custom_execution_timeout(self):
        with tempfile.TemporaryDirectory() as temp, patch('scripts.ci.codex_adaptation.subprocess.Popen') as launch:
            process = MagicMock()
            process.wait.return_value = 0
            launch.return_value = process
            run_bounded(['codex'], Path(temp), {}, Path(temp) / 'output')
            process.wait.assert_called_once_with(timeout=None)

    def test_explicit_timeout_stops_a_bounded_command(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(TimeoutError):
                run_bounded(['python3', '-c', 'import time; time.sleep(30)'], Path(temp), {}, Path(temp) / 'output', timeout=0.1)

    def test_agent_cannot_weaken_or_delete_existing_regression_tests(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            test = root / 'Test.kt'
            test.write_text('assert rejects ambiguous Hook')
            original = {'Test.kt': sha256(test)}
            validate_existing_tests(root, original)
            test.write_text('assert true')
            with self.assertRaisesRegex(ValueError, 'regression tests'):
                validate_existing_tests(root, original)
            test.unlink()
            with self.assertRaisesRegex(ValueError, 'regression tests'):
                validate_existing_tests(root, original)


if __name__ == '__main__':
    unittest.main()
