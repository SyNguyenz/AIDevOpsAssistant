"""Gemini provider dùng langchain-google-genai."""

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

from app.config import settings
from app.llm.providers.base import BaseLLMProvider


class GeminiProvider(BaseLLMProvider):
    name = "gemini"

    def __init__(self, model: str = "gemini-2.0-flash") -> None:
        self._llm = ChatGoogleGenerativeAI(
            model=model,
            google_api_key=settings.gemini_api_key,
            temperature=0.2,
            max_retries=0,  # Tắt retry nội bộ — để router tự quyết fallback
        )

    def generate(self, prompt: str) -> str:
        response = self._llm.invoke([HumanMessage(content=prompt)])
        return response.content
