#!/usr/bin/env python3
"""**OpenClaw Gateway と同一 VM** 上の ``discord-mcp`` に ``.env`` を流し込み ``docker compose up`` する。

ボットは ``network_mode: host`` 想定。``.env`` の ``OPENCLAW_GATEWAY_URL`` は次のどちらか。

- **同居**（同一 VM に Gateway を起動している）: ``http://127.0.0.1:<port>`` （``--local-gateway-url``）
- **別ホスト**（Gateway が Tailscale / 別マシン）: MCP と同じ URL（``--use-mcp-gateway-url``）

``--vmid`` は **OpenClaw が動いている Proxmox 上の QEMU vmid**（Discord 専用 VM など別 ID ではない）。

例::

  export PROXMOX_BASE_URL=... PROXMOX_TOKEN_ID=... PROXMOX_TOKEN_SECRET=... PROXMOX_VERIFY_TLS=false
  export OPENCLAW_QEMU_VMID=101   # OpenClaw ホストの vmid（毎回 --vmid でも可）
  python3 scripts/push_gateway_env_guest_exec.py --vmid 101

  # OpenClaw がボットと別マシン（Tailscale 等）のとき、mcp.json の URL を .env に使う:
  python3 scripts/push_gateway_env_guest_exec.py --vmid 101 --use-mcp-gateway-url

  # Gateway の listen ポートが 18789 でない同一 VM のとき:
  python3 scripts/push_gateway_env_guest_exec.py --vmid 101 --local-gateway-url http://127.0.0.1:9999

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


def _resolve_vmid(explicit: int | None) -> int | None:
    if explicit is not None:
        return explicit
    for key in ("OPENCLAW_QEMU_VMID", "DISCORD_MCP_QEMU_VMID"):
        raw = os.getenv(key, "").strip()
        if raw.isdigit():
            return int(raw)
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--vmid",
        type=int,
        default=None,
        metavar="N",
        help="QEMU vmid of the **VM that runs OpenClaw** (or set OPENCLAW_QEMU_VMID)",
    )
    ap.add_argument("--node", default=os.getenv("PROXMOX_NODE", "pve"))
    ap.add_argument("--timeout", type=float, default=300.0)
    ap.add_argument(
        "--repo-dir",
        default="/root/discord-mcp",
        help="Guest absolute path (default: /root/discord-mcp)",
    )
    ap.add_argument(
        "--git-url",
        default=os.getenv("DISCORD_MCP_GIT_URL", "https://github.com/taka392/discord-mcp.git"),
        help="Clone URL if repo-dir does not exist yet",
    )
    ap.add_argument(
        "--local-gateway-url",
        default=os.getenv("OPENCLAW_GATEWAY_LOCAL_URL", "http://127.0.0.1:18789"),
        help="Bot -> OpenClaw on same host (default: env OPENCLAW_GATEWAY_LOCAL_URL or :18789)",
    )
    ap.add_argument(
        "--use-mcp-gateway-url",
        action="store_true",
        help="Set OPENCLAW_GATEWAY_URL from mcpServers.openclaw.env (when Gateway is on another host)",
    )
    args = ap.parse_args()

    vmid = _resolve_vmid(args.vmid)
    if vmid is None:
        print(
            "error: OpenClaw を動かしている VM の Proxmox vmid を指定してください。"
            " 例: --vmid 101  または  export OPENCLAW_QEMU_VMID=101"
            "（VM100 は別用途のこともあるので、既定の vmid はありません）。",
            file=sys.stderr,
        )
        return 2

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

    if args.use_mcp_gateway_url:
        oc_url = str(oc.get("OPENCLAW_GATEWAY_URL") or "").strip()
        if not oc_url:
            print(
                "mcp.json: --use-mcp-gateway-url には mcpServers.openclaw.env.OPENCLAW_GATEWAY_URL が必要です。",
                file=sys.stderr,
            )
            return 1
    else:
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
    git_sq = _shell_sq(args.git_url)
    bash = f"""set -euo pipefail
REPO={repo_sq}
GIT_URL={git_sq}
if [[ ! -d "$REPO/.git" ]]; then
  parent="$(dirname "$REPO")"
  mkdir -p "$parent"
  git clone "$GIT_URL" "$REPO"
fi
cd "$REPO"
git pull --ff-only
mkdir -p workspace
printf '%s' {_shell_sq(b64)} | base64 -d > .env
chmod 600 .env
if ! command -v docker >/dev/null 2>&1; then
  echo "error: このゲストに docker がありません。OpenClaw と同じ VM で compose するなら Docker をインストールするか、" >&2
  echo "error: 別 VM でボットだけ動かすなら、その VM の .env で OPENCLAW_GATEWAY_URL をこのホストへ届く URL（例: http://$(tailscale ip -4 2>/dev/null || true):18789 ）に設定してください。" >&2
  exit 127
fi
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
            vmid,
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
