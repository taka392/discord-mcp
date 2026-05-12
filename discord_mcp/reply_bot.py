"""Long-running Discord bot: replies to DMs and @mentions (Gateway).

Uses the same ``DISCORD_BOT_TOKEN`` as the MCP. Requires **Message Content
Intent** enabled in the Developer Portal for guild text (not only DMs).

Run::

    pip install -e ".[reply-bot]"
    DISCORD_BOT_TOKEN=... python -m discord_mcp.reply_bot
"""
from __future__ import annotations

import os
import sys

import discord


def _strip_mentions(content: str, user: discord.ClientUser) -> str:
    mention = user.mention
    return content.replace(mention, "").replace(f"<@!{user.id}>", "").strip()


def main() -> None:
    token = (os.getenv("DISCORD_BOT_TOKEN") or "").strip()
    if not token:
        print(
            "DISCORD_BOT_TOKEN is not set. Export it or use the same env as MCP.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    intents = discord.Intents.default()
    intents.dm_messages = True
    intents.message_content = True  # Portal: Bot → Message Content Intent ON

    client = discord.Client(intents=intents)

    @client.event
    async def on_ready() -> None:
        assert client.user
        print(f"Logged in as {client.user} (id={client.user.id})", flush=True)

    @client.event
    async def on_message(message: discord.Message) -> None:
        if message.author.bot:
            return
        assert client.user

        # Direct message: always reply
        if isinstance(message.channel, discord.DMChannel):
            text = (message.content or "").strip() or "（本文なし）"
            await message.channel.send(
                f"受け取りました: {text[:1900]}"
                + ("\n※ 添付のみの場合は本文が空になります。" if not message.content else "")
            )
            return

        # Guild: @bot mention or reply to bot's message
        mentioned = client.user in message.mentions
        replying_to_bot = False
        if message.reference:
            ref_msg = message.reference.resolved or message.reference.cached_message
            if (
                isinstance(ref_msg, discord.Message)
                and ref_msg.author.id == client.user.id
            ):
                replying_to_bot = True

        if not (mentioned or replying_to_bot):
            return

        body = _strip_mentions(message.content or "", client.user) or "（メンションのみ）"
        await message.channel.send(f"返信テスト: {body[:1900]}")

    client.run(token)


if __name__ == "__main__":
    main()
