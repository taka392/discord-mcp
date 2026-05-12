#!/usr/bin/env python3
"""VM 上の /root/discord-mcp/.env を再生成し、agent-gateway に CURSOR_API_KEY を入れる。

Discord ボットの「ゲートウェイが利用できません (503)」は、このキー欠落時に返ります。

前提:
  - 環境変数 ``CURSOR_API_KEY``（Cursor ヘッドレス用 ``crsr_...``）をセット
  - ``~/.cursor/mcp.json`` の ``discord`` / ``cursor-homelab`` でトークン類を読む
  - Proxmox: ``PROXMOX_BASE_URL`` 等（proxmox-mcp と同じ）

例::
  export CURSOR_API_KEY='crsr_...'
  export PROXMOX_BASE_URL=... PROXMOX_TOKEN_ID=... PROXMOX_TOKEN_SECRET=... PROXMOX_VERIFY_TLS=false
  python3 scripts/push_gateway_env_guest_exec.py --vmid 100

キー発行: https://cursor.com/docs/cli/headless（ダッシュボードの API keys）
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
    api_key = (os.getenv("CURSOR_API_KEY") or "").strip()
    if not api_key:
        print(
            "CURSOR_API_KEY が空です。crsr_ で始まるキーを環境変数で渡してください。\n"
            "  https://cursor.com/docs/cli/headless",
            file=sys.stderr,
        )
        return 1

    p = pathlib.Path.home() / ".cursor" / "mcp.json"
    mcp = json.loads(p.read_text(encoding="utf-8"))
    srv = mcp.get("mcpServers") or {}
    discord_t = (srv.get("discord", {}).get("env", {}).get("DISCORD_BOT_TOKEN") or "").strip()
    hl = srv.get("cursor-homelab", {}).get("env", {}) or {}
    gw_tok = str(hl.get("CURSOR_HOMELAB_TOKEN") or "").strip()
    if not discord_t or not gw_tok:
        print("mcp.json に discord と cursor-homelab のトークンが必要です。", file=sys.stderr)
        return 1

    lines = f"""# push_gateway_env_guest_exec.py（コミット禁止）
DISCORD_BOT_TOKEN={discord_t}
CURSOR_AGENT_GATEWAY_URL=http://agent-gateway:9888
GATEWAY_TOKEN={gw_tok}
GATEWAY_ENFORCE_TOKEN=true

CURSOR_API_KEY={api_key}

AGENT_APPROVE_MCPS=true
AGENT_REQUEST_TIMEOUT_SEC=600

CURSOR_GATEWAY_TRUST_WORKSPACE=true
CURSOR_GATEWAY_TIMEOUT_SEC=600
"""
    b64 = base64.b64encode(lines.encode("utf-8")).decode("ascii")
    bash = """set -euo pipefail
cd /root/discord-mcp
mkdir -p workspace
printf '%s' {b64} | base64 -d > .env
chmod 600 .env
docker compose up -d --force-recreate
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

    print("Done.ゲートウェイ再起動済み。", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
