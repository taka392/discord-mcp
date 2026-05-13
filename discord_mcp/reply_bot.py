"""Long-running Discord bot: DMs / @mentions → **OpenClaw** (default).

Uses ``DISCORD_BOT_TOKEN``. Requires **Message Content Intent** for guild text.

**Default:** only **OpenClaw** ``POST {OPENCLAW_GATEWAY_URL}/v1/chat/completions``.
There is **no fallback** to Cursor unless you explicitly set
``DISCORD_LLM_BACKEND=cursor`` (legacy / bundled compose).

Env **``DISCORD_LLM_BACKEND``** (optional): ``openclaw`` (default if unset or unknown),
or ``cursor`` for Cursor homelab ``POST …/v1/prompt`` only.

OpenClaw requires ``gateway.http.endpoints.chatCompletions.enabled`` on the gateway.
See https://docs.openclaw.ai/gateway/openai-http-api

Cursor path (only when ``DISCORD_LLM_BACKEND=cursor``): gateway should run ``agent -p``.
Set ``AGENT_APPROVE_MCPS=true`` on the gateway container for hands-free MCP approval.

Run::

    pip install -e ".[reply-bot]"
    DISCORD_BOT_TOKEN=... python -m discord_mcp.reply_bot
"""
from __future__ import annotations

import json
import os
import re
import sys
from typing import Any, List, Optional
from urllib.parse import urljoin

import aiohttp
import discord


def _strip_mentions(content: str, user: discord.ClientUser) -> str:
    mention = user.mention
    return content.replace(mention, "").replace(f"<@!{user.id}>", "").strip()


def _mask_discord_markup_for_llm(text: str) -> str:
    """Replace Discord mention / channel / role markup so upstream LLMs do not treat
    ``<@snowflake>`` as a request to resolve a person outside Discord (refusal spam).
    Snowflake digits are omitted from the placeholder text on purpose.
    """
    s = text
    s = re.sub(r"<@!?\d+>", "（他ユーザーへのDiscordメンション）", s)
    s = re.sub(r"<#\d+>", "（Discordチャンネルへのリンク）", s)
    s = re.sub(r"<@&\d+>", "（Discordロールへのメンション）", s)
    s = re.sub(r"<a?:\w+:\d+>", "（Discord絵文字）", s)
    return s


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


def _openclaw_base_url() -> str:
    return (os.getenv("OPENCLAW_GATEWAY_URL") or "").strip().rstrip("/")


def _openclaw_auth_headers() -> dict[str, str]:
    token = (os.getenv("OPENCLAW_GATEWAY_TOKEN") or "").strip()
    password = (os.getenv("OPENCLAW_GATEWAY_PASSWORD") or "").strip()
    if token:
        return {"Authorization": f"Bearer {token}"}
    if password:
        return {"Authorization": f"Bearer {password}"}
    return {}


def _openclaw_configured() -> bool:
    return bool(_openclaw_base_url() and _openclaw_auth_headers())


def _openclaw_chat_model() -> str:
    return (os.getenv("OPENCLAW_CHAT_MODEL") or "openclaw/default").strip()


def _openclaw_message_channel() -> str:
    return (os.getenv("OPENCLAW_MESSAGE_CHANNEL") or "discord").strip()


def _openclaw_prompt_prefix() -> str:
    return (os.getenv("OPENCLAW_PROMPT_PREFIX") or "").strip()


def _openclaw_timeout() -> aiohttp.ClientTimeout:
    try:
        total = float((os.getenv("OPENCLAW_GATEWAY_TIMEOUT_SEC") or "600").strip())
    except ValueError:
        total = 600.0
    return aiohttp.ClientTimeout(total=total)


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


def _text_from_chat_completion_json(data: Any) -> str:
    if not isinstance(data, dict):
        return f"OpenClaw の応答形式が不正です: {data!r}"[:500]

    if data.get("ok") is False:
        err = data.get("error") or {}
        msg = err.get("message") if isinstance(err, dict) else str(err)
        return f"OpenClaw: {msg}"[:1500]

    err_top = data.get("error")
    if isinstance(err_top, dict):
        msg = err_top.get("message") or str(err_top)
        return f"OpenClaw エラー: {msg}"[:1500]

    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return (
            "OpenClaw: 応答に choices がありません。"
            f" {json.dumps(data, ensure_ascii=False)[:500]}"
        )

    c0 = choices[0]
    if not isinstance(c0, dict):
        return "OpenClaw: choices[0] が不正です。"

    msg = c0.get("message")
    if isinstance(msg, dict):
        content = msg.get("content")
        if isinstance(content, str):
            return content.strip() or "（空の応答）"
        if isinstance(content, list):
            parts: List[str] = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    parts.append(str(part.get("text", "")))
                elif isinstance(part, str):
                    parts.append(part)
            joined = "".join(parts).strip()
            return joined or "（空の応答）"

    delta = c0.get("delta")
    if isinstance(delta, dict) and isinstance(delta.get("content"), str):
        return (delta["content"] or "").strip() or "（空の応答）"

    return (
        "OpenClaw: アシスタント本文を解析できません。"
        f" {json.dumps(c0, ensure_ascii=False)[:800]}"
    )


