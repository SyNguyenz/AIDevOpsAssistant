"""
Tests cho webhook endpoint.

Kiểm tra:
1. /health trả về 200
2. /webhook/github với event=ping → pong
3. /webhook/github với event=pull_request action=opened → trigger pipeline
4. /webhook/github với action không hỗ trợ → ignored
"""

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def make_signature(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(
        key=secret.encode(), msg=body, digestmod=hashlib.sha256
    ).hexdigest()


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_ping_event():
    resp = client.post(
        "/webhook/github",
        content=b"{}",
        headers={"X-Github-Event": "ping"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"message": "pong"}


def test_unknown_event():
    resp = client.post(
        "/webhook/github",
        content=b"{}",
        headers={"X-Github-Event": "push"},
    )
    assert resp.status_code == 200
    assert "không được xử lý" in resp.json()["message"]


@patch("app.webhook.handler.run_review_pipeline", new_callable=AsyncMock)
def test_pull_request_opened(mock_pipeline):
    mock_pipeline.return_value = {"comment_posted": True}

    payload = {
        "action": "opened",
        "pull_request": {"number": 42},
        "repository": {"full_name": "owner/repo"},
    }
    body = json.dumps(payload).encode()

    resp = client.post(
        "/webhook/github",
        content=body,
        headers={"X-Github-Event": "pull_request"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "processed"
    assert data["pr_number"] == 42
    mock_pipeline.assert_called_once_with(repo_full_name="owner/repo", pr_number=42)


@patch("app.webhook.handler.run_review_pipeline", new_callable=AsyncMock)
def test_pull_request_closed_ignored(mock_pipeline):
    payload = {
        "action": "closed",
        "pull_request": {"number": 10},
        "repository": {"full_name": "owner/repo"},
    }
    body = json.dumps(payload).encode()

    resp = client.post(
        "/webhook/github",
        content=body,
        headers={"X-Github-Event": "pull_request"},
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"
    mock_pipeline.assert_not_called()
