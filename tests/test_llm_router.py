"""
Tests cho LLM router.

Kiểm tra logic fallback: nếu provider đầu lỗi → chuyển sang provider tiếp theo.
Tất cả providers mock để không cần API key thật.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.llm.router import generate_with_fallback, LLMRouterError


def _mock_provider(name: str, response: str | None = None, raises: Exception | None = None):
    provider = MagicMock()
    provider.name = name
    if raises:
        provider.generate.side_effect = raises
    else:
        provider.generate.return_value = response
    return provider


@patch("app.llm.router._build_provider_chain")
def test_uses_first_provider_when_ok(mock_chain):
    gemini = _mock_provider("gemini", response="Review from Gemini")
    groq = _mock_provider("groq", response="Review from Groq")
    mock_chain.return_value = [gemini, groq]

    text, provider = generate_with_fallback("test prompt")

    assert text == "Review from Gemini"
    assert provider == "gemini"
    groq.generate.assert_not_called()


@patch("app.llm.router._build_provider_chain")
def test_fallback_to_groq_when_gemini_fails(mock_chain):
    gemini = _mock_provider("gemini", raises=Exception("API error"))
    groq = _mock_provider("groq", response="Review from Groq")
    mock_chain.return_value = [gemini, groq]

    text, provider = generate_with_fallback("test prompt")

    assert text == "Review from Groq"
    assert provider == "groq"


@patch("app.llm.router._build_provider_chain")
def test_raises_when_all_fail(mock_chain):
    gemini = _mock_provider("gemini", raises=Exception("Gemini down"))
    groq = _mock_provider("groq", raises=Exception("Groq down"))
    openai = _mock_provider("openai", raises=Exception("OpenAI down"))
    mock_chain.return_value = [gemini, groq, openai]

    with pytest.raises(LLMRouterError):
        generate_with_fallback("test prompt")
