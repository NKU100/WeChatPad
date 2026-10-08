"""Drive one budgeted Codex goal and independently verify every completed turn."""
import base64
import json
import os
import re
import signal
import subprocess
from collections import deque
from pathlib import Path

DEFAULT_TOKEN_BUDGET = 200_000


def redact(text, secrets):
    for secret in sorted(set(secrets), key=len, reverse=True):
        if len(secret) >= 8:
            text = text.replace(secret, '[REDACTED]')
            text = text.replace(base64.b64encode(secret.encode()).decode(), '[REDACTED]')
    text = re.sub(r'eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+', '[REDACTED]', text)
    return re.sub(r'(?i)(bearer\s+|(?:access_token|refresh_token|id_token|api_key)\s*[=:]\s*)[^\s,}]+', r'\1[REDACTED]', text)


def sanitize(value, secrets):
    if isinstance(value, str):
        return redact(value, secrets)
    if isinstance(value, list):
        return [sanitize(v, secrets) for v in value]
    if isinstance(value, dict):
        return {k: sanitize(v, secrets) for k, v in value.items()}
    return value


def auth_secrets():
    path = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))) / 'auth.json'
    if not path.is_file():
        return []
    def strings(value):
        if isinstance(value, str):
            return [value]
        if isinstance(value, dict):
            return [s for v in value.values() for s in strings(v)]
        if isinstance(value, list):
            return [s for v in value for s in strings(v)]
        return []
    return strings(json.loads(path.read_text()))


class AppServer:
    def __init__(self, directory, env):
        from scripts.ci.codex_trace import EncryptedTrace
        self.directory = directory
        self.secrets = auth_secrets()
        self.events = deque()
        self.messages = []
        self.tool_output = {}
        self.sequence = 0
        self.trace = EncryptedTrace(directory, os.environ.get('CODEX_TRACE_RECIPIENT', '').strip())
        self.stderr = None
        self.process = None
        try:
            self.stderr = (directory / 'app-server.stderr.log').open('w')
            from scripts.ci.codex_sandbox import model_command
            command = model_command(directory, env,
                ['codex', 'app-server', '--listen', 'stdio://', '-c', 'features.goals=true',
                 '-c', 'features.multi_agent=false', '-c', 'features.multi_agent_v2=false',
                 '-c', 'features.apps=false', '-c', 'features.plugins=false',
                 '-c', 'features.shell_snapshot=false', '-c', 'web_search="disabled"'])
            self.process = subprocess.Popen(command,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.stderr,
                text=True, env=env, start_new_session=True)
            self.request('initialize', {'clientInfo': {'name': 'wechatpad_ci', 'version': '1'},
                                        'capabilities': {'experimentalApi': True}})
            self.send({'method': 'initialized'})
        except Exception:
            self.close()
            raise

    def send(self, message):
        self.trace.record('request', message)
        self.process.stdin.write(json.dumps(message) + '\n')
        self.process.stdin.flush()

    def read(self):
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError('Codex app-server exited before completing its request')
        message = json.loads(line)
        self.trace.record('response', message)
        if 'method' in message and 'id' in message:
            self.send({'id': message['id'], 'error': {'code': -32000, 'message': 'Interactive requests are disabled in CI'}})
            return self.read()
        if message.get('method') == 'item/commandExecution/outputDelta':
            params = message.get('params', {})
            item_id = params.get('itemId', '')
            self.tool_output[item_id] = (self.tool_output.get(item_id, '') + params.get('delta', ''))[-2000:]
        if message.get('method') == 'item/completed':
            item = message.get('params', {}).get('item', {})
            if item.get('type') == 'agentMessage':
                self.messages.append(redact(item.get('text', ''), self.secrets + auth_secrets())[:4000])
            elif item.get('type') == 'commandExecution':
                output = item.get('aggregatedOutput') or self.tool_output.pop(item.get('id', ''), '')
                if item.get('exitCode') not in {None, 0}:
                    self.messages.append(redact('Tool failure: ' + output[-2000:], self.secrets + auth_secrets()))
        return message

    def request(self, method, params):
        self.sequence += 1
        request_id = self.sequence
        self.send({'id': request_id, 'method': method, 'params': params})
        while True:
            message = self.read()
            if message.get('id') == request_id:
                if 'error' in message:
                    raise RuntimeError(redact(str(message['error']), self.secrets + auth_secrets()))
                return message.get('result', {})
            if 'method' in message:
                self.events.append(message)

    def wait_turn(self, thread, turn):
        while True:
            message = self.events.popleft() if self.events else self.read()
            params = message.get('params', {})
            if message.get('method') == 'turn/completed' and params.get('threadId') == thread and params['turn']['id'] == turn:
                return params['turn']

    def pause(self, thread):
        self.request('thread/goal/set', {'threadId': thread, 'status': 'paused'})
        # Fence an automatic continuation that raced with the controller's pause.
        state = self.request('thread/read', {'threadId': thread, 'includeTurns': True})
        for turn in state['thread'].get('turns', []):
            if turn['status'] == 'inProgress':
                self.request('turn/interrupt', {'threadId': thread, 'turnId': turn['id']})
                self.wait_turn(thread, turn['id'])

    def close(self):
        if self.process is not None and self.process.poll() is None:
            if os.getpgid(self.process.pid) == os.getpgrp():
                raise RuntimeError('Refusing to terminate the controller process group')
            os.killpg(self.process.pid, signal.SIGTERM)
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait()
        if self.stderr is not None:
            self.stderr.close()
        self.trace.close()


