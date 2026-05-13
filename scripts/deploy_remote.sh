#!/usr/bin/env bash
# From your Mac: read secrets from Cursor mcp.json, push .env to the **OpenClaw と同居**したホスト, git pull + compose.
# リモートの OPENCLAW_GATEWAY_URL は **ループバック**（デフォルト http://127.0.0.1:18789）。MCP の Tailscale URL は使わない。
#
#   export HOMELAB_SSH='user@192.168.x.x'    # required（OpenClaw Gateway が動いている VM）
#   optional: OPENCLAW_GATEWAY_LOCAL_URL=http://127.0.0.1:18789
#   optional: HOMELAB_REPO_DIR=/root/discord-mcp
#   optional: HOMELAB_GIT_URL=... HOMELAB_SSH_OPTS='-i ~/.ssh/id_ed25519'
#   optional: MCP_JSON_PATH=~/.cursor/mcp.json    (default)
#   optional: DISCORD_USE_MCP_GATEWAY_URL=1   # .env の URL を mcp の OPENCLAW_GATEWAY_URL に（Gateway が別ホストのとき）

: "${HOMELAB_SSH:?Set HOMELAB_SSH, e.g. export HOMELAB_SSH='you@192.168.1.50'}"

REPO_ARG="${HOMELAB_REPO_DIR:-}"
GIT_URL="${HOMELAB_GIT_URL:-https://github.com/taka392/discord-mcp.git}"

# Avoid empty-array + set -u issues across bash versions; optional extra ssh args.
_ssh() {
  if [[ -n "${HOMELAB_SSH_OPTS:-}" ]]; then
    # shellcheck disable=SC2086
    ssh $HOMELAB_SSH_OPTS "$@"
  else
    ssh "$@"
  fi
}
_scp() {
  if [[ -n "${HOMELAB_SSH_OPTS:-}" ]]; then
    # shellcheck disable=SC2086
    scp $HOMELAB_SSH_OPTS "$@"
  else
    scp "$@"
  fi
}

TMP="$(mktemp)"
chmod 600 "$TMP"
trap 'rm -f "$TMP"' EXIT

export TMP_ENV_PATH="$TMP"
export OPENCLAW_GATEWAY_LOCAL_URL="${OPENCLAW_GATEWAY_LOCAL_URL:-http://127.0.0.1:18789}"
export DISCORD_USE_MCP_GATEWAY_URL="${DISCORD_USE_MCP_GATEWAY_URL:-}"

if [[ -n "${DISCORD_BOT_TOKEN:-}" ]]; then
  {
    printf 'COMPOSE_PROFILES=prod\n'
    printf 'DISCORD_BOT_TOKEN=%s\n' "$DISCORD_BOT_TOKEN"
    printf 'OPENCLAW_GATEWAY_URL=%s\n' "${OPENCLAW_GATEWAY_LOCAL_URL}"
    printf 'OPENCLAW_CHAT_MODEL=%s\n' "${OPENCLAW_CHAT_MODEL:-google/gemini-3.1-pro-preview}"
  } > "$TMP"
  echo "warning: only DISCORD_BOT_TOKEN set — add OPENCLAW_GATEWAY_TOKEN to remote .env manually." >&2
else
  MCP_JSON_PATH="${MCP_JSON_PATH:-$HOME/.cursor/mcp.json}"
  export MCP_JSON_PATH
  python3 -c "
import json, os, pathlib
p = pathlib.Path(os.environ['MCP_JSON_PATH']).expanduser()
if not p.is_file():
    raise SystemExit(f'missing MCP JSON: {p}')
