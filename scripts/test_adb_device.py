import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class AdbDeviceTest(unittest.TestCase):
    def test_device_command_uses_fixed_serial_and_socket(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tools = root / 'platform-tools'
            tools.mkdir()
            adb = tools / 'adb'
            adb.write_text('#!/usr/bin/env python3\nimport os,sys,json\nprint(json.dumps({"socket":os.environ["ADB_SERVER_SOCKET"],"args":sys.argv[1:]}))\n')
            adb.chmod(0o755)
            env = dict(os.environ, ANDROID_HOME=str(root), WECHATPAD_ADB_SOCKET=str(root / 'adb.sock'),
                       WECHATPAD_ADB_SERIAL='emulator-5554')
            result = subprocess.check_output(['bash', 'scripts/ci/adb-device.sh', 'shell', 'id'], env=env, text=True)
            parsed = json.loads(result)
            self.assertEqual('localfilesystem:' + str(root / 'adb.sock'), parsed['socket'])
            self.assertEqual(['-s', 'emulator-5554', 'shell', 'id'], parsed['args'])

    def test_server_commands_and_device_overrides_are_rejected(self):
        env = dict(os.environ, WECHATPAD_ADB_SOCKET='/unused', WECHATPAD_ADB_SERIAL='emulator-5554')
        for command in ['kill-server', 'start-server', 'connect', '-s', '-H', '-P', '-L']:
            result = subprocess.run(['bash', 'scripts/ci/adb-device.sh', command], env=env, capture_output=True)
            self.assertEqual(2, result.returncode)


if __name__ == '__main__':
    unittest.main()
