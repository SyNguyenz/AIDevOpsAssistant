"""
LLM Router: Gemini → Groq → OpenAI (fallback chain).

Logic:
1. Thử Gemini trước (rẻ + nhanh).
2. Nếu Gemini raise exception → thử Groq.
3. Nếu Groq cũng lỗi → thử OpenAI.
4. Tất cả đều lỗi → raise LLMRouterError.

Provider nào bị thiếu API key thì tự động bỏ qua (skip).
"""

import logging
from typing import Optional

from app.config import settings
from app.llm.providers.base import BaseLLMProvider
from app.llm.providers.gemini import GeminiProvider
from app.llm.providers.groq import GroqProvider
from app.llm.providers.openai_provider import OpenAIProvider

logger = logging.getLogger(__name__)


class LLMRouterError(Exception):
    """Raise khi tất cả providers đều thất bại."""


def _build_provider_chain() -> list[BaseLLMProvider]:
    """Tạo danh sách providers theo thứ tự ưu tiên, bỏ qua provider thiếu key."""
    chain: list[BaseLLMProvider] = []

    if settings.gemini_api_key:
        chain.append(GeminiProvider())
    if settings.groq_api_key:
        chain.append(GroqProvider())
    if settings.openai_api_key:
        chain.append(OpenAIProvider())

    if not chain:
        raise LLMRouterError(
            "Không có LLM provider nào được cấu hình. "
            "Hãy set ít nhất một trong: GEMINI_API_KEY, GROQ_API_KEY, OPENAI_API_KEY."
        )

    return chain


def generate_with_fallback(prompt: str) -> tuple[str, str]:
    """
    Gọi LLM với fallback chain.

    Returns:
        (response_text, provider_name_used)

    Raises:
        LLMRouterError: nếu mọi provider đều lỗi.
    """
    providers = _build_provider_chain()
    last_error: Optional[Exception] = None

    for provider in providers:
        try:
            logger.info("Thử provider: %s", provider.name)
            response = provider.generate(prompt)
            logger.info("Thành công với provider: %s", provider.name)
            return response, provider.name
        except Exception as exc:
            logger.warning("Provider %s lỗi: %s", provider.name, exc)
            last_error = exc

    raise LLMRouterError(
        f"Tất cả LLM providers đều thất bại. Lỗi cuối: {last_error}"
    ) from last_error
