"""Expose only clean adaptation inputs and tool dependencies to the model server."""

import shutil
import sys
from pathlib import Path


def model_command(directory, env, command):
    if sys.platform != 'linux':
        return command
    workspace = directory / 'checkout'
    home = directory / 'model-home'
    home.mkdir(exist_ok=True)
    gradle = home / '.gradle'
    cached = Path(env.get('GRADLE_USER_HOME', str(Path(env['HOME']) / '.gradle')))
    for name in ['caches/modules-2', 'wrapper/dists']:
        source = cached / name
        if source.is_dir():
            shutil.copytree(source, gradle / name, dirs_exist_ok=True)
    env['HOME'] = str(home)
    env['GRADLE_USER_HOME'] = str(gradle)
    env['TMPDIR'] = '/tmp'
    args = ['bwrap', '--die-with-parent', '--new-session', '--unshare-pid',
            '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp']
    mounted = []
    for name in ['/usr', '/bin', '/sbin', '/lib', '/lib64', '/etc', '/opt']:
        if Path(name).exists():
            args += ['--ro-bind', name, name]
            mounted.append(Path(name).resolve())
    if Path('/run/systemd/resolve').is_dir():
        args += ['--ro-bind', '/run/systemd/resolve', '/run/systemd/resolve']
    def bind(path, writable=False):
        path = Path(path).resolve()
        if any(path.is_relative_to(root) for root in mounted):
            return
        args.extend(['--bind' if writable else '--ro-bind', str(path), str(path)])
        mounted.append(path)
    bind(workspace, True)
    bind(home, True)
    bind(env['CODEX_HOME'], True)
    for name in ['JAVA_HOME', 'ANDROID_HOME', 'ANDROID_SDK_ROOT']:
        if env.get(name):
            bind(env[name])
    jadx = shutil.which('jadx', path=env['PATH'])
    if jadx:
        bind(Path(jadx).resolve().parent.parent)
    args += ['--chdir', str(workspace), '--', *command]
    return args
