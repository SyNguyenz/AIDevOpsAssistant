"""Abstract base cho tất cả LLM providers."""

from abc import ABC, abstractmethod


class BaseLLMProvider(ABC):
    """Interface chung. Mỗi provider implement phương thức generate."""

    name: str = "base"

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Gọi LLM và trả về response text. Raise exception nếu lỗi."""
        ...

    def __repr__(self) -> str:
        return f"<LLMProvider: {self.name}>"
