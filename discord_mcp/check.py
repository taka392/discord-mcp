"""Smoke-test Discord REST API with a bot token."""
from __future__ import annotations

import json
import sys

from .client import DiscordClient, DiscordError


def _dump(label: str, payload: object) -> None:
    print(f"\n=== {label} ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2)[:4000])


def main() -> int:
    try:
        client = DiscordClient()
    except DiscordError as exc:
        print(f"Setup error: {exc}", file=sys.stderr)
        return 1

    try:
        me = client.verify()
        _dump("verify (/users/@me)", me)
        guilds = client.list_guilds(limit=5)
        _dump("list_guilds (up to 5)", guilds)
    except DiscordError as exc:
        print(f"API error: {exc}", file=sys.stderr)
        return 1

    print("\nOK: end-to-end discord access works.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
