#!/usr/bin/env bash
# From your Mac (or any machine with SSH): clone/pull on homelab and run Docker compose there.
# Does not read your Discord token locally — .env must already exist on the remote host once.
#
#   export HOMELAB_SSH='user@192.168.x.x'   # required
#   optional: HOMELAB_REPO_DIR=/opt/discord-mcp   (default on remote: ~/discord-mcp)
#   optional: HOMELAB_GIT_URL=... HOMELAB_SSH_OPTS='-i ~/.ssh/id_ed25519'
#
# First time on remote: after clone, SSH in and edit ~/discord-mcp/.env (DISCORD_BOT_TOKEN), or:
#   scp .env "${HOMELAB_SSH}:~/discord-mcp/.env"
#
set -euo pipefail

: "${HOMELAB_SSH:?Set HOMELAB_SSH, e.g. export HOMELAB_SSH='you@192.168.1.50'}"

REPO_ARG="${HOMELAB_REPO_DIR:-}"
GIT_URL="${HOMELAB_GIT_URL:-https://github.com/taka392/discord-mcp.git}"

# shellcheck disable=SC2206
SSH_EXTRA=(${HOMELAB_SSH_OPTS:-})

echo "==> SSH ${HOMELAB_SSH}: pull + docker compose (repo: ${REPO_ARG:-\$HOME/discord-mcp})"

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

exec ./scripts/homelab_docker_up.sh
REMOTE

echo "==> Remote deploy finished."
