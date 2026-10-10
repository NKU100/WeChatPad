import json
import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/ci/verify_avd_root.sh'
FAKE_ADB = textwrap.dedent('''\
    #!/usr/bin/env python3
    import json
    import os
    import sys
    from pathlib import Path

    state_path = Path(os.environ['FAKE_ADB_STATE'])
    state = json.loads(state_path.read_text())
    args = sys.argv[1:]
    state['calls'].append({'args': args, 'uid': state['uid']})

    def finish(code=0, output=''):
        state_path.write_text(json.dumps(state))
        if output:
            print(output)
        raise SystemExit(code)

    scenario = os.environ['FAKE_ADB_SCENARIO']
    if args == ['root']:
        state['root_attempts'] += 1
        if scenario == 'unauthorized':
            finish(1, 'adbd cannot run as root in production builds')
        state['uid'] = 0
        finish(1 if scenario == 'transient-root' else 0,
               'unable to connect for root: closed' if scenario == 'transient-root' else '')
    if args == ['unroot']:
        state['unroot_attempts'] += 1
        if scenario == 'unroot-fails':
            finish(1, 'unable to connect for unroot: closed')
        state['uid'] = 2000
        finish()
    if args == ['wait-for-device']:
        finish()
    if args and args[0] == 'logcat':
        finish()
    if args and args[0] == 'shell':
        command = ' '.join(args[1:])
        if args[1:] == ['id', '-u']:
            finish(output=str(state['uid']))
        if args[1:] == ['id']:
            finish(output=f"uid={state['uid']}({'root' if state['uid'] == 0 else 'shell'}) gid=2000(shell)")
        if 'pidof magiskd' in command:
            finish(output='420')
        if command.endswith('magisk -v'):
            finish(output='Magisk 31.0')
        if '--sqlite' in command:
            finish(0 if state['uid'] == 0 else 1)
        if 'su -c id' in command:
            state['su_id_calls'] += 1
            finish(output='uid=0(root) gid=0(root) context=u:r:magisk:s0')
        if 'magisk -V' in command:
            finish(output='Magisk 31.0\\n31000')
        finish()
    finish()
''')


class VerifyAvdRootTest(unittest.TestCase):
    def run_with_fake_adb(self, scenario):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        work = Path(temporary.name)
        fake_bin = work / 'bin'
        fake_bin.mkdir()
        fake_adb = fake_bin / 'adb'
        fake_adb.write_text(FAKE_ADB)
        fake_adb.chmod(0o755)
        state_path = work / 'state.json'
        state_path.write_text(json.dumps({
            'uid': 2000,
            'root_attempts': 0,
            'unroot_attempts': 0,
            'su_id_calls': 0,
            'calls': [],
        }))
        environment = os.environ.copy()
        environment.update({
            'PATH': str(fake_bin) + os.pathsep + environment['PATH'],
            'FAKE_ADB_SCENARIO': scenario,
            'FAKE_ADB_STATE': str(state_path),
        })
        result = subprocess.run(
            ['bash', str(SCRIPT)], cwd=work, env=environment,
            capture_output=True, text=True, timeout=30,
        )
        state = json.loads(state_path.read_text())
        output = (work / 'work/root-verification/evidence/root-check.txt').read_text()
        return result, state, output

    def test_accepts_root_transport_error_only_after_uid_confirms_root_and_restores_shell(self):
        result, state, output = self.run_with_fake_adb('transient-root')

        self.assertEqual(0, result.returncode, result.stderr + result.stdout)
        self.assertIn('Accepting adb root transport error because shell UID is 0', output)
        self.assertEqual(1, state['root_attempts'])
        self.assertEqual(1, state['unroot_attempts'])
        self.assertEqual(2000, state['uid'])
        self.assertEqual(1, state['su_id_calls'])

    def test_rejects_root_denial_when_shell_remains_unprivileged(self):
        result, state, output = self.run_with_fake_adb('unauthorized')

        self.assertNotEqual(0, result.returncode)
        self.assertIn('transition failed: shell UID did not reach 0 after 3 attempts', output)
        self.assertEqual(3, state['root_attempts'])
        self.assertEqual(0, state['unroot_attempts'])
        self.assertEqual(0, state['su_id_calls'])
        self.assertFalse(any('--sqlite' in ' '.join(call['args']) for call in state['calls']))

    def test_rejects_unroot_when_shell_uid_remains_root(self):
        result, state, output = self.run_with_fake_adb('unroot-fails')

        self.assertNotEqual(0, result.returncode)
        self.assertIn('transition failed: shell UID did not reach 2000 after 3 attempts', output)
        self.assertEqual(1, state['root_attempts'])
        self.assertEqual(3, state['unroot_attempts'])
        self.assertEqual(0, state['uid'])
        self.assertEqual(0, state['su_id_calls'])


if __name__ == '__main__':
    unittest.main()
