import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from scripts.ci.adb_relay import DeviceRelay, validate_request


class AdbDeviceTest(unittest.TestCase):
    def test_device_command_uses_fixed_serial_and_socket(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tools = root / 'platform-tools'
            tools.mkdir()
            adb = tools / 'adb'
            adb.write_text('#!/usr/bin/env python3\nimport os,sys,json\nprint(json.dumps({"socket":os.environ["ADB_SERVER_SOCKET"],"args":sys.argv[1:]}))\n')
            adb.chmod(0o755)
            (root / 'state.json').write_text(json.dumps({'worktree': str(root), 'runtime': {'socket': str(root / 'adb.sock'), 'serial': 'emulator-5554'}}))
            env = dict(os.environ, ANDROID_HOME=str(root))
            relay = DeviceRelay(root, env)
            env['WECHATPAD_ADB_RELAY'] = str(relay.root)
            try:
                result = subprocess.check_output(['bash', str(Path('scripts/ci/adb-device.sh').resolve()), 'shell', 'id'], env=env, text=True, cwd=root)
            finally:
                relay.close()
            parsed = json.loads(result)
            self.assertEqual('localfilesystem:' + str(root / 'adb.sock'), parsed['socket'])
            self.assertEqual(['-s', 'emulator-5554', 'shell', 'id'], parsed['args'])

    def test_server_commands_and_device_overrides_are_rejected(self):
        env = dict(os.environ, WECHATPAD_ADB_RELAY='/unused')
        for command in ['kill-server', 'start-server', 'connect', '-s', '-H', '-P', '-L']:
            result = subprocess.run(['bash', 'scripts/ci/adb-device.sh', command], env=env, capture_output=True)
            self.assertEqual(2, result.returncode)

    def test_host_rejects_server_overrides_and_outside_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary).resolve()
            commands = [['-s', 'physical', 'shell'], ['kill-server'],
                        ['install', '/etc/passwd'], ['push', '../secret', '/sdcard/secret'],
                        ['pull', '/sdcard/file', '../outside']]
            for args in commands:
                with self.subTest(args=args), self.assertRaises(ValueError):
                    validate_request({'cwd': str(workspace), 'args': args}, workspace)

    def test_relay_preserves_binary_output_and_exit_status(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tools = root / 'platform-tools'
            tools.mkdir()
            adb = tools / 'adb'
            adb.write_text('#!/usr/bin/env python3\nimport sys\nsys.stdout.buffer.write(bytes([0,255,10]))\nsys.stderr.write("device error")\nsys.exit(7)\n')
            adb.chmod(0o755)
            (root / 'state.json').write_text(json.dumps({'worktree': str(root), 'runtime': {'socket': str(root / 'adb.sock'), 'serial': 'emulator-5554'}}))
            env = dict(os.environ, ANDROID_HOME=str(root))
            relay = DeviceRelay(root, env)
            try:
                result = subprocess.run(['bash', str(Path('scripts/ci/adb-device.sh').resolve()), 'exec-out', 'screencap', '-p'],
                                        env=dict(env, WECHATPAD_ADB_RELAY=str(relay.root)), capture_output=True, cwd=root)
            finally:
                relay.close()
            self.assertEqual(7, result.returncode)
            self.assertEqual(bytes([0,255,10]), result.stdout)
            self.assertEqual(b'device error', result.stderr)


if __name__ == '__main__':
    unittest.main()
