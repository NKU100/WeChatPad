"""Exercise managed AVD launch and relay cancellation on the fresh CI emulator."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.ci.adb_relay import DeviceRelay


def main():
    root = Path('work/runtime-smoke/tooling').resolve()
    task = root / 'task'; task.mkdir(parents=True, exist_ok=True)
    workspace = root / 'checkout'; workspace.mkdir(exist_ok=True)
    socket = root / 'adb.sock'
    devices = subprocess.check_output(['adb','devices'],text=True).splitlines()[1:]
    assert [line.split()[0] for line in devices if line.strip()]==['emulator-5554'], 'Tooling probe requires one disposable emulator'
    subprocess.run(['adb','kill-server'],check=True)
    subprocess.run(['adb','-L','localfilesystem:'+str(socket),'start-server'],check=True)
    env = dict(os.environ, ADB_SERVER_SOCKET='localfilesystem:'+str(socket))
    subprocess.run(['adb','-s','emulator-5554','wait-for-device'],env=env,check=True,timeout=120)
    (task/'state.json').write_text(json.dumps({'appId':os.environ.get('APP_ID', 'wechat'),'worktree':str(workspace),'runtime':{'socket':str(socket),'serial':'emulator-5554'}}))
    relay = DeviceRelay(task,env)
    env['WECHATPAD_ADB_RELAY'] = str(relay.root)
    wrapper = str(Path('scripts/ci/adb-device.sh').resolve())
    try:
        subprocess.run(['bash',wrapper,'app-launch'],cwd=workspace,env=env,check=True,timeout=180)
        screenshot = subprocess.check_output(['bash',wrapper,'exec-out','screencap','-p'],cwd=workspace,env=env,timeout=45)
        assert screenshot.startswith(b'\x89PNG\r\n\x1a\n'), 'Relay screenshot is not a PNG'
        client = subprocess.Popen(['bash',wrapper,'shell','sleep','30'],cwd=workspace,env=env)
        try:
            time.sleep(1)
            client.terminate(); client.wait(timeout=5)
            started = time.monotonic()
            state = subprocess.check_output(['bash',wrapper,'get-state'],cwd=workspace,env=env,timeout=5)
            assert state.strip()==b'device'
            seconds = time.monotonic()-started
        finally:
            if client.poll() is None: client.kill(); client.wait()
        (root/'tooling-report.json').write_text(json.dumps({'status':'PASSED','managedLaunch':True,'binaryScreenshot':True,'queueRecoveredSeconds':seconds},indent=2)+'\n')
        print('Managed AVD launch, binary screenshot and cancelled-request queue recovery passed')
    finally:
        relay.close()


if __name__=='__main__':
    main()
