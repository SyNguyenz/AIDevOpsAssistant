"""
LangGraph orchestrator — review pipeline.

Graph:
  fetch_pr_diff → build_prompt → call_llm → post_comment

Mỗi node là một hàm thuần tuý nhận ReviewState, trả về dict update.
"""

import logging
from typing import Any

from langgraph.graph import StateGraph, END

from app.agent.state import ReviewState
from app.github import client as gh
from app.llm.router import generate_with_fallback, LLMRouterError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

def fetch_pr_diff(state: ReviewState) -> dict[str, Any]:
    """Node 1: Lấy diff + metadata của PR từ GitHub."""
    repo = state["repo_full_name"]
    pr_num = state["pr_number"]

    try:
        pr = gh.get_pull_request(repo, pr_num)
        diff = gh.get_pr_diff(repo, pr_num)
        return {
            "diff": diff,
            "pr_title": pr.title,
            "pr_author": pr.user.login,
            "error": None,
        }
    except Exception as exc:
        logger.error("fetch_pr_diff lỗi: %s", exc)
        return {"diff": "", "pr_title": "", "pr_author": "", "error": str(exc)}


def build_prompt(state: ReviewState) -> dict[str, Any]:
    """Node 2: Xây dựng prompt có cấu trúc cho LLM."""
    if state.get("error"):
        return {"prompt": ""}

    prompt = f"""Bạn là một senior software engineer đang review code.

## Pull Request
- **Title:** {state["pr_title"]}
- **Author:** {state["pr_author"]}
- **Repo:** {state["repo_full_name"]}
- **PR #:** {state["pr_number"]}

## Diff
```diff
{state["diff"]}
```

## Nhiệm vụ
Hãy review code diff trên và đưa ra nhận xét theo cấu trúc sau:

### Summary
(Tóm tắt thay đổi trong 2-3 câu)

### Issues Found
(Liệt kê các vấn đề: bug tiềm ẩn, logic sai, security risk, v.v.)

### Suggestions
(Đề xuất cải thiện cụ thể)

### Risk Level
(Low / Medium / High — kèm lý do)

Hãy trả lời bằng tiếng Anh, ngắn gọn và actionable.
"""
    return {"prompt": prompt}


def call_llm(state: ReviewState) -> dict[str, Any]:
    """Node 3: Gọi LLM router (Gemini → Groq → OpenAI)."""
    if state.get("error") or not state.get("prompt"):
        return {"review_text": "", "provider_used": "none"}

    try:
        review_text, provider = generate_with_fallback(state["prompt"])
        return {"review_text": review_text, "provider_used": provider}
    except LLMRouterError as exc:
        logger.error("call_llm lỗi: %s", exc)
        return {
            "review_text": "",
            "provider_used": "none",
            "error": str(exc),
        }


def post_comment(state: ReviewState) -> dict[str, Any]:
    """Node 4: Đăng review comment lên GitHub PR."""
    if state.get("error") or not state.get("review_text"):
        # Nếu có lỗi, vẫn post một comment thông báo
        error_msg = state.get("error", "Unknown error")
        body = f"⚠️ **AI DevOps Assistant** gặp lỗi khi review PR này:\n\n`{error_msg}`"
        try:
            gh.post_pr_comment(state["repo_full_name"], state["pr_number"], body)
        except Exception:
            pass
        return {"comment_posted": False}

    provider = state.get("provider_used", "unknown")
    body = (
        f"## 🤖 AI Code Review\n\n"
        f"{state['review_text']}\n\n"
        f"---\n"
        f"*Reviewed by AI DevOps Assistant · Provider: `{provider}`*"
    )

    try:
        gh.post_pr_comment(state["repo_full_name"], state["pr_number"], body)
        logger.info("Đã post comment lên PR #%d", state["pr_number"])
        return {"comment_posted": True}
    except Exception as exc:
        logger.error("post_comment lỗi: %s", exc)
        return {"comment_posted": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Build graph
# ---------------------------------------------------------------------------

def _build_graph() -> Any:
    graph = StateGraph(ReviewState)

    graph.add_node("fetch_pr_diff", fetch_pr_diff)
    graph.add_node("build_prompt", build_prompt)
    graph.add_node("call_llm", call_llm)
    graph.add_node("post_comment", post_comment)

    graph.set_entry_point("fetch_pr_diff")
    graph.add_edge("fetch_pr_diff", "build_prompt")
    graph.add_edge("build_prompt", "call_llm")
    graph.add_edge("call_llm", "post_comment")
    graph.add_edge("post_comment", END)

    return graph.compile()


_compiled_graph = _build_graph()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def run_review_pipeline(repo_full_name: str, pr_number: int) -> dict[str, Any]:
    """
    Chạy toàn bộ review pipeline cho một PR.
    Trả về final state dict.
    """
    initial_state: ReviewState = {
        "repo_full_name": repo_full_name,
        "pr_number": pr_number,
        "diff": "",
        "pr_title": "",
        "pr_author": "",
        "prompt": "",
        "review_text": "",
        "provider_used": "",
        "comment_posted": False,
        "error": None,
    }

    final_state = await _compiled_graph.ainvoke(initial_state)
    return final_state
