"""
LLM Router: Gemini (primary) → Groq (fallback 1) → OpenAI (fallback 2)

Uses litellm.Router for automatic fallback on rate limit / API errors.
PR-Agent also uses litellm internally, so this router is for our custom
risk scoring prompts (KG context → structured explanation).
"""

import os
import litellm
from litellm import Router

# Suppress litellm verbose output unless debugging
litellm.suppress_debug_info = True

MODELS = [
    {
        "model_name": "primary",
        "litellm_params": {
            "model": "gemini/gemini-2.0-flash",
            "api_key": os.getenv("GEMINI_API_KEY"),
        },
    },
    {
        "model_name": "fallback-1",
        "litellm_params": {
            "model": "groq/llama-3.3-70b-versatile",
            "api_key": os.getenv("GROQ_API_KEY"),
        },
    },
    {
        "model_name": "fallback-2",
        "litellm_params": {
            "model": "gpt-4o-mini",
            "api_key": os.getenv("OPENAI_API_KEY"),
        },
    },
]

# Fallback order: primary → fallback-1 → fallback-2
FALLBACKS = [
    {"primary": ["fallback-1"]},
    {"fallback-1": ["fallback-2"]},
]

_router: Router | None = None


def get_router() -> Router:
    """Return singleton LLM router instance."""
    global _router
    if _router is None:
        _router = Router(
            model_list=MODELS,
            fallbacks=FALLBACKS,
            allowed_fails=1,        # trigger fallback after 1 failure
            retry_after=5,          # seconds before retry on same model
            num_retries=1,
        )
    return _router


async def chat(system: str, user: str, temperature: float = 0.2) -> str:
    """
    Send a chat completion request through the fallback chain.

    Returns the response text, or raises if all providers fail.
    """
    router = get_router()
    response = await router.acompletion(
        model="primary",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
    )
    return response.choices[0].message.content
