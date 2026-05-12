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
