import {run} from './codex_live.mjs';
await run({
  info: message => console.log(message),
  warning: message => console.log(`::warning::${message}`),
  setFailed: message => {console.log(`::error::${message}`); process.exitCode = 1;}
});
