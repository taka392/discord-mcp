# discord-mcp

[MCP](https://modelcontextprotocol.io/) server that wraps a subset of the [Discord REST API v10](https://discord.com/developers/docs/reference) using a **bot token**.

## Security

- Never commit the bot token. Pass `DISCORD_BOT_TOKEN` only via your MCP client `env` block (see `examples/`).
- If a token was pasted into chat or committed anywhere, **reset it** in the Discord Developer Portal and use the new token locally.

## Tools

| Tool | Description |
|------|-------------|
| `verify` | `GET /users/@me` |
| `list_guilds` | `GET /users/@me/guilds` |
| `get_guild` | `GET /guilds/{id}` |
| `list_guild_channels` | `GET /guilds/{id}/channels` |
| `get_channel` | `GET /channels/{id}` |
| `list_channel_messages` | `GET /channels/{id}/messages` |
| `create_channel_message` | `POST /channels/{id}/messages` |

Gateway intents (Presence, Server Members, Message Content) apply to the **Gateway** websocket. This MCP uses **HTTP** only; channel permissions still apply (e.g. Read Message History, Send Messages).

## Reply bot (auto-replies on Discord)

The MCP alone cannot listen for messages. For **DMs and @mentions** (and replies to the bot when Discord fills the reference), run the optional Gateway bot:

1. In the [Developer Portal](https://discord.com/developers/applications) → your app → **Bot**, enable **Message Content Intent** (Privileged Gateway Intents).
2. Install extras and start the process (keep this terminal open, or run under `tmux` / a process manager):

```bash
cd projects/discord-mcp
source .venv/bin/activate
pip install -e ".[reply-bot]"
export DISCORD_BOT_TOKEN='…'   # same token as MCP
python -m discord_mcp.reply_bot
# or: discord-reply-bot
```

`uvx` のデフォルトでは `reply-bot` 用の `discord.py` は入りません。リポジトリを clone しない場合は例えば次でも可です。

```bash
pip install "discord-mcp[reply-bot] @ git+https://github.com/taka392/discord-mcp.git"
DISCORD_BOT_TOKEN='…' discord-reply-bot
```

Behavior:

- **DM** to the bot → bot echoes an acknowledgment.
- **Server channel** → bot responds only if **@メンション** or **返信がボットのメッセージ宛**（取得できる場合のみ）。

### Docker（Proxmox 上の VM / LXC など）

返信ボットだけをコンテナで常駐させる。MCP（Cursor）は別マシンでも同じトークンで動かせる。**Docker デーモンは homelab 上のその Linux だけで動き**、外向きに Discord Gateway へ接続します（こちらからあなたの Proxmox へリモートデプロイはできません。ゲストで次を実行してください）。

1. Proxmox で Docker 入りの **VM または LXC**（公式推奨は VM）を用意する。
2. ゲストでリポジトリを取得し、スクリプトで起動する。

```bash
git clone https://github.com/taka392/discord-mcp.git
cd discord-mcp
./scripts/homelab_docker_up.sh
# 初回は .env が無いので .env.example がコピーされる → DISCORD_BOT_TOKEN を編集して再度 ./scripts/homelab_docker_up.sh
```

手動でも同じです。トークンは `.env` のみ（**コミットしない**）。

```bash
cp .env.example .env
# edit .env → DISCORD_BOT_TOKEN=...
docker compose up -d --build
docker compose logs -f
```

停止・更新:

```bash
docker compose down
docker compose up -d --build
```

`restart: unless-stopped` なのでゲスト再起動後もコンテナが戻る（Docker が起動時に有効な前提）。

### Mac などから homelab へ SSH でデプロイ

`scripts/deploy_remote.sh` は次まで一気に実行します: **リモートで `git pull` → ローカルの Cursor `mcp.json` からトークンを読む → `scp` でリモートの `.env` を上書き → `homelab_docker_up.sh`（Docker）**。

- デフォルトで **`~/.cursor/mcp.json`** の `mcpServers.discord.env.DISCORD_BOT_TOKEN` を使う。
- 別ファイルなら `export MCP_JSON_PATH='/path/to/mcp.json'`。
- `mcp.json` を使わず一時的に上書きしたいだけなら `export DISCORD_BOT_TOKEN='…'`（その場合は mcp.json は読まない）。

```bash
cd /path/to/discord-mcp   # clone 済みのどこでも可
export HOMELAB_SSH='you@192.168.x.x'          # 必須
# optional: export HOMELAB_REPO_DIR='/srv/discord-mcp'
# optional: export HOMELAB_SSH_OPTS='-i ~/.ssh/id_ed25519'
# optional: export MCP_JSON_PATH="$HOME/.cursor/mcp.json"
./scripts/deploy_remote.sh
```

**注意:** デプロイのたびにリモートの `.env` はローカル設定と同期される（トークンを homelab だけで管理したい場合はサーバー上で `homelab_docker_up.sh` だけ使う）。

## Local check

```bash
cd projects/discord-mcp
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
DISCORD_BOT_TOKEN='your token' python -m discord_mcp.check
```

## Cursor registration

After publishing to GitHub, merge the snippet from `examples/cursor_mcp_config.example.json` into `~/.cursor/mcp.json` and reload Cursor.

## License

MIT
