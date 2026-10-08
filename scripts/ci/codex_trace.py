"""Stream app-server protocol records into an age-encrypted artifact."""
import json
import os
import re
import subprocess
from datetime import datetime, timezone


class EncryptedTrace:
    def __init__(self, directory, recipient):
        self.path = directory / 'session.jsonl.age'
        self.partial = directory / 'session.jsonl.age.partial'
        self.closed = False
        self.recipient = recipient
        self.pending = []
        self.pending_bytes = 0
        self.chunk_number = 0
        self.chunks = directory / 'trace-chunks'
        self.chunks.mkdir(mode=0o700, exist_ok=True)
        self.path.unlink(missing_ok=True)
        self.partial.unlink(missing_ok=True)
        if not re.fullmatch(r'age1[0-9a-z]{58}', recipient):
            raise ValueError('CODEX_TRACE_RECIPIENT must be an age X25519 public key')
        probe = subprocess.run(['age', '--encrypt', '-r', recipient], input=b'',
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        if probe.returncode:
            raise ValueError('CODEX_TRACE_RECIPIENT is not a valid age public key')
        output = os.fdopen(os.open(self.partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb')
        try:
            self.process = subprocess.Popen(['age', '--encrypt', '-r', recipient],
                                            stdin=subprocess.PIPE, stdout=output,
                                            stderr=subprocess.DEVNULL)
        except Exception:
            self.partial.unlink(missing_ok=True)
            raise
        finally:
            output.close()

    def record(self, direction, message):
        record = {'timestamp': datetime.now(timezone.utc).isoformat(),
                  'direction': direction, 'message': message}
        try:
            encoded = (json.dumps(record, ensure_ascii=False) + '\n').encode()
            self.process.stdin.write(encoded)
            self.process.stdin.flush()
            self.pending.append(encoded)
            self.pending_bytes += len(encoded)
            if len(self.pending) >= 32 or self.pending_bytes >= 1024 * 1024:
                self.checkpoint()
        except (BrokenPipeError, OSError):
            self._discard()
            raise RuntimeError('Session encryption failed; encrypted artifact discarded') from None

    def checkpoint(self):
        if not self.pending:
            return
        self.chunk_number += 1
        path = self.chunks / f'{self.chunk_number:06d}.jsonl.age'
        partial = path.with_suffix('.age.partial')
        try:
            with os.fdopen(os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as output:
                subprocess.run(['age', '--encrypt', '-r', self.recipient],
                               input=b''.join(self.pending), stdout=output,
                               stderr=subprocess.DEVNULL, timeout=30, check=True,
                               start_new_session=True)
            partial.replace(path)
            self.pending.clear()
            self.pending_bytes = 0
        finally:
            partial.unlink(missing_ok=True)

    def _discard(self):
        self.closed = True
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait()
        try:
            self.process.stdin.close()
        except OSError:
            pass
        self.partial.unlink(missing_ok=True)
        self.path.unlink(missing_ok=True)

    def close(self):
        if self.closed:
            return
        try:
            self.checkpoint()
            self.process.stdin.close()
            if self.process.wait(timeout=30):
                raise RuntimeError('Session encryption failed')
            self.partial.replace(self.path)
            self.closed = True
        except (OSError, RuntimeError, subprocess.TimeoutExpired):
            self._discard()
            raise RuntimeError('Session encryption failed; encrypted artifact discarded') from None
