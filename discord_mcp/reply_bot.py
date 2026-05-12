"""Long-running Discord bot: DMs / @mentions → optional Cursor Agent via homelab gateway.

Uses ``DISCORD_BOT_TOKEN``. Requires **Message Content Intent** for guild text.

When ``CURSOR_AGENT_GATEWAY_URL`` is set, each eligible message is sent to
``POST {url}/v1/prompt`` (same contract as cursor-cli-homelab ``agent-gateway``)
and the agent stdout is posted back to Discord. Otherwise falls back to a short
echo (previous test behavior).

Gateway should run ``agent -p`` (full **agent** mode, not ``--mode ask``).
Set ``AGENT_APPROVE_MCPS=true`` on the gateway container for hands-free MCP
approval (closer to IDE "Auto").

Run::

    pip install -e ".[reply-bot]"
    DISCORD_BOT_TOKEN=... python -m discord_mcp.reply_bot
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, List, Optional
from urllib.parse import urljoin

import aiohttp
import discord


def _strip_mentions(content: str, user: discord.ClientUser) -> str:
    mention = user.mention
    return content.replace(mention, "").replace(f"<@!{user.id}>", "").strip()


def _chunks(text: str, limit: int = 1900) -> List[str]:
    if not text:
        return ["（出力なし）"]
    out: List[str] = []
    s = text
    while s:
        out.append(s[:limit])
        s = s[limit:]
    return out


def _gateway_url() -> str:
    return (os.getenv("CURSOR_AGENT_GATEWAY_URL") or "").strip().rstrip("/")


def _gateway_token() -> str:
    return (os.getenv("GATEWAY_TOKEN") or "").strip()


def _trust_workspace() -> bool:
    v = (os.getenv("CURSOR_GATEWAY_TRUST_WORKSPACE") or "true").strip().lower()
    return v in ("1", "true", "yes", "on")


def _gateway_timeout() -> aiohttp.ClientTimeout:
    try:
        total = float((os.getenv("CURSOR_GATEWAY_TIMEOUT_SEC") or "600").strip())
    except ValueError:
        total = 600.0
    return aiohttp.ClientTimeout(total=total)


def _prompt_prefix() -> str:
    return (os.getenv("CURSOR_GATEWAY_PROMPT_PREFIX") or "").strip()


async def _call_cursor_gateway(user_text: str) -> str:
    base = _gateway_url()
    if not base:
        return ""

    url = urljoin(base + "/", "v1/prompt")
    token = _gateway_token()
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    body_text = user_text
    prefix = _prompt_prefix()
    if prefix:
        body_text = f"{prefix}\n\n{user_text}"

    payload: dict[str, Any] = {
        "prompt": body_text,
        "trust_workspace": _trust_workspace(),
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                headers=headers,
                timeout=_gateway_timeout(),
            ) as resp:
                raw = await resp.text()
                if resp.status == 401:
                    return "ゲートウェイ認証エラー (401)。GATEWAY_TOKEN をボット側と揃えてください。"
                if resp.status == 503:
                    return "ゲートウェイが利用できません (503)。homelab の CURSOR_API_KEY / agent-gateway を確認してください。"
                if resp.status == 504:
                    return "Cursor エージェントがタイムアウトしました (504)。プロンプトを短くするかゲートウェイの AGENT_REQUEST_TIMEOUT_SEC を延長してください。"
                if resp.status >= 400:
                    detail = raw[:500]
                    try:
                        err = json.loads(raw)
                        detail = str(err.get("detail", raw))[:500]
                    except json.JSONDecodeError:
                        pass
                    return f"ゲートウェイエラー HTTP {resp.status}: {detail}"

                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    return f"ゲートウェイの応答が JSON ではありません: {raw[:300]}"

                exit_code = data.get("exit_code")
                out = (data.get("stdout") or "").strip()
                err = (data.get("stderr") or "").strip()
                parts: List[str] = []
                if out:
                    parts.append(out)
                if exit_code not in (0, None):
                    hint = err or "(stderr なし)"
                    parts.append(f"\n\n— exit {exit_code} —\n{hint[:1500]}")
                elif err:
                    parts.append(f"\n\n— stderr —\n{err[:1500]}")
                return "".join(parts).strip() or "（空の応答）"
    except aiohttp.ClientError as exc:
        return f"ゲートウェイに接続できません: {exc}"


async def _reply_in_chunks(
    channel: discord.abc.Messageable,
    text: str,
    *,
    reference: Optional[discord.Message] = None,
) -> None:
    first = True
    for part in _chunks(text, 1900):
        kwargs: dict[str, Any] = {"content": part[:2000]}
        if first and reference is not None:
            kwargs["reference"] = reference
            kwargs["mention_author"] = False
        await channel.send(**kwargs)
        first = False


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
        if _gateway_url():
            print(
                f"Cursor gateway: {_gateway_url()} (trust_workspace={_trust_workspace()})",
                flush=True,
            )
        else:
            print(
                "CURSOR_AGENT_GATEWAY_URL unset — echo fallback only.",
                flush=True,
            )

    @client.event
    async def on_message(message: discord.Message) -> None:
        if message.author.bot:
            return
        assert client.user

        use_cursor = bool(_gateway_url())

        # Direct message
        if isinstance(message.channel, discord.DMChannel):
            text = (message.content or "").strip() or "（本文なし）"
            if not message.content:
                text += "\n※ 添付のみの場合は本文が空になります。"
            if use_cursor:
                await message.channel.send("… Cursor で処理中（完了まで数分かかることがあります）")
                answer = await _call_cursor_gateway(text)
                await _reply_in_chunks(message.channel, answer, reference=message)
            else:
                await message.channel.send(f"受け取りました: {text[:1900]}")
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

        if use_cursor:
            reply_notice = await message.channel.send(
                "… Cursor で処理中（完了まで数分かかることがあります）",
                reference=message,
                mention_author=False,
            )
            answer = await _call_cursor_gateway(body)
            try:
                await reply_notice.delete()
            except discord.HTTPException:
                pass
            await _reply_in_chunks(message.channel, answer, reference=message)
            return

        await message.channel.send(f"返信テスト: {body[:1900]}")

    client.run(token)


if __name__ == "__main__":
    main()
