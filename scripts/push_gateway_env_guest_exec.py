#!/usr/bin/env python3
"""**OpenClaw Gateway と同一 VM** 上の ``discord-mcp`` に ``.env`` を流し込み ``docker compose up`` する。

ボットは ``network_mode: host`` で ``OPENCLAW_GATEWAY_URL=http://127.0.0.1:<port>`` へ向ける（MCP の Tailscale URL は使わない）。

``~/.cursor/mcp.json`` の ``discord`` / ``openclaw`` からトークンを読みます（URL はローカル固定可）。

例::

  export PROXMOX_BASE_URL=... PROXMOX_TOKEN_ID=... PROXMOX_TOKEN_SECRET=... PROXMOX_VERIFY_TLS=false
  python3 scripts/push_gateway_env_guest_exec.py --vmid 100

  # Gateway の listen ポートが 18789 でない場合:
  python3 scripts/push_gateway_env_guest_exec.py --vmid 100 --local-gateway-url http://127.0.0.1:9999

（旧 Cursor-only: VM 上で ``DISCORD_LLM_BACKEND=cursor`` と ``CURSOR_AGENT_GATEWAY_URL`` を手編集）
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import pathlib
import sys

_REPO = pathlib.Path(__file__).resolve().parents[1]
_PROXMOX_MCP = _REPO.parent / "proxmox-mcp"
if str(_PROXMOX_MCP) not in sys.path:
    sys.path.insert(0, str(_PROXMOX_MCP))

from proxmox_mcp.client import ProxmoxClient, ProxmoxError  # noqa: E402


def _shell_sq(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vmid", type=int, default=100)
    ap.add_argument("--node", default=os.getenv("PROXMOX_NODE", "pve"))
    ap.add_argument("--timeout", type=float, default=300.0)
    ap.add_argument(
        "--repo-dir",
        default="/root/discord-mcp",
        help="Guest absolute path (default: /root/discord-mcp)",
    )
    ap.add_argument(
        "--local-gateway-url",
        default=os.getenv("OPENCLAW_GATEWAY_LOCAL_URL", "http://127.0.0.1:18789"),
        help="Bot -> OpenClaw on same host (default: env OPENCLAW_GATEWAY_LOCAL_URL or :18789)",
    )
    args = ap.parse_args()

    mcp_path = pathlib.Path.home() / ".cursor" / "mcp.json"
    mcp = json.loads(mcp_path.read_text(encoding="utf-8"))
    srv = mcp.get("mcpServers") or {}
    discord_t = (srv.get("discord", {}).get("env", {}).get("DISCORD_BOT_TOKEN") or "").strip()
    oc = srv.get("openclaw", {}).get("env", {}) or {}
    oc_tok = str(oc.get("OPENCLAW_GATEWAY_TOKEN") or "").strip()
    oc_pw = str(oc.get("OPENCLAW_GATEWAY_PASSWORD") or "").strip()
    oc_model = str(oc.get("OPENCLAW_CHAT_MODEL") or "").strip() or "google/gemini-3.1-pro-preview"
    if not discord_t:
        print("mcp.json: mcpServers.discord.env.DISCORD_BOT_TOKEN が必要です。", file=sys.stderr)
        return 1
    if not (oc_tok or oc_pw):
        print(
            "mcp.json: mcpServers.openclaw.env に "
            "OPENCLAW_GATEWAY_TOKEN（または PASSWORD）が必要です。",
            file=sys.stderr,
        )
        return 1

    oc_url = str(args.local_gateway_url or "").strip()
    if not oc_url:
        oc_url = "http://127.0.0.1:18789"

    auth_line = f"OPENCLAW_GATEWAY_TOKEN={oc_tok}" if oc_tok else f"OPENCLAW_GATEWAY_PASSWORD={oc_pw}"

    lines = f"""# push_gateway_env_guest_exec.py（OpenClaw 同居 VM・.env はコミット禁止）
COMPOSE_PROFILES=prod
DISCORD_BOT_TOKEN={discord_t}
OPENCLAW_GATEWAY_URL={oc_url}
OPENCLAW_CHAT_MODEL={oc_model}
{auth_line}
"""
    b64 = base64.b64encode(lines.encode("utf-8")).decode("ascii")
    repo_sq = _shell_sq(args.repo_dir)
    bash = f"""set -euo pipefail
cd {repo_sq}
git pull --ff-only
mkdir -p workspace
printf '%s' {_shell_sq(b64)} | base64 -d > .env
chmod 600 .env
docker compose up -d --build --force-recreate
docker compose ps
"""

    try:
        client = ProxmoxClient()
    except ProxmoxError as exc:
        print(exc, file=sys.stderr)
        return 1

    try:
        out = client.qemu_guest_exec_wait(
            args.node,
            args.vmid,
            ["/bin/bash", "-lc", bash],
            timeout_seconds=args.timeout,
        )
    except ProxmoxError as exc:
        print(exc, file=sys.stderr)
        return 1

    if out.get("timeout"):
        print("guest exec timed out", file=sys.stderr)
        return 124
    if (out.get("out") or "").strip():
        print(out["out"])
    if (out.get("err") or "").strip():
        print(out["err"], file=sys.stderr)

    xc = out.get("exitcode")
    if xc not in (0, None):
        return int(xc) & 255 or 1

    print("Done. docker compose 再起動済み（OpenClaw 同居用 .env）。", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
