#!/usr/bin/env bash
# From your Mac: read DISCORD_BOT_TOKEN from Cursor MCP config, push .env to homelab, pull + docker compose.
#
#   export HOMELAB_SSH='user@192.168.x.x'    # required
#   optional: HOMELAB_REPO_DIR=/opt/discord-mcp   (default on remote: ~/discord-mcp)
#   optional: HOMELAB_GIT_URL=... HOMELAB_SSH_OPTS='-i ~/.ssh/id_ed25519'
#   optional: MCP_JSON_PATH=~/.cursor/mcp.json    (default)
#   optional: DISCORD_BOT_TOKEN=...               (if set, skips mcp.json)
#
set -euo pipefail

: "${HOMELAB_SSH:?Set HOMELAB_SSH, e.g. export HOMELAB_SSH='you@192.168.1.50'}"

REPO_ARG="${HOMELAB_REPO_DIR:-}"
GIT_URL="${HOMELAB_GIT_URL:-https://github.com/taka392/discord-mcp.git}"

# shellcheck disable=SC2206
SSH_EXTRA=(${HOMELAB_SSH_OPTS:-})

TMP="$(mktemp)"
chmod 600 "$TMP"
trap 'rm -f "$TMP"' EXIT

if [[ -n "${DISCORD_BOT_TOKEN:-}" ]]; then
  printf 'DISCORD_BOT_TOKEN=%s\n' "$DISCORD_BOT_TOKEN" > "$TMP"
else
  MCP_JSON_PATH="${MCP_JSON_PATH:-$HOME/.cursor/mcp.json}"
  export MCP_JSON_PATH
  TOKEN="$(python3 -c "
import json, os, pathlib
p = pathlib.Path(os.environ['MCP_JSON_PATH']).expanduser()
if not p.is_file():
    raise SystemExit(f'missing MCP JSON: {p}')
d = json.loads(p.read_text(encoding='utf-8'))
t = (d.get('mcpServers') or {}).get('discord', {}).get('env', {}).get('DISCORD_BOT_TOKEN') or ''
t = str(t).strip()
if not t:
    raise SystemExit(
        'DISCORD_BOT_TOKEN empty in mcp.json (mcpServers.discord.env). '
        'Set it in Cursor MCP or export DISCORD_BOT_TOKEN for this script.'
    )
print(t, end='')
")"
  printf 'DISCORD_BOT_TOKEN=%s\n' "$TOKEN" > "$TMP"
fi

if [[ -n "${HOMELAB_REPO_DIR:-}" ]]; then
  SCP_TARGET="${HOMELAB_SSH}:${HOMELAB_REPO_DIR}/.env"
else
  SCP_TARGET="${HOMELAB_SSH}:~/discord-mcp/.env"
fi

echo "==> ${HOMELAB_SSH}: git clone/pull (repo: ${HOMELAB_REPO_DIR:-\$HOME/discord-mcp})"
ssh "${SSH_EXTRA[@]}" "$HOMELAB_SSH" bash -s -- "$REPO_ARG" "$GIT_URL" <<'REMOTE'
set -euo pipefail
REPO="${1:-}"
GIT_URL="${2:-}"
if [[ -z "$REPO" ]]; then
  REPO="$HOME/discord-mcp"
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
scp "${SSH_EXTRA[@]}" "$TMP" "$SCP_TARGET"

echo "==> docker compose up"
ssh "${SSH_EXTRA[@]}" "$HOMELAB_SSH" bash -s -- "$REPO_ARG" <<'REMOTE'
set -euo pipefail
REPO="${1:-}"
if [[ -z "$REPO" ]]; then
  REPO="$HOME/discord-mcp"
fi
cd "$REPO"
chmod 600 .env 2>/dev/null || true
exec ./scripts/homelab_docker_up.sh
REMOTE

echo "==> Remote deploy finished."
