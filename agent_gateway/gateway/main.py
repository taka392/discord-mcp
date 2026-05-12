"""HTTP ゲートウェイ: homelab 上の `agent` CLI を叩く。（cursor-cli-homelab のコピー）"""
from __future__ import annotations

import os
import subprocess
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

REQUEST_TIMEOUT_SEC = int(os.getenv("AGENT_REQUEST_TIMEOUT_SEC", "600"))


@asynccontextmanager
async def _lifespan(app: FastAPI):
    enforce = os.getenv("GATEWAY_ENFORCE_TOKEN", "").lower() in ("1", "true", "yes")
    if enforce and not (os.getenv("GATEWAY_TOKEN") or "").strip():
        raise RuntimeError(
            "GATEWAY_ENFORCE_TOKEN is set but GATEWAY_TOKEN is empty"
        )
    yield


app = FastAPI(
    title="cursor-agent-gateway",
    version="0.1.0",
    lifespan=_lifespan,
)


def _require_token(authorization: Optional[str], x_gateway_token: Optional[str]) -> None:
    expected = (os.getenv("GATEWAY_TOKEN") or "").strip()
    if not expected:
        return
    bearer = ""
    if authorization and authorization.lower().startswith("bearer "):
        bearer = authorization[7:].strip()
    if bearer == expected or (x_gateway_token or "").strip() == expected:
        return
    raise HTTPException(status_code=401, detail="invalid or missing gateway token")


class PromptBody(BaseModel):
    prompt: str = Field(..., min_length=1)
    trust_workspace: bool = Field(
        default=True,
        description="agent -p に --trust を付けます（/workspace 前提）。",
    )


@app.get("/health")
def health(
    authorization: Optional[str] = Header(default=None),
    x_gateway_token: Optional[str] = Header(default=None, alias="X-Gateway-Token"),
) -> dict[str, str]:
    _require_token(authorization, x_gateway_token)
    return {"status": "ok"}


@app.get("/v1/version")
def agent_version(
    authorization: Optional[str] = Header(default=None),
    x_gateway_token: Optional[str] = Header(default=None, alias="X-Gateway-Token"),
) -> dict[str, str]:
    _require_token(authorization, x_gateway_token)
    env = os.environ.copy()
    try:
        proc = subprocess.run(
            ["agent", "--version"],
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
            cwd="/workspace",
            check=False,
        )
    except subprocess.SubprocessError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    ver = (proc.stdout or proc.stderr or "").strip()
    if proc.returncode != 0:
        raise HTTPException(status_code=500, detail=ver or "agent --version failed")
    return {"version": ver}


@app.post("/v1/prompt")
def run_prompt(
    body: PromptBody,
    authorization: Optional[str] = Header(default=None),
    x_gateway_token: Optional[str] = Header(default=None, alias="X-Gateway-Token"),
) -> dict[str, object]:
    _require_token(authorization, x_gateway_token)
    if not (os.getenv("CURSOR_API_KEY") or "").strip():
        raise HTTPException(
            status_code=503,
            detail="CURSOR_API_KEY is not set in the gateway container",
        )
    cmd: list[str] = ["agent", "-p", "--output-format", "text"]
    if os.getenv("AGENT_APPROVE_MCPS", "").lower() in ("1", "true", "yes"):
        cmd.append("--approve-mcps")
    if body.trust_workspace:
        cmd.append("--trust")
    cmd.append(body.prompt)
    env = os.environ.copy()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=REQUEST_TIMEOUT_SEC,
            env=env,
            cwd="/workspace",
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="agent timed out") from None
    except subprocess.SubprocessError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    return {
        "exit_code": proc.returncode,
        "stdout": out,
        "stderr": err,
    }
