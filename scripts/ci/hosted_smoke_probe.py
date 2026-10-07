"""Gate a hosted smoke experiment on execution of the registered ARM64 APK."""

import json
import subprocess
import time
import zipfile
from pathlib import Path


ROOT = Path('work/probe')
EVIDENCE = ROOT / 'evidence'


def adb(*arguments, timeout=60):
    return subprocess.run(['adb', *arguments], capture_output=True, timeout=timeout)


def save(name, result):
    (EVIDENCE / name).write_bytes(result.stdout + result.stderr)


def finish(status, reason, **details):
    report = dict(status=status, reason=reason, **details)
    (EVIDENCE / 'environment-report.json').write_text(json.dumps(report, indent=2) + '\n')
    (EVIDENCE / 'summary.md').write_text(f'# Hosted WeChat environment probe\n\nStatus: `{status}`\n\n{reason}\n\n'
                                      'This environment probe does not certify LSPosed injection or runtime compatibility.\n')
    print(status, reason)
    return 0 if status == 'ARM_APK_RUNNING' else 1


def main():
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    properties = adb('shell', 'getprop')
    save('device-properties.txt', properties)
    abis = adb('shell', 'getprop', 'ro.product.cpu.abilist').stdout.decode().strip()
    bridge = adb('shell', 'getprop', 'ro.dalvik.vm.native.bridge').stdout.decode().strip()
    apk = ROOT / 'wechat.apk'
    with zipfile.ZipFile(apk) as archive:
        apk_abis = sorted({name.split('/')[1] for name in archive.namelist() if name.startswith('lib/') and name.endswith('.so')})
    details = dict(deviceAbis=abis, nativeBridge=bridge, apkAbis=apk_abis)
    adb('logcat', '-c')
    installed = adb('install', '-r', str(apk), timeout=180)
    save('wechat-install.txt', installed)
    if installed.returncode:
        return finish('ARM_APK_INSTALL_FAILED', installed.stdout.decode() + installed.stderr.decode(), **details)
    module = adb('install', '-r', str(ROOT / 'module/app-debug.apk'), timeout=120)
    save('module-install.txt', module)
    if module.returncode:
        return finish('MODULE_INSTALL_FAILED', 'The existing module APK could not be installed.', **details)
    launched = adb('shell', 'monkey', '-p', 'com.tencent.mm', '-c', 'android.intent.category.LAUNCHER', '1')
    save('wechat-launch.txt', launched)
    visible = False
    for _ in range(30):
        activity = adb('shell', 'dumpsys', 'activity', 'activities')
        text = activity.stdout.decode(errors='replace')
        save('activities.txt', activity)
        if any('com.tencent.mm/' in line and ('mResumedActivity' in line or 'topResumedActivity' in line) for line in text.splitlines()):
            visible = True
            break
        time.sleep(2)
    time.sleep(5)
    activity = adb('shell', 'dumpsys', 'activity', 'activities')
    save('activities.txt', activity)
    text = activity.stdout.decode(errors='replace')
    visible = visible and any('com.tencent.mm/' in line and ('mResumedActivity' in line or 'topResumedActivity' in line) for line in text.splitlines())
    save('logcat.txt', adb('logcat', '-d', '-v', 'threadtime'))
    screen = adb('exec-out', 'screencap', '-p')
    if screen.returncode == 0:
        (EVIDENCE / 'wechat-screen.png').write_bytes(screen.stdout)
    adb('shell', 'uiautomator', 'dump', '/sdcard/probe-ui.xml')
    save('ui.xml', adb('shell', 'cat', '/sdcard/probe-ui.xml'))
    if not visible:
        return finish('ARM_APK_LAUNCH_FAILED', 'WeChat did not remain the resumed application; inspect logs and screenshot.', **details)
    return finish('ARM_APK_RUNNING', 'ARM64 WeChat installed and remained visible. Root and LSPosed injection still require the next experiment stage.', **details)


if __name__ == '__main__':
    raise SystemExit(main())
