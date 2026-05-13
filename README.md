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
  - 主な環境変数: `OPENCLAW_GATEWAY_URL`, `OPENCLAW_GATEWAY_TOKEN`, 任意で `OPENCLAW_CHAT_MODEL`（未指定時は **`google/gemini-3.1-pro-preview`**）、`OPENCLAW_SESSION_USER`（未設定時は `discord:<Discord ユーザー ID>`）、`OPENCLAW_MESSAGE_CHANNEL`（既定 `discord`）、`OPENCLAW_SESSION_KEY`, `OPENCLAW_MODEL_HEADER`, `OPENCLAW_PROMPT_PREFIX`, `OPENCLAW_GATEWAY_TIMEOUT_SEC`。Gemini を使うには Gateway 側に [Google プロバイダの認証](https://docs.openclaw.ai/providers/google)（`GEMINI_API_KEY` 等）が必要です。
  - Cursor の `mcp.json` の `openclaw` の **`OPENCLAW_GATEWAY_TOKEN`（または PASSWORD）**を reply-bot の `.env` に**同じ値で**渡してください。**URL は OpenClaw と同じホストなら `http://127.0.0.1:<gateway-port>`**（Mac の MCP が使う Tailscale URL と同じである必要はありません）。
  - OpenClaw が未設定のときは、DM／メンションでも **設定不足の説明**が返ります（旧来の短文エコーはしません）。

- **Cursor の HTTP ゲートウェイだけ使う**場合（[`cursor-cli-homelab`](../cursor-cli-homelab) を**別ホスト／別 compose**で動かしているとき）: `.env` に **`DISCORD_LLM_BACKEND=cursor`** と、到達可能な **`CURSOR_AGENT_GATEWAY_URL`**（例: `http://192.168.x.x:9888`）を書いてください。**POST /v1/prompt`** で `agent -p` の標準出力を返します。
  - ゲートウェイ側に **`CURSOR_API_KEY`**、任意で **`AGENT_APPROVE_MCPS=true`** など。リポジトリ付属の `docker compose` には **agent-gateway は含みません**（`agent_gateway/` は手動同期用の参照実装のまま残しています）。

- **DM** と **サーバー（@またはボットへの返信）** の両方で上記のいずれかが使われます。

Discord の本文に含まれる **`<@…>` 形式のメンション**は、LLM に渡す前にプレースホルダへ置き換えます（モデルが「ユーザーIDは解決できない」と返すのを防ぐため）。

### Docker（推奨: **OpenClaw Gateway と同一 VM**）

`docker compose` は **`discord-reply-bot` の 1 サービスのみ**です。OpenClaw Gateway 本体は **含みません**（ホスト上の `openclaw gateway` / systemd と同居させます）。

- **`network_mode: host`** のため、`.env` の **`OPENCLAW_GATEWAY_URL` は `http://127.0.0.1:<port>`**（例: `http://127.0.0.1:18789`）。ポートはその VM で Gateway が待ち受けているものに合わせる。
- **Mac で `docker compose up` だけ**だとコンテナは立ちません（**profile `prod`**）。誤実行でリソースを食わないため。
- **本番 VM**では `.env` の **`COMPOSE_PROFILES=prod`**（`.env.example` に同梱）か、`./scripts/homelab_docker_up.sh`。
- **ローカル試験のみ**: `COMPOSE_PROFILES=prod docker compose up -d --build`（Linux が前提。Docker Desktop の挙動は環境による）。

- **必須**: `.env` に **`DISCORD_BOT_TOKEN`** と **`OPENCLAW_GATEWAY_URL`（ループバック）** / **`OPENCLAW_GATEWAY_TOKEN`**（または `PASSWORD`）。
- **Cursor 経路**に切り替えるときだけ `.env` に **`DISCORD_LLM_BACKEND=cursor`** と、到達可能な `CURSOR_AGENT_GATEWAY_URL`。
- **`DISCORD_BOT_TOKEN`・`OPENCLAW_GATEWAY_TOKEN` は Git に載せない**こと。

**旧構成（別 VM に Discord ボットだけ置く）をやめた場合:** もう使わない VM 上で `docker compose down` のうえ、コンテナ／compose を削除してください。Tailscale 越し URL は不要になるため、`.env` の `OPENCLAW_GATEWAY_URL` はループバックに統一します。

ゲスト（OpenClaw VM）での手順例:

```bash
git clone https://github.com/taka392/discord-mcp.git
cd discord-mcp
./scripts/homelab_docker_up.sh
# 初回は .env が無いので .env.example がコピーされる → DISCORD_BOT_TOKEN と OPENCLAW_* を編集して再度
```

手動でも同じです。

```bash
cp .env.example .env
# DISCORD_BOT_TOKEN, OPENCLAW_GATEWAY_URL=http://127.0.0.1:18789, OPENCLAW_GATEWAY_TOKEN
COMPOSE_PROFILES=prod docker compose up -d --build
docker compose logs -f
```

停止・更新:

```bash
COMPOSE_PROFILES=prod docker compose down
COMPOSE_PROFILES=prod docker compose up -d --build
```

`restart: unless-stopped` なのでゲスト再起動後もコンテナが戻る（Docker が起動時に有効な前提）。

### Proxmox QEMU VM（ゲストエージェント）

**OpenClaw Gateway を動かしている QEMU VM**（Discord 専用 VM など **別 vmid ではない**）に `discord-mcp` を clone し、Mac から `.env` を流し込んで `docker compose` まで実行します。

1. `~/.cursor/mcp.json` に `mcpServers.discord.env.DISCORD_BOT_TOKEN` と `openclaw` のトークン（またはパスワード）を用意する。
2. `proxmox-mcp` と同じ **`PROXMOX_*`** をシェルにエクスポートする。
3. **`--vmid`** には **その OpenClaw ホストの vmid** を渡す。毎回省略したい場合は `export OPENCLAW_QEMU_VMID=<vmid>`。
4. **Gateway ポートが 18789 でない**ときは `OPENCLAW_GATEWAY_LOCAL_URL` または `--local-gateway-url` を指定。

```bash
cd projects/discord-mcp
export PROXMOX_BASE_URL=... PROXMOX_TOKEN_ID=... PROXMOX_TOKEN_SECRET=... PROXMOX_VERIFY_TLS=false
export OPENCLAW_QEMU_VMID=101   # OpenClaw が乗っている VM（例。100 とは限らない）
python3 scripts/push_gateway_env_guest_exec.py --vmid 101
# 例: python3 scripts/push_gateway_env_guest_exec.py --vmid 101 --repo-dir /root/discord-mcp --local-gateway-url http://127.0.0.1:18789
```

### Mac から OpenClaw VM へ SSH でデプロイ

`scripts/deploy_remote.sh` は **リモートで `git pull` → `scp` で `.env` → `homelab_docker_up.sh`** まで行います。生成する **`OPENCLAW_GATEWAY_URL` はデフォルトで `http://127.0.0.1:18789`**（`OPENCLAW_GATEWAY_LOCAL_URL` で変更可）。**Gateway が別ホストのとき**は `export DISCORD_USE_MCP_GATEWAY_URL=1` とすると **mcp.json の `OPENCLAW_GATEWAY_URL`** を書き込みます。

```bash
cd /path/to/discord-mcp
export HOMELAB_SSH='root@<OpenClaw-VM の IP or tailscale>'
# optional: export OPENCLAW_GATEWAY_LOCAL_URL='http://127.0.0.1:18789'
# optional: export DISCORD_USE_MCP_GATEWAY_URL=1   # Gateway が別マシン（MCP の URL を .env に）
# optional: export HOMELAB_REPO_DIR='/root/discord-mcp'
./scripts/deploy_remote.sh
```

**注意:** `DISCORD_BOT_TOKEN` だけ `export` したモードでは、リモート `.env` にトークンとループバック URLだけ入り **`OPENCLAW_GATEWAY_TOKEN` は手で追記**してください。

Discord から **「ゲートウェイが利用できません (503)」** は **`DISCORD_LLM_BACKEND=cursor`** かつ **`CURSOR_API_KEY` 未設定**なときに出やすいです（Cursor 経路）。

**OpenClaw 既定**では、同一 VM 上で Gateway が待ち受けているか（`ss -tlnp` 等）、`OPENCLAW_GATEWAY_URL` / トークン、Gateway の **chat completions** 有効化を確認してください。

**`127.0.0.1:18789` に接続できない** と出るのは、その VM で **そのポートに Gateway が居ない**ときです。OpenClaw が別サーバなら `.env` をループバックにしてはいけません。`push_gateway_env_guest_exec.py --use-mcp-gateway-url` または `DISCORD_USE_MCP_GATEWAY_URL=1 ./scripts/deploy_remote.sh` で **MCP に書いてある Gateway URL** に戻せます。本当に同居させるなら、その VM で OpenClaw を起動し、`.env` のポートを **`ss`** で合わせてください。

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
