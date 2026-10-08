"""Execute sandbox device requests without granting the model network access."""
import json
import os
from pathlib import Path
import re
import subprocess
import threading

COMMANDS = {'shell', 'exec-out', 'push', 'pull', 'install', 'uninstall', 'logcat',
            'reboot', 'root', 'unroot', 'wait-for-device', 'get-state', 'version', 'help'}


def validate_request(request, workspace):
    args = request['args']
    if (not isinstance(args, list) or not 1 <= len(args) <= 64
            or any(not isinstance(a, str) or len(a) > 8192 or '\0' in a for a in args)
            or args[0] not in COMMANDS):
        raise ValueError('Use a device command; the emulator and ADB server are fixed by the controller.')
    cwd = Path(request['cwd']).resolve()
    if not cwd.is_relative_to(workspace):
        raise ValueError('Device command must run inside the adaptation workspace')
    def local_path(value):
        if not (cwd / value).resolve().is_relative_to(workspace):
            raise ValueError('ADB local files must stay inside the adaptation workspace')
    if args[0] == 'install':
        files = [a for a in args[1:] if not a.startswith('-')]
        if len(files) != 1 or any(a.startswith('-') and a not in {'-r', '-g', '-t', '-d', '--no-streaming', '--streaming'} for a in args[1:]):
            raise ValueError('Use install with one workspace APK and supported flags')
        local_path(files[0])
    elif args[0] == 'push':
        files = [a for a in args[1:] if not a.startswith('-')]
        if len(files) < 2 or any(a.startswith('-') for a in args[1:]):
            raise ValueError('Use push with workspace files and one device destination')
        for value in files[:-1]:
            local_path(value)
    elif args[0] == 'pull':
        if len(args) not in {2, 3} or any(a.startswith('-') for a in args[1:]):
            raise ValueError('Use pull with one device source and optional workspace destination')
        local_path(args[2] if len(args) == 3 else '.')
    return args, cwd


class DeviceRelay:
    def __init__(self, directory, env):
        state = json.loads((directory / 'state.json').read_text())
        self.workspace = Path(state['worktree']).resolve()
        self.root = self.workspace / 'work/analysis/adb-relay'
        self.root.mkdir(parents=True, exist_ok=True)
        self.fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        runtime = state['runtime']
        self.adb = str(Path(env['ANDROID_HOME']) / 'platform-tools/adb')
        self.serial = runtime['serial']
        self.env = dict(env, ADB_SERVER_SOCKET='localfilesystem:' + runtime['socket'])
        self.stop = threading.Event()
        self.process_lock = threading.Lock()
        self.process = None
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()

    def write(self, name, data):
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)

    def serve(self):
        while not self.stop.is_set():
            for name in os.listdir(self.fd):
                if not re.fullmatch(r'[a-f0-9]{32}\.request', name):
                    continue
                key = name[:-8]
                try:
                    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=self.fd)
                    with os.fdopen(fd, 'rb') as stream:
                        request = json.loads(stream.read(65536))
                    args, cwd = validate_request(request, self.workspace)
                    with self.process_lock:
                        if self.stop.is_set():
                            return
                        self.process = subprocess.Popen([self.adb, '-s', self.serial, *args], cwd=cwd,
                                                        env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    try:
                        stdout, stderr = self.process.communicate(timeout=120)
                        code = self.process.returncode
                    except subprocess.TimeoutExpired:
                        self.process.kill()
                        stdout, stderr = self.process.communicate()
                        code, stderr = 124, stderr + b'\nDevice command exceeded 120 seconds\n'
                    finally:
                        with self.process_lock:
                            self.process = None
                except Exception as error:
                    code, stdout, stderr = 2, b'', (str(error) + '\n').encode()
                try:
                    self.write(key + '.stdout', stdout)
                    self.write(key + '.stderr', stderr)
                    os.unlink(name, dir_fd=self.fd)
                    self.write(key + '.result', json.dumps({'exitCode': code}).encode())
                except OSError:
                    pass
            self.stop.wait(0.05)

    def close(self):
        self.stop.set()
        with self.process_lock:
            if self.process is not None:
                self.process.kill()
        self.thread.join(timeout=5)
        os.close(self.fd)
