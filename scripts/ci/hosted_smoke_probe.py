"""Gate a hosted smoke experiment on execution of the registered ARM64 APK."""

import json
import subprocess
import time
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path('work/probe')
EVIDENCE = ROOT / 'evidence'


def adb(*arguments, timeout=60):
    return subprocess.run(['adb', *arguments], capture_output=True, timeout=timeout)


def save(name, result):
    (EVIDENCE / name).write_bytes(result.stdout + result.stderr)


def wechat_page_ready(activity, ui):
    resumed = any('com.tencent.mm/' in line and 'WeChatSplashActivity' not in line
                  and ('mResumedActivity' in line or 'topResumedActivity' in line)
                  for line in activity.splitlines())
    try:
        return resumed and any(node.get('package') == 'com.tencent.mm' for node in ET.fromstring(ui).iter('node'))
    except ET.ParseError:
        return False


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
    ready_count = 0
    for _ in range(30):
        activity = adb('shell', 'dumpsys', 'activity', 'activities')
        text = activity.stdout.decode(errors='replace')
        save('activities.txt', activity)
        adb('shell', 'uiautomator', 'dump', '/sdcard/probe-ui.xml', timeout=20)
        ui = adb('shell', 'cat', '/sdcard/probe-ui.xml')
        save('ui.xml', ui)
        ready_count = ready_count + 1 if wechat_page_ready(text, ui.stdout) else 0
        if ready_count >= 2:
            break
        time.sleep(2)
    time.sleep(5)
    activity = adb('shell', 'dumpsys', 'activity', 'activities')
    save('activities.txt', activity)
    text = activity.stdout.decode(errors='replace')
    adb('shell', 'uiautomator', 'dump', '/sdcard/probe-ui.xml', timeout=20)
    ui = adb('shell', 'cat', '/sdcard/probe-ui.xml')
    save('ui.xml', ui)
    visible = ready_count >= 2 and wechat_page_ready(text, ui.stdout)
    screen = adb('exec-out', 'screencap', '-p')
    if screen.returncode == 0:
        (EVIDENCE / 'wechat-screen.png').write_bytes(screen.stdout)
    save('logcat.txt', adb('logcat', '-d', '-v', 'threadtime'))
    if not visible:
        return finish('ARM_APK_LAUNCH_FAILED', 'A visible WeChat page beyond the splash activity did not remain stable; inspect logs and screenshot.', **details)
    return finish('ARM_APK_RUNNING', 'ARM64 WeChat installed and remained visible. Root and LSPosed injection still require the next experiment stage.', **details)


if __name__ == '__main__':
    raise SystemExit(main())