async def _call_openclaw_chat(user_text: str, *, discord_user_id: int) -> str:
    if not _openclaw_configured():
        return ""

    base = _openclaw_base_url()
    url = urljoin(base + "/", "v1/chat/completions")
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        **_openclaw_auth_headers(),
    }
    ch = _openclaw_message_channel()
    if ch:
        headers["x-openclaw-message-channel"] = ch
    sk = (os.getenv("OPENCLAW_SESSION_KEY") or "").strip()
    if sk:
        headers["x-openclaw-session-key"] = sk
    om = (os.getenv("OPENCLAW_MODEL_HEADER") or "").strip()
    if om:
        headers["x-openclaw-model"] = om

    body_text = user_text
    prefix = _openclaw_prompt_prefix()
    if prefix:
        body_text = f"{prefix}\n\n{user_text}"

    body: dict[str, Any] = {
        "model": _openclaw_chat_model(),
        "messages": [{"role": "user", "content": body_text}],
        "stream": False,
        "user": (os.getenv("OPENCLAW_SESSION_USER") or f"discord:{discord_user_id}").strip(),
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=body,
                headers=headers,
                timeout=_openclaw_timeout(),
            ) as resp:
                raw = await resp.text()
                if resp.status == 401:
                    return (
                        "OpenClaw 認証エラー (401)。"
                        "OPENCLAW_GATEWAY_TOKEN（または PASSWORD）を Gateway と揃えてください。"
                    )
                if resp.status == 404:
                    return (
                        "OpenClaw が HTTP 404 を返しました。"
                        "chat completions が無効か URL が違う可能性があります。"
                        "Gateway で gateway.http.endpoints.chatCompletions.enabled を true にし、"
                        "OPENCLAW_GATEWAY_URL が Gateway のベース URL か確認してください。"
                    )
                if resp.status >= 400:
                    detail = raw[:600]
                    try:
                        err = json.loads(raw)
                        if isinstance(err, dict):
                            e = err.get("error")
                            if isinstance(e, dict):
                                detail = str(e.get("message", detail))
                            elif isinstance(e, str):
                                detail = e
                    except json.JSONDecodeError:
                        pass
                    return f"OpenClaw エラー HTTP {resp.status}: {detail}"

                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    return f"OpenClaw の応答が JSON ではありません: {raw[:300]}"

                return _text_from_chat_completion_json(data)
    except aiohttp.ClientError as exc:
        return f"OpenClaw に接続できません: {exc}"


def _llm_backend_mode() -> str:
    """openclaw (default) | cursor (opt-in legacy)."""
    raw = (
        os.getenv("DISCORD_LLM_BACKEND") or os.getenv("DISCORD_REPLY_BACKEND") or "openclaw"
    ).strip().lower()
    if raw in ("cursor", "homelab", "agent-gateway", "agent_gateway"):
        return "cursor"
    return "openclaw"


async def _call_llm_backend(user_text: str, *, discord_user_id: int) -> str:
    if _llm_backend_mode() == "cursor":
        if not _gateway_url():
            return (
                "【設定不足】DISCORD_LLM_BACKEND=cursor ですが "
                "CURSOR_AGENT_GATEWAY_URL が未設定です。"
            )
        return await _call_cursor_gateway(user_text)
    if not _openclaw_configured():
        return (
            "【設定不足】このボットは **OpenClaw のみ**を使います（Cursor には送りません）。"
            "OPENCLAW_GATEWAY_URL と OPENCLAW_GATEWAY_TOKEN（または OPENCLAW_GATEWAY_PASSWORD）を "
            "discord-reply-bot の環境に設定してください。"
            " 旧来の Cursor ゲートウェイだけ使う場合は DISCORD_LLM_BACKEND=cursor を設定してください。"
        )
    return await _call_openclaw_chat(user_text, discord_user_id=discord_user_id)


def _busy_wait_message() -> str:
    if _llm_backend_mode() == "cursor":
        return "… Cursor で処理中（完了まで数分かかることがあります）"
    return "… OpenClaw で処理中（完了まで数分かかることがあります）"


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
        mode = _llm_backend_mode()
        print(f"DISCORD_LLM_BACKEND={mode!r}", flush=True)
        if mode == "cursor":
            if _gateway_url():
                print(
                    f"Cursor legacy: {_gateway_url()} (trust_workspace={_trust_workspace()})",
                    flush=True,
                )
            else:
                print(
                    "DISCORD_LLM_BACKEND=cursor but CURSOR_AGENT_GATEWAY_URL missing.",
                    flush=True,
                )
        else:
            if _openclaw_configured():
                print(
                    f"OpenClaw: {_openclaw_base_url()} (model={_openclaw_chat_model()}, "
                    f"channel={_openclaw_message_channel()!r})",
                    flush=True,
                )
            else:
                print(
                    "OpenClaw URL+auth missing — replies will be a config error until fixed.",
                    flush=True,
                )

    @client.event
    async def on_message(message: discord.Message) -> None:
        if message.author.bot:
            return
        assert client.user

        busy = _busy_wait_message()

        # Direct message
        if isinstance(message.channel, discord.DMChannel):
            text = (message.content or "").strip() or "（本文なし）"
            if not message.content:
                text += "\n※ 添付のみの場合は本文が空になります。"
            await message.channel.send(busy)
            answer = await _call_llm_backend(
                _mask_discord_markup_for_llm(text),
                discord_user_id=message.author.id,
            )
            await _reply_in_chunks(message.channel, answer, reference=message)
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

        reply_notice = await message.channel.send(
            busy,
            reference=message,
            mention_author=False,
        )
        answer = await _call_llm_backend(
            _mask_discord_markup_for_llm(body),
            discord_user_id=message.author.id,
        )
        try:
            await reply_notice.delete()
        except discord.HTTPException:
            pass
        await _reply_in_chunks(message.channel, answer, reference=message)

    client.run(token)


if __name__ == "__main__":
    main()
