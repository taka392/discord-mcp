# Discord Gateway reply bot only (not the MCP stdio server).
FROM python:3.11-slim-bookworm

WORKDIR /app

COPY pyproject.toml LICENSE README.md ./
COPY discord_mcp ./discord_mcp

RUN pip install --no-cache-dir -U pip setuptools \
    && pip install --no-cache-dir ".[reply-bot]"

ENV PYTHONUNBUFFERED=1

# Token at runtime: docker compose / -e DISCORD_BOT_TOKEN
CMD ["discord-reply-bot"]
