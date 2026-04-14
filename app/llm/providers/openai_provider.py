"""OpenAI provider dùng langchain-openai."""

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from app.config import settings
from app.llm.providers.base import BaseLLMProvider


class OpenAIProvider(BaseLLMProvider):
    name = "openai"

    def __init__(self, model: str = "gpt-4o-mini") -> None:
        self._llm = ChatOpenAI(
            model=model,
            openai_api_key=settings.openai_api_key,
            temperature=0.2,
        )

    def generate(self, prompt: str) -> str:
        response = self._llm.invoke([HumanMessage(content=prompt)])
        return response.content