def verify(directory):
    from scripts.ci.codex_adaptation import validate
    validate(directory)


def write_diagnostics(directory, iterations, client):
    secrets = getattr(client, 'secrets', []) + auth_secrets()
    result = {'iterations': iterations, 'modelMessages': getattr(client, 'messages', [])[-10:]}
    (directory / 'goal-diagnostics.json').write_text(json.dumps(sanitize(result, secrets), indent=2) + '\n')


def verification_error(directory, error):
    details = str(error)
    if isinstance(error, subprocess.SubprocessError):
        logs = sorted(directory.glob('*.log'), key=lambda p: p.stat().st_mtime, reverse=True)
        for path in logs:
            if path.name not in {'app-server.stderr.log', 'model-output.log'}:
                details += '\n' + path.name + ':\n' + path.read_text(errors='replace')[-4000:]
                break
    return redact(details, auth_secrets())


def run_goal(client, directory, prompt, token_budget):
    if type(token_budget) is not int or token_budget <= 0:
        raise ValueError('Goal token budget must be a positive integer')
    workspace = directory / 'checkout'
    hidden_repository = str(Path(os.environ.get('GITHUB_WORKSPACE', '/unavailable-repository')) / '.git/HEAD')
    probe = ("from pathlib import Path; import tempfile; "
             "assert Path('work/apks/candidate.apk').is_file(); "
             "assert Path('work/analysis/candidate-report.json').is_file(); "
             "assert not Path('../state.json').exists(); "
             f"assert not Path({hidden_repository!r}).exists(); "
             "f=tempfile.TemporaryFile(dir='.'); f.write(b'probe'); f.close(); print('sandbox ready')")
    preflight = client.request('command/exec', {
        'command': ['python3', '-c', probe],
        'cwd': str(workspace), 'timeoutMs': 10000,
        'sandboxPolicy': {'type': 'workspaceWrite', 'writableRoots': [str(workspace)], 'networkAccess': False}})
    if preflight.get('exitCode') != 0:
        raise RuntimeError('Sandbox preflight failed before model invocation: ' + str(preflight.get('stderr', ''))[:2000])
    from scripts.ci.codex_adaptation import MODEL, REASONING
    thread = client.request('thread/start', {'cwd': str(directory / 'checkout'), 'model': MODEL,
        'approvalPolicy': 'never', 'sandbox': 'workspace-write', 'ephemeral': False,
        'config': {'model_reasoning_effort': REASONING, 'features.multi_agent': False,
                   'features.multi_agent_v2': False, 'features.goals': True}})['thread']['id']
    objective = prompt + '\nComplete only when the exact candidate and old-build static checks and module tests/build pass. The controller will independently verify each turn and return failures. Do not weaken checks. If evidence is insufficient, explain it and mark the goal blocked.'
    client.request('thread/goal/set', {'threadId': thread, 'objective': objective,
                                      'tokenBudget': token_budget, 'status': 'paused'})
    iterations = []
    feedback = objective
    previous_error = None
    repeated = 0
    try:
        while True:
            turn = client.request('turn/start', {'threadId': thread, 'model': MODEL, 'effort': REASONING,
                                  'input': [{'type': 'text', 'text': feedback}]})['turn']['id']
            client.request('thread/goal/set', {'threadId': thread, 'status': 'active'})
            outcome = client.wait_turn(thread, turn)
            goal = client.request('thread/goal/get', {'threadId': thread})['goal']
            client.pause(thread)
            if outcome['status'] != 'completed':
                iterations.append({'turn': turn, 'status': outcome['status'], 'error': outcome.get('error')})
                raise RuntimeError('Codex turn failed or was interrupted; see goal diagnostics')
            try:
                verify(directory)
            except (ValueError, OSError, RuntimeError, subprocess.SubprocessError, StopIteration) as error:
                reason = verification_error(directory, error)
                iterations.append({'turn': turn, 'status': 'verification-failed', 'goal': goal, 'error': reason})
                repeated = repeated + 1 if reason == previous_error else 1
                previous_error = reason
                write_diagnostics(directory, iterations, client)
                if goal is None:
                    raise RuntimeError('Codex cleared its goal before verification completed')
                if goal['status'] in {'blocked', 'budgetLimited', 'usageLimited'} or goal['tokensUsed'] >= token_budget:
                    raise RuntimeError('Codex goal stopped: ' + goal['status'])
                if repeated >= 3:
                    raise RuntimeError('The same verification failure occurred three consecutive times')
                feedback = 'Independent verification failed. Continue this same adaptation goal and correct the failure without changing its constraints:\n' + reason
            else:
                iterations.append({'turn': turn, 'status': 'verified', 'goal': goal})
                client.request('thread/goal/set', {'threadId': thread, 'status': 'complete'})
                return
    finally:
        write_diagnostics(directory, iterations, client)


