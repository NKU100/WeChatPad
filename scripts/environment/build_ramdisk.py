"""Rebuild the pinned AVD Magisk ramdisk using verified official inputs."""
import argparse
import hashlib
import json
import os
import platform
import shlex
import shutil
import subprocess
import tempfile
import uuid
import zipfile
from pathlib import Path

RECIPE = Path(__file__).resolve().parents[2] / 'environment/avd-runtime.json'


def digest(path, algorithm='sha256'):
    value = hashlib.new(algorithm)
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def verify(path, expected, algorithm='sha256'):
    actual = digest(path, algorithm)
    if actual != expected:
        raise ValueError(f'{path.name}: {algorithm} mismatch; expected {expected}, got {actual}')


def fetch_verified(url, path, expected, algorithm='sha256'):
    if path.is_file():
        verify(path, expected, algorithm)
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
    try:
        subprocess.run(['curl', '--fail', '--location', '--silent', '--show-error', '--retry', '3',
                        '--connect-timeout', '20', '--max-time', '900', '--proto', '=https',
                        '--proto-redir', '=https', url, '-o', str(temporary)], check=True)
        verify(temporary, expected, algorithm)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def merge_cpio(data):
    # Android concatenates archives; later entries override earlier ones. Keep raw headers
    # and first-insertion order to reproduce the originally published merge exactly.
    position, archives = 0, 0
    entries, trailer = {}, None
    in_archive = False
    while position < len(data):
        while position < len(data) and data[position] == 0:
            position += 1
        if position == len(data):
            break
        if data[position:position + 6] not in (b'070701', b'070702') or position + 110 > len(data):
            raise ValueError('Malformed newc CPIO header')
        fields = [int(data[position + 6 + i * 8:position + 14 + i * 8], 16) for i in range(13)]
        size, name_size = fields[6], fields[11]
        name_end = position + 110 + name_size
        if name_size < 1 or name_end > len(data) or data[name_end - 1] != 0:
            raise ValueError('Malformed CPIO filename')
        name = data[position + 110:name_end - 1].decode('utf-8')
        content = (name_end + 3) // 4 * 4
        end = (content + size + 3) // 4 * 4
        if end > len(data):
            raise ValueError('Truncated CPIO entry')
        if name == 'TRAILER!!!':
            archives += 1
            trailer = data[position:end]
            in_archive = False
        else:
            entries[name] = data[position:end]
            in_archive = True
        position = end
    if trailer is None or in_archive:
        raise ValueError('CPIO archive is missing its trailer')
    return b''.join(entries.values()) + trailer, archives


class Backend:
    def __init__(self, work, serial):
        self.work, self.serial = work, serial
        self.remote = '/data/local/tmp/wechatpad-ramdisk-build-' + uuid.uuid4().hex
        self.created = False
        if serial:
            if not serial.startswith('emulator-'):
                raise ValueError('Use an explicitly selected disposable AVD, not a physical device')
            self.abi = self.adb('shell', 'getprop', 'ro.product.cpu.abi', capture=True).strip()
        else:
            if platform.system() != 'Linux':
                raise ValueError('Native mode requires Linux. On macOS, pass --serial for a dedicated AVD')
            self.abi = {'x86_64': 'x86_64', 'aarch64': 'arm64-v8a'}.get(platform.machine())
        if self.abi not in {'x86_64', 'arm64-v8a'}:
            raise ValueError('Builder must be x86_64 or ARM64')

    def adb(self, *args, capture=False):
        result = subprocess.run(['adb', '-s', self.serial, *args], check=True, timeout=180,
                                stdout=subprocess.PIPE if capture else None, text=True)
        return result.stdout if capture else None

    def start(self):
        if self.serial:
            self.adb('shell', 'mkdir', self.remote)
            self.created = True

    def put(self, name):
        if self.serial:
            self.adb('push', str(self.work / name), self.remote + '/' + name)

    def get(self, name):
        if self.serial:
            self.adb('pull', self.remote + '/' + name, str(self.work / name))

    def run(self, *args):
        if self.serial:
            command = (f'cd {shlex.quote(self.remote)} && chmod 755 magiskboot && '
                       'KEEPVERITY=true KEEPFORCEENCRYPT=true ./magiskboot ' + shlex.join(args))
            self.adb('shell', command)
        else:
            env = dict(os.environ, KEEPVERITY='true', KEEPFORCEENCRYPT='true')
            subprocess.run(['./magiskboot', *args], cwd=self.work, env=env, check=True, timeout=180)

    def close(self):
        if self.created:
            subprocess.run(['adb', '-s', self.serial, 'shell', 'rm', '-rf', self.remote],
                           check=False, timeout=30)


