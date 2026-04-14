"""Groq provider dùng langchain-groq."""

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage

from app.config import settings
from app.llm.providers.base import BaseLLMProvider


class GroqProvider(BaseLLMProvider):
    name = "groq"

    def __init__(self, model: str = "llama-3.3-70b-versatile") -> None:
        self._llm = ChatGroq(
            model=model,
            groq_api_key=settings.groq_api_key,
            temperature=0.2,
        )

    def generate(self, prompt: str) -> str:
        response = self._llm.invoke([HumanMessage(content=prompt)])
        return response.content
