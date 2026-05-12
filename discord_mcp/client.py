"""Discord REST API client (Bot token, API v10)."""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import requests

API_BASE = "https://discord.com/api/v10"


class DiscordError(RuntimeError):
    """Raised when the Discord API returns an error or invalid response."""


class DiscordClient:
    """Discord REST API v10 with a bot token.

    Set ``DISCORD_BOT_TOKEN`` in the MCP client's ``env`` block (or pass
    ``bot_token``). The value must be the raw token from the Developer Portal;
    the client sends ``Authorization: Bot <token>``.
    """

    def __init__(self, bot_token: Optional[str] = None) -> None:
        raw = (bot_token or os.getenv("DISCORD_BOT_TOKEN", "")).strip()
        if not raw:
            raise DiscordError(
                "DISCORD_BOT_TOKEN is not set. Pass it via the MCP client's env block."
            )
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bot {raw}",
                "User-Agent": "discord-mcp/0.1.0 (https://github.com/taka392/discord-mcp)",
            }
        )

    def _parse_json(self, resp: requests.Response) -> Any:
        if not resp.content:
            return None
        try:
            return resp.json()
        except ValueError as exc:
            raise DiscordError(
                f"Non-JSON response ({resp.status_code}): {resp.text[:800]}"
            ) from exc

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
    ) -> Any:
        url = f"{API_BASE}{path}"
        try:
            resp = self._session.request(
                method,
                url,
                params=params,
                json=json_body,
                timeout=30,
            )
        except requests.RequestException as exc:
            raise DiscordError(f"Network error calling {url}: {exc}") from exc

        data = self._parse_json(resp)
        if resp.status_code >= 400:
            if isinstance(data, dict):
                msg = data.get("message", resp.text[:800])
                code = data.get("code")
                extra = f" (code {code})" if code is not None else ""
                raise DiscordError(f"HTTP {resp.status_code}{extra}: {msg}")
            raise DiscordError(f"HTTP {resp.status_code}: {resp.text[:800]}")
        return data

    def verify(self) -> Dict[str, Any]:
        """GET /users/@me — current bot user."""
        out = self._request("GET", "/users/@me")
        if not isinstance(out, dict):
            raise DiscordError("Expected object from /users/@me")
        return out

    def list_guilds(self, limit: int = 200, before: Optional[str] = None) -> List[Dict[str, Any]]:
        """GET /users/@me/guilds — guilds the bot is a member of."""
        lim = max(1, min(200, limit))
        params: Dict[str, Any] = {"limit": lim}
        if before:
            params["before"] = before
        out = self._request("GET", "/users/@me/guilds", params=params)
        if not isinstance(out, list):
            raise DiscordError("Expected array from /users/@me/guilds")
        return out

    def get_guild(self, guild_id: str) -> Dict[str, Any]:
        """GET /guilds/{guild.id} — guild object (bot must be in the guild)."""
        out = self._request("GET", f"/guilds/{guild_id}")
        if not isinstance(out, dict):
            raise DiscordError("Expected object from /guilds/{id}")
        return out

    def list_guild_channels(self, guild_id: str) -> List[Dict[str, Any]]:
        """GET /guilds/{guild.id}/channels — channels in a guild."""
        out = self._request("GET", f"/guilds/{guild_id}/channels")
        if not isinstance(out, list):
            raise DiscordError("Expected array from /guilds/{id}/channels")
        return out

    def get_channel(self, channel_id: str) -> Dict[str, Any]:
        """GET /channels/{channel.id} — channel object."""
        out = self._request("GET", f"/channels/{channel_id}")
        if not isinstance(out, dict):
            raise DiscordError("Expected object from /channels/{id}")
        return out

    def list_channel_messages(
        self,
        channel_id: str,
        limit: int = 50,
        before: Optional[str] = None,
        after: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """GET /channels/{channel.id}/messages — recent messages.

        Requires channel permission **Read Message History** (and bot access to
        the channel). ``limit`` is clamped to 1–100.
        """
        lim = max(1, min(100, limit))
        params: Dict[str, Any] = {"limit": lim}
        if before:
            params["before"] = before
        if after:
            params["after"] = after
        out = self._request(
            "GET", f"/channels/{channel_id}/messages", params=params
        )
        if not isinstance(out, list):
            raise DiscordError("Expected array from /channels/{id}/messages")
        return out

    def send_channel_message(
        self,
        channel_id: str,
        content: str,
    ) -> Dict[str, Any]:
        """POST /channels/{channel.id}/messages — send a text message.

        Requires **Send Messages** in the channel. Keep ``content`` within
        Discord's length limits (2000 characters for plain text).
        """
        body = {"content": content}
        out = self._request(
            "POST", f"/channels/{channel_id}/messages", json_body=body
        )
        if not isinstance(out, dict):
            raise DiscordError("Expected object from POST messages")
        return out