def build(args):
    recipe = json.loads(args.recipe.read_text())
    if recipe['recipeVersion'] != 1:
        raise ValueError('Unsupported recipe version')
    image, magisk, patch = recipe['systemImage'], recipe['magisk'], recipe['patch']
    if not patch['keepVerity'] or not patch['keepForceEncrypt']:
        raise ValueError('This recipe preserves verity and force encryption')
    if args.output.exists() and any(args.output.iterdir()):
        raise ValueError('Output directory must be empty')
    args.output.mkdir(parents=True, exist_ok=True)
    args.cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='wechatpad-ramdisk-') as folder:
        work = Path(folder)
        backend = Backend(work, args.serial)
        try:
            if args.stock_ramdisk:
                verify(args.stock_ramdisk, image['stockRamdiskSha256'])
                shutil.copyfile(args.stock_ramdisk, work / 'stock.img')
            else:
                archive = args.system_image_zip or fetch_verified(
                    image['sourceUrl'], args.cache / (image['archiveSha1'] + '.zip'), image['archiveSha1'], 'sha1')
                verify(archive, image['archiveSha1'], 'sha1')
                with zipfile.ZipFile(archive) as source:
                    candidates = [name for name in source.namelist() if name.endswith('/ramdisk.img')]
                    if len(candidates) != 1:
                        raise ValueError('System archive must contain one ramdisk.img')
                    with source.open(candidates[0]) as stream, (work / 'stock.img').open('wb') as output:
                        shutil.copyfileobj(stream, output)
                verify(work / 'stock.img', image['stockRamdiskSha256'])
            apk = args.magisk_apk or fetch_verified(magisk['sourceUrl'], args.cache / (magisk['apkSha256'] + '.apk'), magisk['apkSha256'])
            verify(apk, magisk['apkSha256'])
            payload = patch['payloadAbi']
            with zipfile.ZipFile(apk) as source:
                for name, member in [('magiskboot', f'lib/{backend.abi}/libmagiskboot.so'),
                                     ('magiskinit', f'lib/{payload}/libmagiskinit.so'),
                                     ('magisk', f'lib/{payload}/libmagisk.so'),
                                     ('init-ld', f'lib/{payload}/libinit-ld.so'), ('stub.apk', 'assets/stub.apk')]:
                    (work / name).write_bytes(source.read(member))
            (work / 'magiskboot').chmod(0o755)
            (work / 'config').write_bytes(b'KEEPVERITY=true\nKEEPFORCEENCRYPT=true\nRECOVERYMODE=false\n')
            backend.start()
            for name in ['stock.img', 'magiskboot', 'magiskinit', 'magisk', 'init-ld', 'stub.apk', 'config']:
                backend.put(name)
            backend.run('decompress', 'stock.img', 'raw.cpio')
            backend.get('raw.cpio')
            merged, count = merge_cpio((work / 'raw.cpio').read_bytes())
            if count != patch['mergedCpioArchives']:
                raise ValueError(f'Expected {patch["mergedCpioArchives"]} CPIO archives, got {count}')
            for name in ['ramdisk.cpio', 'ramdisk.cpio.orig']:
                (work / name).write_bytes(merged)
                backend.put(name)
            for source, output in [('magisk', 'magisk.xz'), ('init-ld', 'init-ld.xz'), ('stub.apk', 'stub.xz')]:
                backend.run('compress=xz', source, output)
            backend.run('cpio', 'ramdisk.cpio', 'add 0750 init magiskinit', 'mkdir 0750 overlay.d',
                        'mkdir 0750 overlay.d/sbin', 'add 0644 overlay.d/sbin/magisk.xz magisk.xz',
                        'add 0644 overlay.d/sbin/stub.xz stub.xz', 'add 0644 overlay.d/sbin/init-ld.xz init-ld.xz',
                        'patch', 'backup ramdisk.cpio.orig', 'mkdir 000 .backup', 'add 000 .backup/.magisk config')
            backend.run('compress=' + patch['compression'], 'ramdisk.cpio', 'ramdisk37-patched.img')
            backend.get('ramdisk37-patched.img')
            verify(work / 'ramdisk37-patched.img', patch['ramdiskSha256'])
            manifest = dict(recipe)
            manifest['patch'] = dict(patch, toolAbi=backend.abi, magiskbootSha256=digest(work / 'magiskboot'))
            manifest['reproduction'] = {'recipeSha256': digest(args.recipe), 'expectedOutputMatched': True,
                                        'systemArchiveVerified': not bool(args.stock_ramdisk)}
            shutil.copyfile(work / 'ramdisk37-patched.img', args.output / 'ramdisk37-patched.img')
            (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
            print('Reproduced pinned ramdisk SHA-256: ' + patch['ramdiskSha256'])
        finally:
            backend.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recipe', type=Path, default=RECIPE)
    parser.add_argument('--stock-ramdisk', type=Path)
    parser.add_argument('--system-image-zip', type=Path)
    parser.add_argument('--magisk-apk', type=Path)
    parser.add_argument('--serial', help='Explicit disposable AVD serial; omit for native Linux')
    parser.add_argument('--cache', type=Path, default=Path('work/ramdisk-build/cache'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.stock_ramdisk and args.system_image_zip:
        parser.error('Choose --stock-ramdisk or --system-image-zip')
    build(args)


if __name__ == '__main__':
    main()
