"""
GitHub webhook event handler.

Các event quan tâm:
- pull_request (opened / synchronize / reopened) → trigger review pipeline
"""

import logging

from app.agent.orchestrator import run_review_pipeline

logger = logging.getLogger(__name__)

# Action của pull_request event mà ta xử lý
HANDLED_ACTIONS = {"opened", "synchronize", "reopened"}


async def handle_pull_request_event(payload: dict) -> dict:
    """
    Xử lý webhook payload của event pull_request.
    Trả về dict mô tả kết quả để tiện log / test.
    """
    action = payload.get("action", "")
    pr_data = payload.get("pull_request", {})
    repo_data = payload.get("repository", {})

    pr_number: int = pr_data.get("number", 0)
    repo_full_name: str = repo_data.get("full_name", "")

    if action not in HANDLED_ACTIONS:
        logger.info("Bỏ qua action=%s cho PR #%d", action, pr_number)
        return {"status": "ignored", "action": action}

    logger.info("Xử lý PR #%d (%s) repo=%s", pr_number, action, repo_full_name)

    result = await run_review_pipeline(
        repo_full_name=repo_full_name,
        pr_number=pr_number,
    )

    return {"status": "processed", "pr_number": pr_number, "result": result}