def run_model_goal(directory, prompt_path, token_budget):
    allowed = {'PATH', 'HOME', 'LANG', 'LC_ALL', 'JAVA_HOME', 'ANDROID_HOME', 'ANDROID_SDK_ROOT',
               'GRADLE_USER_HOME', 'CODEX_HOME', 'SSL_CERT_FILE', 'TMPDIR'}
    env = {key: value for key, value in os.environ.items() if key in allowed}
    if type(token_budget) is not int or token_budget <= 0:
        raise ValueError('Goal token budget must be a positive integer')
    client = None
    def interrupted(number, frame):
        raise InterruptedError(f'Controller received signal {number}')
    handlers = {number: signal.signal(number, interrupted) for number in [signal.SIGTERM, signal.SIGINT]}
    try:
        client = AppServer(directory, env)
        run_goal(client, directory, prompt_path.read_text(), token_budget)
    except Exception as error:
        path = directory / 'goal-diagnostics.json'
        diagnostics = json.loads(path.read_text()) if path.is_file() else {}
        secrets = getattr(client, 'secrets', []) + auth_secrets()
        diagnostics['controllerError'] = redact(str(error), secrets)
        stderr = directory / 'app-server.stderr.log'
        if stderr.is_file():
            diagnostics['serverErrorTail'] = redact(stderr.read_text(errors='replace')[-2000:], secrets)
        path.write_text(json.dumps(diagnostics, indent=2) + '\n')
        raise
    finally:
        for number, handler in handlers.items():
            signal.signal(number, handler)
        if client is not None:
            client.close()
