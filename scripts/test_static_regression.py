import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts.ci.static_regression import registered_window, ensure_apk, check_apk


class StaticRegressionTest(unittest.TestCase):
    def test_window_uses_three_highest_supported_builds(self):
        profiles = [{'identity': {'packageName': 'com.tencent.mm', 'abi': 'arm64-v8a', 'versionCode': n,
                                  'versionName': f'8.0.{n}', 'apkSha256': f'{n:064x}',
                                  'signerSha256': '0fe4ff85c215918396dadc7cd8ce6963339af33d37751a56e54c7206b63a3c7c'},
                     'sourceUrl': f'https://dldir1v6.qq.com/weixin/android/test{n}.apk',
                     'hooks': [{'id': 'tablet'}, {'id': 'login'}], 'verificationStatus': status}
                    for n, status in [(1, 'runtime-verified-local'), (4, 'static-verified'),
                                      (2, 'runtime-verified-hosted'), (3, 'runtime-verified-local'),
                                      (5, 'runtime-verified-hosted')]]
        self.assertEqual([5, 3, 2], [p['identity']['versionCode'] for p in registered_window(profiles)])

    def test_cache_is_rehashed_and_corruption_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            digest = hashlib.sha256(b'apk').hexdigest()
            profile = {'identity': {'packageName': 'com.tencent.mm', 'abi': 'arm64-v8a', 'apkSha256': digest}, 'sourceUrl': 'https://dldir1v6.qq.com/weixin/android/test.apk'}
            path = Path(root) / (digest + '.apk')
            path.write_bytes(b'apk')
            self.assertEqual(path, ensure_apk(profile, Path(root)))
            path.write_bytes(b'bad')
            with patch('scripts.ci.static_regression.download_candidate', return_value=(path, digest, False, {})), patch('scripts.ci.static_regression.remote_metadata', return_value={}):
                with self.assertRaises(ValueError):
                    ensure_apk(profile, Path(root))

    def test_checker_rejects_changed_apk_before_running_gradle(self):
        with tempfile.TemporaryDirectory() as root:
            apk = Path(root) / 'wechat.apk'
            apk.write_bytes(b'bad')
            with patch('scripts.ci.static_regression.subprocess.run') as run:
                with self.assertRaises(ValueError):
                    check_apk(Path(root), Path('targets.json'), apk, '0' * 64, Path(root) / 'log')
                run.assert_not_called()
