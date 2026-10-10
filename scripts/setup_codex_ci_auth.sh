#!/usr/bin/env bash
set -euo pipefail

repository="${1:-NKU100/ImPad}"
auth_directory="$(mktemp -d "${TMPDIR:-/tmp}/impad-codex-ci.XXXXXX")"
trap 'rm -rf "$auth_directory"' EXIT
chmod 700 "$auth_directory"

# A separate login keeps CI token rotation independent of desktop sessions.
CODEX_HOME="$auth_directory" codex login --device-auth \
  -c 'cli_auth_credentials_store="file"'

python3 - "$auth_directory/auth.json" <<'PY'
import json, sys
from pathlib import Path
auth = json.loads(Path(sys.argv[1]).read_text())
if auth.get('auth_mode') != 'chatgpt' or not auth.get('tokens', {}).get('refresh_token'):
    raise SystemExit('A dedicated managed ChatGPT login with a refresh token is required.')
PY

gh secret set CODEX_AUTH_JSON --repo "$repository" < "$auth_directory/auth.json"
echo 'Dedicated CI authentication stored in CODEX_AUTH_JSON; temporary local credentials removed on exit.'
