#!/usr/bin/env bash
# Run on your homelab host (Proxmox VM/LXC with Docker). Repo root = cwd of script's parent.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

for cmd in docker; do
  command -v "$cmd" >/dev/null || {
    echo "error: '$cmd' not found. Install Docker on this machine first." >&2
    exit 1
  }
done
docker compose version >/dev/null 2>&1 || {
  echo "error: 'docker compose' not available. Use Docker Engine 20.10+ with Compose v2 plugin." >&2
  exit 1
}

if [[ ! -f .env ]]; then
  if [[ -f .env.example ]]; then
    cp .env.example .env
    echo "Created .env from .env.example — set DISCORD_BOT_TOKEN and OPENCLAW_* then run this script again." >&2
    exit 1
  fi
  echo "error: missing .env (and no .env.example)" >&2
  exit 1
fi

# Non-empty token on DISCORD_BOT_TOKEN= line (do not source .env — special chars in token)
line="$(grep -E '^[[:space:]]*DISCORD_BOT_TOKEN=' .env | head -1 || true)"
val="${line#*=}"
val="${val%%#*}"
val="$(echo -n "$val" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e "s/^['\"]//" -e "s/['\"]$//")"
if [[ -z "$val" ]]; then
  echo "error: DISCORD_BOT_TOKEN is empty in .env" >&2
  exit 1
fi

oc_line="$(grep -E '^[[:space:]]*OPENCLAW_GATEWAY_URL=' .env | head -1 || true)"
oc_val="${oc_line#*=}"
oc_val="${oc_val%%#*}"
oc_val="$(printf '%s' "$oc_val" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e "s/^['\"]//" -e "s/['\"]$//")"
if [[ -z "$oc_val" ]]; then
  echo "warning: OPENCLAW_GATEWAY_URL is empty — reply-bot will reply with a config error until set." >&2
fi

docker compose up -d --build
docker compose ps
echo ""
echo "OK. Logs: cd \"$ROOT\" && docker compose logs -f"
echo "Stop:   cd \"$ROOT\" && docker compose down"
