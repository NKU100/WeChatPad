import {spawn, execFileSync} from 'node:child_process';
import {readFile, readdir, mkdir, writeFile, copyFile, statfs} from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';

// Runs in the trusted action process; runtime upload credentials never enter the model environment.
export async function run(core) {
  const controller = process.env.CONTROLLER_ROOT;
  const task = process.env.CODEX_TASK_DIR;
  const {DefaultArtifactClient} = await import(pathToFileURL(path.join(controller, 'node_modules/@actions/artifact/lib/artifact.js')));
  const artifacts = new DefaultArtifactClient();
  const uploaded = new Set();
  let sequence = 0;
  let stopping = false;
  let signal = null;
  const child = spawn('python3', ['-m', 'scripts.ci.codex_adaptation', 'model',
    '--directory', task, '--prompt', path.join(controller, 'adapt-wechat.md'),
    '--goal-token-budget', process.env.GOAL_TOKEN_BUDGET], {cwd: controller, stdio: 'inherit'});
  const finished = new Promise(resolve => {
    child.once('error', error => resolve({error: String(error)}));
    child.once('exit', (code, received) => resolve({code, signal: received}));
  });
  const onSignal = received => {signal = received; stopping = true; child.kill(received);};
  const term = () => onSignal('SIGTERM');
  const interrupt = () => onSignal('SIGINT');
  process.on('SIGTERM', term);
  process.on('SIGINT', interrupt);
  async function snapshot() {
    const chunks = path.join(task, 'trace-chunks');
    const names = (await readdir(chunks).catch(() => [])).filter(name => /^\d+\.jsonl\.age$/.test(name) && !uploaded.has(name)).sort();
    const root = path.join(task, 'live', String(++sequence));
    await mkdir(root, {recursive: true, mode: 0o700});
    const read = name => readFile(name, 'utf8').catch(() => 'unavailable');
    const disk = await statfs(task);
    const telemetry = {disk: {blockSize: disk.bsize, availableBlocks: disk.bavail},
      processes: execFileSync('ps', ['-eo', 'pid,ppid,rss,comm'], {encoding: 'utf8'}), timestamp: new Date().toISOString(), controllerPid: child.pid, signal,
      memory: await read('/proc/meminfo'), memoryPressure: await read('/proc/pressure/memory'),
      cgroupMemoryEvents: await read('/sys/fs/cgroup/memory.events'),
      cgroupMemoryCurrent: await read('/sys/fs/cgroup/memory.current'),
      cgroupMemoryMax: await read('/sys/fs/cgroup/memory.max')};
    const destination = path.join(root, 'runner-health.json');
    await writeFile(destination, JSON.stringify(telemetry, null, 2), {mode: 0o600});
    const files = [destination];
    for (const name of names) {
      const target = path.join(root, name);
      await copyFile(path.join(chunks, name), target);
      files.push(target);
    }
    await artifacts.uploadArtifact(`wechatpad-codex-live-${process.env.GITHUB_RUN_ATTEMPT}-${sequence}`, files, root, {retentionDays: 14});
    names.forEach(name => uploaded.add(name));
    core.info(`Saved live diagnostics ${sequence}; ${names.length} encrypted conversation chunks.`);
  }
  let outcome;
  try {
    while (!stopping) {
      try {await snapshot();} catch (error) {core.warning(`Live diagnostic upload failed: ${error.message}`);}
      let timer;
      const tick = new Promise(resolve => {timer = setTimeout(() => resolve(null), 60000);});
      outcome = await Promise.race([finished, tick]);
      clearTimeout(timer);
      if (outcome) break;
    }
    outcome ??= await finished;
    try {await snapshot();} catch (error) {core.warning(`Final diagnostic upload failed: ${error.message}`);}
    if (outcome.code !== 0) core.setFailed(`Codex controller exited: ${JSON.stringify(outcome)}`);
  } finally {
    process.off('SIGTERM', term);
    process.off('SIGINT', interrupt);
  }
}
