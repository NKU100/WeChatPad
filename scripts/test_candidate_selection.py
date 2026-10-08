import copy
import unittest
import io
from contextlib import redirect_stderr
import hashlib
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from scripts.ci.candidate_selection import replay_report, main


class CandidateSelectionTest(unittest.TestCase):
    def setUp(self):
        self.profile = {'identity': {'versionName': '8.0.78', 'versionCode': 3180,
                                     'apkSha256': 'a' * 64},
                        'sourceUrl': 'https://dldir1v6.qq.com/weixin/android/weixin8078android3180_arm64.apk',
                        'verificationStatus': 'runtime-verified-local'}

    def test_cli_rejects_explicit_version_selection(self):
        error = io.StringIO()
        with redirect_stderr(error), patch('sys.argv', ['candidate_selection', '--version', '8.0.78', '--directory', '/tmp/unused']):
            with self.assertRaises(SystemExit) as failure:
                main()
        self.assertEqual(failure.exception.code, 2)
        self.assertIn("unrecognized arguments: --version", error.getvalue())

    def test_replay_requires_an_exact_registered_artifact(self):
        report = replay_report([self.profile], self.profile['sourceUrl'], 'a' * 64)
        self.assertEqual(report['checkedVersions'], ['8.0.78'])
        self.assertEqual(report['status'], 'STATIC_VERIFIED_PENDING_RUNTIME')
        self.assertEqual(self.profile['verificationStatus'], 'runtime-verified-local')
        with self.assertRaisesRegex(ValueError, 'not registered'):
            replay_report([self.profile], self.profile['sourceUrl'], 'b' * 64)

    def test_static_only_profile_cannot_be_replayed_as_supported(self):
        profile = copy.deepcopy(self.profile)
        profile['verificationStatus'] = 'static-verified'
        with self.assertRaisesRegex(ValueError, 'runtime-verified'):
            replay_report([profile], profile['sourceUrl'], 'a' * 64)

    def test_latest_unknown_build_does_not_fall_back_to_registered_version(self):
        latest = 'https://dldir1v6.qq.com/weixin/android/weixin8079android3200_arm64.apk'
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = root / 'targets.json'
            manifest.write_text(json.dumps([self.profile]))
            with patch('sys.argv', ['candidate_selection', '--targets', str(manifest), '--directory', str(root / 'inputs')]), patch('scripts.ci.candidate_selection.fetch_official_page', return_value=latest):
                with self.assertRaisesRegex(ValueError, 'Latest official APK is not runtime-verified'):
                    main()
            self.assertFalse((root / 'inputs/wechat.apk').exists())

    def test_replay_cli_reuses_verified_cache_and_writes_inputs(self):
        body = b'cached official artifact'
        digest = hashlib.sha256(body).hexdigest()
        profile = copy.deepcopy(self.profile)
        profile['identity']['apkSha256'] = digest
        remote = {'content_length': len(body), 'last_modified': 'Wed, 07 Oct 2026 00:00:00 GMT', 'etag': ''}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = root / 'targets.json'
            manifest.write_text(json.dumps([profile]))
            cache = root / 'cache'
            cache.mkdir()
            (cache / (digest + '.apk')).write_bytes(body)
            (cache / 'candidate.json').write_text(json.dumps(dict(remote, url=profile['sourceUrl'], sha256=digest)))
            with patch('sys.argv', ['candidate_selection', '--targets', str(manifest), '--directory', str(root)]), patch('scripts.ci.candidate_selection.fetch_official_page', return_value=profile['sourceUrl']), patch('scripts.ci.candidate_selection.remote_metadata', return_value=remote):
                main()
            self.assertEqual((root / 'wechat.apk').read_bytes(), body)
            self.assertEqual(json.loads((root / 'candidate-report.json').read_text())['identity']['versionName'], '8.0.78')
