# cursor-cli-homelab の Dockerfile.gateway と同期すること（standalone ビルド用）
FROM debian:bookworm-slim

RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    tar \
    git \
    python3 \
    python3-pip \
  && rm -rf /var/lib/apt/lists/*

ENV HOME=/root
ENV PATH="/root/.local/bin:${PATH}"

RUN curl -fsSL https://cursor.com/install | bash \
  && agent --version

RUN pip3 install --break-system-packages --no-cache-dir \
    "fastapi>=0.115.0" \
    "uvicorn[standard]>=0.32.0" \
    "pydantic>=2.0"

COPY gateway /app/gateway
WORKDIR /workspace

ENV PYTHONUNBUFFERED=1
EXPOSE 9888

ENTRYPOINT []
CMD ["uvicorn", "gateway.main:app", "--host", "0.0.0.0", "--port", "9888", "--app-dir", "/app"]
