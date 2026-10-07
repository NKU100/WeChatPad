import importlib.util
import json
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch


spec = importlib.util.spec_from_file_location('probe', Path(__file__).parent / 'ci/hosted_smoke_probe.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class HostedProbeTest(unittest.TestCase):
    def run_probe(self, activity, ui):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with zipfile.ZipFile(root / 'wechat.apk', 'w') as apk:
                apk.writestr('lib/arm64-v8a/libtest.so', '')

            def adb(*args, **kwargs):
                output = b''
                if args == ('shell', 'dumpsys', 'activity', 'activities'):
                    output = activity.encode()
                elif args == ('shell', 'cat', '/sdcard/probe-ui.xml'):
                    output = ui.encode()
                return subprocess.CompletedProcess(args, 0, output, b'')

            with patch.object(probe, 'ROOT', root), patch.object(probe, 'EVIDENCE', root / 'evidence'), patch.object(probe, 'adb', adb), patch.object(probe.time, 'sleep'):
                result = probe.main()
            return result, json.loads((root / 'evidence/environment-report.json').read_text())

    def test_splash_activity_and_launcher_ui_are_not_running_wechat(self):
        result, report = self.run_probe(
            'topResumedActivity=ActivityRecord{ com.tencent.mm/.app.WeChatSplashActivity }',
            '<hierarchy><node package="com.google.android.apps.nexuslauncher" /></hierarchy>')
        self.assertEqual(1, result)
        self.assertEqual('ARM_APK_LAUNCH_FAILED', report['status'])

    def test_login_activity_and_wechat_ui_pass(self):
        result, report = self.run_probe(
            'topResumedActivity=ActivityRecord{ com.tencent.mm/.plugin.account.ui.MobileInputUI }',
            '<hierarchy><node package="com.tencent.mm" /></hierarchy>')
        self.assertEqual(0, result)
        self.assertEqual('ARM_APK_RUNNING', report['status'])


if __name__ == '__main__':
    unittest.main()
