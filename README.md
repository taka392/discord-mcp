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

- **既定は OpenClaw のみ**です。`OPENCLAW_GATEWAY_URL` と `OPENCLAW_GATEWAY_TOKEN`（または `OPENCLAW_GATEWAY_PASSWORD`）を `discord-reply-bot` に渡すと、[OpenClaw Gateway](https://docs.openclaw.ai/gateway/openai-http-api) の **`POST /v1/chat/completions`** にユーザ文を送り、**アシスタント本文を Discord に返信**します。**Cursor ゲートウェイには送りません**（`.env` に `CURSOR_AGENT_GATEWAY_URL` が残っていても無視されます）。
  - Gateway で **`gateway.http.endpoints.chatCompletions.enabled`** を有効にしてください（無効だと HTTP 404 などになります）。
  - 主な環境変数: `OPENCLAW_GATEWAY_URL`, `OPENCLAW_GATEWAY_TOKEN`, 任意で `OPENCLAW_CHAT_MODEL`（既定 `openclaw/default`）、`OPENCLAW_SESSION_USER`（未設定時は `discord:<Discord ユーザー ID>`）、`OPENCLAW_MESSAGE_CHANNEL`（既定 `discord`）、`OPENCLAW_SESSION_KEY`, `OPENCLAW_MODEL_HEADER`, `OPENCLAW_PROMPT_PREFIX`, `OPENCLAW_GATEWAY_TIMEOUT_SEC`。
  - Cursor の `mcp.json` の `openclaw` と**同じ URL／トークン**を reply-bot の環境に渡せばよいです（別プロセスのため自動同期はしません）。
  - OpenClaw が未設定のときは、DM／メンションでも **設定不足の説明**が返ります（旧来の短文エコーはしません）。

- **Cursor の HTTP ゲートウェイだけ使う**場合（[`cursor-cli-homelab`](../cursor-cli-homelab) を**別ホスト／別 compose**で動かしているとき）: `.env` に **`DISCORD_LLM_BACKEND=cursor`** と、到達可能な **`CURSOR_AGENT_GATEWAY_URL`**（例: `http://192.168.x.x:9888`）を書いてください。**POST /v1/prompt`** で `agent -p` の標準出力を返します。
  - ゲートウェイ側に **`CURSOR_API_KEY`**、任意で **`AGENT_APPROVE_MCPS=true`** など。リポジトリ付属の `docker compose` には **agent-gateway は含みません**（`agent_gateway/` は手動同期用の参照実装のまま残しています）。

- **DM** と **サーバー（@またはボットへの返信）** の両方で上記のいずれかが使われます。

Discord の本文に含まれる **`<@…>` 形式のメンション**は、LLM に渡す前にプレースホルダへ置き換えます（モデルが「ユーザーIDは解決できない」と返すのを防ぐため）。

### Docker（Proxmox 上の VM / LXC など）

`docker compose` は **`discord-reply-bot` の 1 サービスのみ**です（**bundled の `agent-gateway` は含みません**。OpenClaw は別 VM／Tailscale 等で動かしている前提です）。

- **必須**: `.env` に **`DISCORD_BOT_TOKEN`** と **`OPENCLAW_GATEWAY_URL` / `OPENCLAW_GATEWAY_TOKEN`**（または `PASSWORD`）。
- **Cursor 経路**に切り替えるときだけ `.env` に **`DISCORD_LLM_BACKEND=cursor`** と、**別途動いている** `CURSOR_AGENT_GATEWAY_URL` を書いてください。
- **`DISCORD_BOT_TOKEN`・`OPENCLAW_GATEWAY_TOKEN` は Git に載せない**こと。

ゲスト側の手順例:

```bash
git clone https://github.com/taka392/discord-mcp.git
cd discord-mcp
./scripts/homelab_docker_up.sh
# 初回は .env が無いので .env.example がコピーされる → DISCORD_BOT_TOKEN と OPENCLAW_* を編集して再度
```

手動でも同じです。

```bash
cp .env.example .env
# edit .env （必須: DISCORD_BOT_TOKEN, OPENCLAW_GATEWAY_URL, OPENCLAW_GATEWAY_TOKEN）
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

Discord から **「ゲートウェイが利用できません (503)」** と出るのは、**`DISCORD_LLM_BACKEND=cursor`** で Cursor 経路を使っているときに、コンテナ内で **`CURSOR_API_KEY` が空**なことが多いです（[Headless CLI](https://cursor.com/docs/cli/headless)）。

**OpenClaw 既定**のときは、Gateway の **chat completions** や **認証トークン**を確認してください。

Mac から Proxmox で VM100 に OpenClaw 用 `.env` を流し込む例::

```bash
export PROXMOX_BASE_URL=... PROXMOX_TOKEN_ID=... PROXMOX_TOKEN_SECRET=... PROXMOX_VERIFY_TLS=false
python3 scripts/push_gateway_env_guest_exec.py --vmid 100
```

（`~/.cursor/mcp.json` の **discord** と **openclaw** を読みます。）

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
