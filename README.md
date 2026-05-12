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

- **`CURSOR_AGENT_GATEWAY_URL` が未設定**: **DM** → 短文の確認エコー。**サーバー** → @メンション／ボットへの返信で「返信テスト」エコーのみ。
- **`CURSOR_AGENT_GATEWAY_URL` を設定**（[`cursor-cli-homelab`](../cursor-cli-homelab) の `agent-gateway`、`POST /v1/prompt` と同じ）: 上記と同じトリガで、プロンプトをゲートウェイ経由で **`agent -p`** に渡し、**標準出力を Discord に返信**します（長文は自動で分割）。
  - `.env`: `CURSOR_AGENT_GATEWAY_URL`, `GATEWAY_TOKEN`（ゲートウェイでトークン必須のとき）、`CURSOR_GATEWAY_TRUST_WORKSPACE`, `CURSOR_GATEWAY_TIMEOUT_SEC`, 任意で `CURSOR_GATEWAY_PROMPT_PREFIX`。
  - ゲートウェイ側に **`CURSOR_API_KEY`** が必要です。CLI の MCP を確認なしで通したいときはゲートウェイの環境に **`AGENT_APPROVE_MCPS=true`**（[`--approve-mcps`](https://cursor.com/docs/cli/reference/parameters)）を設定。**Agent 既定**（`-p`、IDE の Ask モードではない）で動きますが、「Auto」と完全同一ではなくツール許可／サンドボックス次第です。
- **DM** と **サーバー（@またはボットへの返信）** の両方でゲートウェイ連携あり。

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

### Proxmox QEMU VM（ゲストエージェント経由）

Mac などから **Proxmox API + QEMU Guest Agent** で VM 内に clone・`.env` 同期・`docker compose up -d --build` まで一括できます（VM に Docker / git / agent が入っていること）。

1. Cursor の `~/.cursor/mcp.json` に `mcpServers.discord.env.DISCORD_BOT_TOKEN` を用意する（または環境変数 `DISCORD_BOT_TOKEN`）。
2. `proxmox-mcp` と同じ **`PROXMOX_*`** をシェルにエクスポートする。
3. リポジトリで実行:

```bash
cd projects/discord-mcp
python3 scripts/deploy_guest_exec.py --vmid 100
```

ゲストが **root のみ**（ubuntu ユーザーなし）の場合は既定で `/root/discord-mcp` に置きます。cloud-init で `ubuntu` がある場合は  
`--unix-user ubuntu --repo-dir /home/ubuntu/discord-mcp` を付けてください。初回 Docker ビルドが長いときは `--timeout 900` など。

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
