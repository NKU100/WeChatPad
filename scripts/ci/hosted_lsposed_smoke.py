"""Probe official LSPosed and WeChat login UI on a disposable hosted AVD."""

import json
import csv
import io
from pathlib import Path
import re
import shlex
import subprocess
import time
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path('work/hosted-lsp')
EVIDENCE = ROOT / 'evidence'
MAGISK = '/debug_ramdisk/magisk'
WECHAT = 'com.tencent.mm'
MODULE = 'io.github.nku100.wechatpad'
stage = 'START'


def run(*args, timeout=60, check=True):
    try:
        result = subprocess.run(args, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        if check:
            raise RuntimeError(f'{args[0]} timed out after {timeout} seconds') from error
        return subprocess.CompletedProcess(args, 124, error.stdout or b'', b'Command timed out')
    if check and result.returncode:
        raise RuntimeError(f'{args[0]} exited {result.returncode}: ' + (result.stdout + result.stderr).decode(errors='replace'))
    return result


def adb(*args, timeout=60, check=True):
    if args[0] == 'shell':
        args = ('shell', ' '.join(shlex.quote(arg) for arg in args[1:]))
    return run('adb', *args, timeout=timeout, check=check)


def su(command, **kwargs):
    return adb('shell', MAGISK, 'su', '-c', command, **kwargs)


def save(name, result):
    (EVIDENCE / name).write_bytes(result.stdout + result.stderr)


def nodes(xml):
    try:
        return list(ET.fromstring(xml).iter('node'))
    except ET.ParseError:
        return []


def has_wechat_ui(xml):
    return any(node.get('package') == WECHAT for node in nodes(xml))


def is_tablet_entry(text):
    return bool(re.search(r'(?:log(?:ged)?\s*in|登录).*(?:phone\s*&\s*tablet|平板)', text, re.I))


def qr_page_ready(activity, xml):
    return ('LoginAsExDeviceUI' in activity and has_wechat_ui(xml)
            and any(re.search(r'QR\s*code|二维码', node.get('text', ''), re.I) for node in nodes(xml)))


def unique_node(xml, predicate):
    matches = [node for node in nodes(xml) if node.get('visible') != 'false' and predicate(node)]
    if len(matches) > 1:
        raise ValueError(f'UI selector is ambiguous ({len(matches)} matches)')
    return matches[0] if matches else None


def ocr_target(tsv, label):
    lines = {}
    for word in csv.DictReader(io.StringIO(tsv), delimiter='\t'):
        if word['level'] != '5' or not word['text'].strip():
            continue
        key = tuple(word[field] for field in ('page_num', 'block_num', 'par_num', 'line_num'))
        lines.setdefault(key, []).append(word)
    matches = []
    for words in lines.values():
        text = ' '.join(word['text'] for word in words)
        if text.casefold() != label.casefold() or any(float(word['conf']) < 70 for word in words):
            continue
        left = min(int(word['left']) for word in words)
        top = min(int(word['top']) for word in words)
        right = max(int(word['left']) + int(word['width']) for word in words)
        bottom = max(int(word['top']) + int(word['height']) for word in words)
        matches.append(ET.Element('node', {'text': text, 'bounds': f'[{left},{top}][{right},{bottom}]'}))
    if len(matches) > 1:
        raise ValueError(f'OCR selector is ambiguous ({len(matches)} matches)')
    return matches[0] if matches else None


def manager_ocr():
    result = run('tesseract', str(EVIDENCE / 'manager-current.png'), 'stdout', '--psm', '11', 'tsv')
    save('manager-current-ocr.tsv', result)
    return result.stdout.decode(errors='replace')


def snapshot(label):
    adb('shell', 'rm', '-f', '/data/local/tmp/hosted-smoke.xml')
    dump = adb('shell', 'env', 'CLASSPATH=/data/local/tmp/ui-hierarchy.jar',
               'app_process', '/system/bin', 'UiHierarchy', '/data/local/tmp/hosted-smoke.xml',
               timeout=25, check=False)
    save(label + '-dump.txt', dump)
    ui = adb('shell', 'cat', '/data/local/tmp/hosted-smoke.xml', check=False)
    save(label + '.xml', ui)
    screen = adb('exec-out', 'screencap', '-p', check=False)
    if screen.returncode == 0:
        (EVIDENCE / (label + '.png')).write_bytes(screen.stdout)
    activity = adb('shell', 'dumpsys', 'activity', 'activities')
    save(label + '-activity.txt', activity)
    return activity.stdout.decode(errors='replace'), ui.stdout.decode(errors='replace')


def tap(node):
    bounds = [int(part) for part in re.findall(r'\d+', node.get('bounds', ''))]
    if len(bounds) != 4 or bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
        raise RuntimeError('Selected UI element has no visible bounds')
    adb('shell', 'input', 'tap', str((bounds[0] + bounds[2]) // 2), str((bounds[1] + bounds[3]) // 2))
    time.sleep(2)


def enable_page_size_backcompat():
    # Recovery libraries unpacked at runtime can still have 4 KB ELF alignment.
    su('setprop bionic.linker.16kb.app_compat.enabled true; setprop pm.16kb.app_compat.disabled false')


def mobile_input(label):
    enable_page_size_backcompat()
    adb('shell', 'am', 'force-stop', WECHAT)
    adb('shell', 'monkey', '-p', WECHAT, '-c', 'android.intent.category.LAUNCHER', '1')
    ready = 0
    for attempt in range(30):
        activity, ui = snapshot(label + '-current')
        if 'MobileInputUI' in activity and has_wechat_ui(ui):
            ready += 1
            if ready >= 2:
                snapshot(label)
                return ui
        else:
            ready = 0
            node = unique_node(ui, lambda n: n.get('text', '').strip().lower() in (
                'log in', 'login', 'log in via mobile number', 'log in with phone number',
                'agree', 'accept', 'allow', 'while using the app', '登录', '手机号登录', '同意'))
            if node is not None:
                tap(node)
        time.sleep(2)
    raise RuntimeError('WeChat did not reach a stable, rendered MobileInputUI')


def reboot():
    adb('reboot')
    adb('wait-for-device', timeout=180)
    for _ in range(90):
        if adb('shell', 'getprop', 'sys.boot_completed', check=False).stdout.strip() == b'1':
            return
        time.sleep(2)
    raise RuntimeError('Device did not complete reboot')


def bootstrap_magisk():
    files = ROOT / 'magisk-files'
    files.mkdir(exist_ok=True)
    with zipfile.ZipFile(ROOT / 'magisk.apk') as apk:
        for name in apk.namelist():
            if name.startswith('assets/') and name.endswith('.sh'):
                (files / Path(name).name).write_bytes(apk.read(name))
        for binary in ('busybox', 'magisk', 'magiskboot', 'magiskinit', 'magiskpolicy', 'bootctl'):
            (files / binary).write_bytes(apk.read(f'lib/x86_64/lib{binary}.so'))
    adb('shell', 'mkdir', '-p', '/data/local/tmp/wechatpad-magisk-files')
    for file in files.iterdir():
        adb('push', str(file), '/data/local/tmp/wechatpad-magisk-files/' + file.name)
    save('magisk-bootstrap.txt', su('mkdir -p /data/adb/magisk; cp /data/local/tmp/wechatpad-magisk-files/* /data/adb/magisk/; chmod -R 755 /data/adb/magisk'))
    save('preinit-device.txt', su(MAGISK + ' --preinit-device', check=False))
    adb('install', '-r', str(ROOT / 'magisk.apk'), timeout=120)


def configure_manager():
    adb('shell', 'am', 'start', '-n', 'org.lsposed.manager/.ui.activity.MainActivity')
    for _ in range(10):
        _, ui = snapshot('manager-current')
        enabled = unique_node(ui, lambda n: 'Switch' in n.get('class', '') and n.get('checkable') == 'true')
        if enabled is not None and any(n.get('text') == 'WeChatPad' for n in nodes(ui)):
            if enabled.get('checked') != 'true':
                tap(enabled)
                _, ui = snapshot('manager-enabled')
                enabled = unique_node(ui, lambda n: 'Switch' in n.get('class', '') and n.get('checkable') == 'true')
            if enabled is None or enabled.get('checked') != 'true':
                raise RuntimeError('Manager did not confirm WeChatPad enabled')
            return
        tsv = manager_ocr()
        enable = ocr_target(tsv, 'Enable module')
        if enable is not None:
            tap(enable)
            snapshot('manager-enable-requested')
            # The final hook logs and QR page verify that enabling took effect.
            return
        node = unique_node(ui, lambda n: n.get('text') == 'WeChatPad')
        if node is None:
            node = ocr_target(tsv, 'WeChatPad')
        if node is None:
            node = unique_node(ui, lambda n: n.get('text') == 'Modules' or n.get('content-desc') == 'Modules')
        if node is not None:
            tap(node)
        else:
            time.sleep(2)
    raise RuntimeError('Unable to enable WeChatPad through the official Manager UI')


def collect_logs():
    logcat = adb('logcat', '-d', '-v', 'threadtime', check=False)
    save('logcat.txt', logcat)
    framework = su('for d in /data/adb/lspd/log /data/adb/lspd/logs; do if [ -d "$d" ]; then find "$d" -type f -exec cat {} +; fi; done', check=False)
    save('lsposed-logs.txt', framework)
    save('framework-state.txt', su('ls -la /data/adb/lspd; ls -la /data/adb/modules/zygisk_lsposed; cat /data/adb/modules/zygisk_lsposed/module.prop; ps -A', check=False))
    return (logcat.stdout + framework.stdout).decode(errors='replace')


def main():
    global stage
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    report = {'status': 'FAILED', 'stage': stage}
    try:
        stage = 'AUTOMATION_SETUP'
        adb('push', str(ROOT / 'ui-hierarchy.jar'), '/data/local/tmp/ui-hierarchy.jar')
        stage = 'BASELINE'
        enable_page_size_backcompat()
        save('page-size-compat.txt', adb('shell', 'getprop'))
        adb('logcat', '-c')
        save('wechat-install.txt', adb('install', '-r', '-g', str(ROOT / 'wechat.apk'), timeout=240))
        ui = mobile_input('baseline-mobile')
        if any(is_tablet_entry(n.get('text', '')) for n in nodes(ui)):
            raise RuntimeError('Tablet choice already exists without WeChatPad; baseline does not establish module effect')
        report['baseline'] = 'NO_TABLET_ENTRY'
        stage = 'FRAMEWORK_INSTALL'
        bootstrap_magisk()
        adb('push', str(ROOT / 'lsposed.zip'), '/data/local/tmp/lsposed.zip')
        save('zygisk-setting.txt', su(MAGISK + ' --sqlite "REPLACE INTO settings (key,value) VALUES (\'zygisk\',1)"'))
        result = su('export PATH=/debug_ramdisk:/data/adb/magisk:$PATH; magisk --install-module /data/local/tmp/lsposed.zip', timeout=240, check=False)
        save('lsposed-install.txt', result)
        if result.returncode:
            raise RuntimeError('Official LSPosed installer failed; see lsposed-install.txt')
        save('module-install.txt', adb('install', '-r', str(ROOT / 'module/app-debug.apk'), timeout=120))
        save('manager-install.txt', adb('install', '-r', str(ROOT / 'manager.apk'), timeout=120))
        reboot()
        stage = 'FRAMEWORK_START'
        for _ in range(45):
            daemon = su('pidof lspd', check=False)
            if daemon.returncode == 0 and daemon.stdout.strip():
                save('lspd-pid.txt', daemon)
                break
            time.sleep(2)
        else:
            raise RuntimeError('LSPosed daemon did not start after reboot')
        stage = 'MODULE_ENABLE'
        configure_manager()
        stage = 'HOOK_AND_LOGIN'
        adb('shell', 'pm', 'clear', WECHAT)
        adb('logcat', '-c')
        ui = mobile_input('module-mobile')
        choice = unique_node(ui, lambda n: is_tablet_entry(n.get('text', '')))
        if choice is None:
            raise RuntimeError('No tablet login choice after module enable')
        tap(choice)
        for _ in range(20):
            activity, ui = snapshot('qr-current')
            if qr_page_ready(activity, ui):
                time.sleep(3)
                activity, ui = snapshot('qr')
                if qr_page_ready(activity, ui):
                    break
            time.sleep(2)
        else:
            raise RuntimeError('Tablet login did not reach a stable rendered QR page')
        logs = collect_logs()
        if 'status=COMPATIBLE' not in logs or 'installed 2 WeChat hooks' not in logs:
            raise RuntimeError('Rendered QR page was not accompanied by compatible WeChatPad hook installation logs')
        report.update(status='RUNTIME_SMOKE_VERIFIED', stage='COMPLETE', hooks=2, qrPage='LoginAsExDeviceUI')
    except Exception as error:
        report.update(stage=stage, reason=str(error))
        try:
            snapshot('failure')
        except Exception as diagnostic:
            report['diagnosticError'] = str(diagnostic)
    finally:
        collect_logs()
        (EVIDENCE / 'smoke-report.json').write_text(json.dumps(report, indent=2) + '\n')
        (EVIDENCE / 'summary.md').write_text('# Hosted LSPosed smoke\n\n' + json.dumps(report, indent=2)
                                            + '\n\nNo QR scanning, account login or dual-device session was performed.\n')
        print(json.dumps(report))
    return 0 if report['status'] == 'RUNTIME_SMOKE_VERIFIED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