d = json.loads(p.read_text(encoding='utf-8'))
srv = d.get('mcpServers') or {}
dt = (srv.get('discord', {}).get('env', {}).get('DISCORD_BOT_TOKEN') or '').strip()
oc = srv.get('openclaw', {}).get('env', {}) or {}
ot = str(oc.get('OPENCLAW_GATEWAY_TOKEN') or '').strip()
op = str(oc.get('OPENCLAW_GATEWAY_PASSWORD') or '').strip()
ocm = str(oc.get('OPENCLAW_CHAT_MODEL') or '').strip() or 'google/gemini-3.1-pro-preview'
local_u = (os.environ.get('OPENCLAW_GATEWAY_LOCAL_URL') or 'http://127.0.0.1:18789').strip()
mcp_u = str(oc.get('OPENCLAW_GATEWAY_URL') or '').strip()
use_mcp = os.environ.get('DISCORD_USE_MCP_GATEWAY_URL', '').strip().lower() in ('1', 'true', 'yes')
gateway_u = mcp_u if use_mcp else local_u
if use_mcp and not mcp_u:
    raise SystemExit('DISCORD_USE_MCP_GATEWAY_URL=1 requires OPENCLAW_GATEWAY_URL in mcp.json')
if not dt:
    raise SystemExit(
        'DISCORD_BOT_TOKEN empty in mcp.json (mcpServers.discord.env). '
        'Set it in Cursor MCP or export DISCORD_BOT_TOKEN for this script.'
    )
if not (ot or op):
    raise SystemExit(
        'mcpServers.openclaw.env needs OPENCLAW_GATEWAY_TOKEN (or PASSWORD).'
    )
lines = [
    'COMPOSE_PROFILES=prod',
    f'DISCORD_BOT_TOKEN={dt}',
    f'OPENCLAW_GATEWAY_URL={gateway_u}',
    f'OPENCLAW_CHAT_MODEL={ocm}',
]
lines.append(f'OPENCLAW_GATEWAY_TOKEN={ot}' if ot else f'OPENCLAW_GATEWAY_PASSWORD={op}')
pathlib.Path(os.environ['TMP_ENV_PATH']).write_text('\\n'.join(lines) + '\\n', encoding='utf-8')
" || exit 1
fi

if [[ -n "${HOMELAB_REPO_DIR:-}" ]]; then
  SCP_TARGET="${HOMELAB_SSH}:${HOMELAB_REPO_DIR}/.env"
else
  SCP_TARGET="${HOMELAB_SSH}:~/discord-mcp/.env"
fi

echo "==> ${HOMELAB_SSH}: git clone/pull (repo: ${HOMELAB_REPO_DIR:-\$HOME/discord-mcp})"
# Pass repo/URL via env — some ssh versions mishandle bash -s positional args after --.
_ssh "$HOMELAB_SSH" env \
  "REMOTE_REPO_ARG=${REPO_ARG}" \
  "REMOTE_GIT_URL=${GIT_URL}" \
  bash -s <<'REMOTE'
set -euo pipefail
REPO="${REMOTE_REPO_ARG:-}"
GIT_URL="${REMOTE_GIT_URL:-}"
if [[ -z "$REPO" ]]; then
  REPO="$HOME/discord-mcp"
fi
if [[ -z "$GIT_URL" ]]; then
  echo "error: REMOTE_GIT_URL empty" >&2
  exit 1
fi

if [[ ! -d "$REPO/.git" ]]; then
  parent="$(dirname "$REPO")"
  mkdir -p "$parent"
  git clone "$GIT_URL" "$REPO"
fi

cd "$REPO"
git pull --ff-only
REMOTE

echo "==> scp .env (from mcp.json or DISCORD_BOT_TOKEN env) -> ${SCP_TARGET}"
_scp "$TMP" "$SCP_TARGET"

echo "==> docker compose up"
_ssh "$HOMELAB_SSH" env "REMOTE_REPO_ARG=${REPO_ARG}" bash -s <<'REMOTE'
set -euo pipefail
REPO="${REMOTE_REPO_ARG:-}"
if [[ -z "$REPO" ]]; then
  REPO="$HOME/discord-mcp"
fi
cd "$REPO"
chmod 600 .env 2>/dev/null || true
exec ./scripts/homelab_docker_up.sh
REMOTE

echo "==> Remote deploy finished."
