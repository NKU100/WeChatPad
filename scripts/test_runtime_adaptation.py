import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from scripts.ci import runtime_adaptation as runtime
from scripts.ci.codex_adaptation import sha256


class RuntimeAdaptationTest(unittest.TestCase):
    def setUp(self):
        for name in ['ROOT', 'EVIDENCE', 'stage']:
            original = getattr(runtime.smoke, name)
            self.addCleanup(setattr, runtime.smoke, name, original)

    def test_initializer_refuses_a_physical_or_additional_device_before_setup(self):
        for devices in ['List of devices attached\nphone\tdevice\n',
                        'List of devices attached\nemulator-5554\tdevice\nphone\tdevice\n']:
            with patch.object(runtime.subprocess, 'check_output', return_value=devices), patch.object(runtime.smoke, 'main') as setup:
                with self.assertRaisesRegex(RuntimeError, 'exactly one disposable'):
                    runtime.initialize(Path('/unused'), Path('/unused'), 'emulator-5554')
                setup.assert_not_called()

    def test_runtime_failure_copies_evidence_for_same_goal_feedback(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / 'task'
            workspace = root / 'checkout'
            device = root / 'device'
            directory.mkdir(); device.mkdir()
            apk = workspace / 'app/build/outputs/apk/debug/app-debug.apk'
            apk.parent.mkdir(parents=True); apk.write_bytes(b'module')
            wechat = device / 'wechat.apk'; wechat.write_bytes(b'official')
            state = {'worktree': str(workspace), 'report': {'identity': {'apkSha256': sha256(wechat)}},
                     'runtime': {'root': str(device), 'socket': str(root / 'socket'), 'serial': 'emulator-5554'}}
            (directory / 'state.json').write_text(json.dumps(state))
            def probe(mode):
                self.assertEqual('probe', mode)
                (runtime.smoke.EVIDENCE / 'smoke-report.json').write_text(json.dumps({
                    'status': 'FAILED', 'reason': 'No tablet login choice', 'apkSha256': sha256(wechat)}))
                (runtime.smoke.EVIDENCE / 'failure.xml').write_text('<hierarchy/>')
                return 1
            with patch.dict('os.environ'), patch.object(runtime.smoke, 'adb', return_value=MagicMock(stdout=b'installed', stderr=b'')), patch.object(runtime.smoke, 'reboot'), patch.object(runtime.smoke, 'configure_manager'), patch.object(runtime.smoke, 'main', side_effect=probe):
                with self.assertRaisesRegex(ValueError, 'Independent AVD verification failed'):
                    runtime.verify_runtime(directory)
            self.assertTrue((workspace / 'work/analysis/runtime/iteration-001/failure.xml').exists())
            self.assertEqual(sha256(apk), json.loads((directory / 'runtime-report.json').read_text())['moduleApkSha256'])


if __name__ == '__main__':
    unittest.main()
