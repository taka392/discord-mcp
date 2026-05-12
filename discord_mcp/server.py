"""Discord REST API MCP server (FastMCP)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP

from .client import DiscordClient, DiscordError

mcp = FastMCP("discord")


def _client() -> DiscordClient:
    try:
        return DiscordClient()
    except DiscordError as exc:
        raise RuntimeError(str(exc)) from exc


@mcp.tool()
def verify() -> Dict[str, Any]:
    """Verify the bot token by calling GET /users/@me.

    Returns the bot user object (id, username, discriminator flags, etc.).
    """
    return _client().verify()


@mcp.tool()
def list_guilds(limit: int = 200, before: Optional[str] = None) -> List[Dict[str, Any]]:
    """List guilds the bot is in (GET /users/@me/guilds).

    Args:
        limit: Max guilds per request (1–200).
        before: Optional guild id cursor for pagination.
    """
    return _client().list_guilds(limit=limit, before=before)


@mcp.tool()
def get_guild(guild_id: str) -> Dict[str, Any]:
    """Get a guild by id. The bot must be a member of that guild."""
    return _client().get_guild(guild_id)


@mcp.tool()
def list_guild_channels(guild_id: str) -> List[Dict[str, Any]]:
    """List channels in a guild (text, voice, categories, etc.)."""
    return _client().list_guild_channels(guild_id)


@mcp.tool()
def get_channel(channel_id: str) -> Dict[str, Any]:
    """Get a single channel object by id."""
    return _client().get_channel(channel_id)


@mcp.tool()
def list_channel_messages(
    channel_id: str,
    limit: int = 50,
    before: Optional[str] = None,
    after: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List recent messages in a channel (newest first in the response).

    Requires **Read Message History** and access to the channel. ``limit`` is
    1–100. Use ``before`` / ``after`` message ids for pagination.
    """
    return _client().list_channel_messages(
        channel_id, limit=limit, before=before, after=after
    )


@mcp.tool()
def create_channel_message(channel_id: str, content: str) -> Dict[str, Any]:
    """Send a text message to a channel.

    Requires **Send Messages**. Respect server rules and rate limits; content
    is limited to 2000 characters for plain text.
    """
    return _client().send_channel_message(channel_id, content)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
