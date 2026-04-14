"""
LangGraph state definition cho review pipeline.

State là một TypedDict — mỗi node đọc vào và trả về
dict chứa các key muốn cập nhật (merge tự động bởi LangGraph).
"""

from typing import Optional
from typing_extensions import TypedDict


class ReviewState(TypedDict):
    # Input
    repo_full_name: str
    pr_number: int

    # Sau node fetch_pr_diff
    diff: str
    pr_title: str
    pr_author: str

    # Sau node build_prompt
    prompt: str

    # Sau node call_llm
    review_text: str
    provider_used: str

    # Sau node post_comment
    comment_posted: bool
    error: Optional[str]
