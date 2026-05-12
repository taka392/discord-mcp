#!/usr/bin/env python3
"""Proxmox API + QEMU Guest Agent で VM 内に discord-mcp の返信ボットを常駐起動する。

前提:
  - ゲストで qemu-guest-agent が動いていること
  - API トークンに VM.GuestAgent.Unrestricted 相当
  - ゲストに Docker / docker compose v2、git
  - デフォルトは ``/root/discord-mcp``（ゲストが root のみの場合）。Ubuntu ユーザーがある場合は
    ``--unix-user ubuntu --repo-dir /home/ubuntu/discord-mcp`` を指定。
  - git / .env は ``sudo -u <user>``、Docker はそのユーザーが docker グループならそのユーザー、
    そうでなければ root で ``docker compose`` を実行。

トークンは **Base64 で埋め込み**、VM 内でデコードして .env に書きます（シェル展開で壊れにくい）。

例:
  export PROXMOX_BASE_URL=... PROXMOX_TOKEN_ID=... PROXMOX_TOKEN_SECRET=... PROXMOX_VERIFY_TLS=false
  python3 scripts/deploy_guest_exec.py --vmid 100

  # cloud-init で ubuntu がある場合:
  python3 scripts/deploy_guest_exec.py --vmid 100 --unix-user ubuntu --repo-dir /home/ubuntu/discord-mcp
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import pathlib
import sys

_DISCORD_MCP_ROOT = pathlib.Path(__file__).resolve().parents[1]
_PROXMOX_MCP = _DISCORD_MCP_ROOT.parent / "proxmox-mcp"
if str(_PROXMOX_MCP) not in sys.path:
    sys.path.insert(0, str(_PROXMOX_MCP))

from proxmox_mcp.client import ProxmoxClient, ProxmoxError  # noqa: E402


def _load_token(mcp_json_path: pathlib.Path, server_key: str) -> str:
    if os.getenv("DISCORD_BOT_TOKEN", "").strip():
        return os.getenv("DISCORD_BOT_TOKEN", "").strip()
    if not mcp_json_path.is_file():
        raise SystemExit(f"Missing {mcp_json_path}; set DISCORD_BOT_TOKEN or fix --mcp-json")
    data = json.loads(mcp_json_path.read_text(encoding="utf-8"))
    token = (
        (data.get("mcpServers") or {})
        .get(server_key, {})
        .get("env", {})
        .get("DISCORD_BOT_TOKEN", "")
    )
    token = str(token).strip()
    if not token:
        raise SystemExit(
            f"DISCORD_BOT_TOKEN empty in mcpServers.{server_key}.env "
            "or set DISCORD_BOT_TOKEN in the environment."
        )
    return token


def _shell_sq(value: str) -> str:
    """Escape for safe embedding in bash single-quoted strings."""
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _remote_bash(repo_dir: str, unix_user: str, git_url: str, b64_token: str) -> str:
    repo_q = _shell_sq(repo_dir)
    user_q = _shell_sq(unix_user)
    git_q = _shell_sq(git_url)
    return """set -euo pipefail
REPO={repo}
USER={user}
GIT_URL={git}
B64_TOKEN='{b64}'

if ! id "$USER" >/dev/null 2>&1; then
  echo "error: user $USER does not exist" >&2
  exit 1
fi

parent="$(dirname "$REPO")"
sudo mkdir -p "$parent"
if [[ ! -d "$REPO/.git" ]]; then
  sudo -u "$USER" git clone "$GIT_URL" "$REPO"
fi
sudo chown -R "$USER:$USER" "$REPO"

sudo -u "$USER" bash -lc "set -euo pipefail && cd \"$REPO\" && git pull --ff-only"

sudo -u "$USER" bash -lc "set -euo pipefail && cd \"$REPO\" && umask 077 && printf 'DISCORD_BOT_TOKEN=%s\\n' \"$(printf '%s' \"$B64_TOKEN\" | base64 -d)\" > .env && chmod 600 .env"

if id -nG "$USER" 2>/dev/null | grep -qw docker; then
  sudo -u "$USER" bash -lc "set -euo pipefail && cd \"$REPO\" && ./scripts/homelab_docker_up.sh"
else
  bash -lc "set -euo pipefail && cd \"$REPO\" && ./scripts/homelab_docker_up.sh"
fi
""".format(repo=repo_q, user=user_q, git=git_q, b64=b64_token)


def main() -> int:
    p = argparse.ArgumentParser(description="Deploy discord-reply-bot on a Proxmox QEMU VM via guest agent")
    p.add_argument("--node", default=os.getenv("PROXMOX_NODE", "pve"))
    p.add_argument("--vmid", type=int, default=100, help="QEMU VM ID (default: 100)")
    p.add_argument(
        "--repo-dir",
        default="/root/discord-mcp",
        help="Absolute path on guest (default: /root/discord-mcp)",
    )
    p.add_argument("--unix-user", default="root", help="Owner of clone + .env (default: root)")
    p.add_argument(
        "--git-url",
        default="https://github.com/taka392/discord-mcp.git",
    )
    p.add_argument(
        "--mcp-json",
        type=pathlib.Path,
        default=pathlib.Path.home() / ".cursor" / "mcp.json",
        help="Cursor MCP config to read DISCORD_BOT_TOKEN (if env unset)",
    )
    p.add_argument(
        "--mcp-server-key",
        default="discord",
        help="Key under mcpServers (default: discord)",
    )
    p.add_argument("--timeout", type=float, default=600.0)
    args = p.parse_args()

    try:
        token = _load_token(args.mcp_json, args.mcp_server_key)
    except SystemExit as exc:
        print(str(exc), file=sys.stderr)
        return 1

    b64 = base64.b64encode(token.encode("utf-8")).decode("ascii")
    bash_src = _remote_bash(args.repo_dir, args.unix_user, args.git_url, b64)

    try:
        client = ProxmoxClient()
    except ProxmoxError as exc:
        print(f"auth/config error: {exc}", file=sys.stderr)
        return 1

    argv = ["/bin/bash", "-lc", bash_src]
    try:
        out = client.qemu_guest_exec_wait(
            args.node,
            args.vmid,
            argv,
            timeout_seconds=args.timeout,
        )
    except ProxmoxError as exc:
        print(f"guest exec error: {exc}", file=sys.stderr)
        return 1

    if out.get("timeout"):
        print("guest exec: timeout (increase --timeout if docker build is slow)", file=sys.stderr)
        return 124

    data = out.get("out") or ""
    err = out.get("err") or ""
    if data:
        print(data)
    if err:
        print(err, file=sys.stderr)

    exitcode = out.get("exitcode")
    if exitcode not in (0, None):
        return int(exitcode) & 255 or 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
