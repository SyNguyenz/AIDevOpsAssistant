"""
FastAPI application entry point.

Routes:
  GET  /health              — health check
  POST /webhook/github      — GitHub webhook endpoint
  GET  /repos/{owner}/{repo}/pulls — list open PRs (dev/test helper)
"""

import json
import logging

import uvicorn
from fastapi import FastAPI, Header, Request, HTTPException
from fastapi.responses import JSONResponse

from app.config import settings
from app.webhook.validator import verify_github_signature
from app.webhook.handler import handle_pull_request_event
from app.github.client import list_open_prs

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)

app = FastAPI(
    title="AI DevOps Assistant",
    description="Context-aware PR review bot powered by LangGraph + LLM",
    version="0.1.0",
)


@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "0.1.0"}


@app.post("/webhook/github")
async def github_webhook(
    request: Request,
    x_github_event: str = Header(default=""),
):
    """
    Nhận GitHub webhook events.
    Xác thực signature, sau đó dispatch theo event type.
    """
    body = await verify_github_signature(request)

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}") from exc

    if x_github_event == "ping":
        return {"message": "pong"}

    if x_github_event == "pull_request":
        result = await handle_pull_request_event(payload)
        return JSONResponse(content=result)

    return {"message": f"Event '{x_github_event}' không được xử lý"}


@app.get("/repos/{owner}/{repo}/pulls")
async def list_prs(owner: str, repo: str):
    """Dev helper: list open PRs của một repo."""
    repo_full_name = f"{owner}/{repo}"
    try:
        prs = list_open_prs(repo_full_name)
        return {"repo": repo_full_name, "open_prs": prs}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
