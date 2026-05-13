#!/usr/bin/env python3
"""VM 上の ``/root/discord-mcp/.env`` を OpenClaw 用に再生成し ``docker compose up`` する。

既定の ``docker compose`` スタックは **discord-reply-bot のみ**（bundled agent-gateway なし）。
``~/.cursor/mcp.json`` の ``discord`` / ``openclaw`` からトークンと URL を読みます。

例::

  export PROXMOX_BASE_URL=... PROXMOX_TOKEN_ID=... PROXMOX_TOKEN_SECRET=... PROXMOX_VERIFY_TLS=false
  python3 scripts/push_gateway_env_guest_exec.py --vmid 100

（旧 Cursor-only の一括投入が必要な場合は、VM 上で手編集し ``DISCORD_LLM_BACKEND=cursor`` と
外部の ``CURSOR_AGENT_GATEWAY_URL`` を設定してください。）
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
    p = pathlib.Path.home() / ".cursor" / "mcp.json"
    mcp = json.loads(p.read_text(encoding="utf-8"))
    srv = mcp.get("mcpServers") or {}
    discord_t = (srv.get("discord", {}).get("env", {}).get("DISCORD_BOT_TOKEN") or "").strip()
    oc = srv.get("openclaw", {}).get("env", {}) or {}
    oc_url = str(oc.get("OPENCLAW_GATEWAY_URL") or "").strip()
    oc_tok = str(oc.get("OPENCLAW_GATEWAY_TOKEN") or "").strip()
    oc_pw = str(oc.get("OPENCLAW_GATEWAY_PASSWORD") or "").strip()
    if not discord_t:
        print("mcp.json: mcpServers.discord.env.DISCORD_BOT_TOKEN が必要です。", file=sys.stderr)
        return 1
    if not oc_url or not (oc_tok or oc_pw):
        print(
            "mcp.json: mcpServers.openclaw.env に OPENCLAW_GATEWAY_URL と "
            "OPENCLAW_GATEWAY_TOKEN（または PASSWORD）が必要です。",
            file=sys.stderr,
        )
        return 1

    auth_line = f"OPENCLAW_GATEWAY_TOKEN={oc_tok}" if oc_tok else f"OPENCLAW_GATEWAY_PASSWORD={oc_pw}"

    lines = f"""# push_gateway_env_guest_exec.py（コミット禁止・OpenClaw 既定）
DISCORD_BOT_TOKEN={discord_t}
OPENCLAW_GATEWAY_URL={oc_url}
{auth_line}
"""
    b64 = base64.b64encode(lines.encode("utf-8")).decode("ascii")
    bash = """set -euo pipefail
cd /root/discord-mcp
mkdir -p workspace
printf '%s' {b64} | base64 -d > .env
chmod 600 .env
docker compose up -d --build --force-recreate
docker compose ps
""".format(b64=_shell_sq(b64))

    ap = argparse.ArgumentParser()
    ap.add_argument("--vmid", type=int, default=100)
    ap.add_argument("--node", default=os.getenv("PROXMOX_NODE", "pve"))
    ap.add_argument("--timeout", type=float, default=300.0)
    args = ap.parse_args()

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

    print("Done. docker compose 再起動済み（OpenClaw 用 .env）.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
