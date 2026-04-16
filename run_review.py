"""
Quick runner: chạy PR-Agent review trên một PR URL bất kỳ.
Dùng để test Week 4 milestone: PR-Agent chạy local, review được PR.

Usage:
    python run_review.py <PR_URL>
    python run_review.py https://github.com/owner/repo/pull/123

Yêu cầu:
    - Điền API keys vào .env (copy từ .env.example)
    - GITHUB_USER_TOKEN: GitHub PAT với repo scope
    - GEMINI_API_KEY (primary) hoặc GROQ_API_KEY (fallback 1) hoặc OPENAI_API_KEY (fallback 2)
"""

import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load .env trước khi import PR-Agent (dynaconf đọc env vars lúc init)
load_dotenv()

# Map env vars → dynaconf SECTION__KEY format (double underscore = nested key)
_ENV_MAP = {
    "GEMINI_API_KEY":    "GOOGLE_AI_STUDIO__GEMINI_API_KEY",
    "GROQ_API_KEY":      "GROQ__KEY",
    "OPENAI_API_KEY":    "OPENAI__KEY",
    "GITHUB_USER_TOKEN": "GITHUB__USER_TOKEN",
}
for src, dst in _ENV_MAP.items():
    if os.getenv(src) and not os.getenv(dst):
        os.environ[dst] = os.environ[src]

# Override model via env so dynaconf picks it up before global_settings is built
os.environ.setdefault("CONFIG__MODEL", "gemini/gemini-2.0-flash")
os.environ.setdefault("CONFIG__FALLBACK_MODELS", '["groq/llama-3.3-70b-versatile", "gpt-4o-mini"]')


async def main(pr_url: str):
    # Import AFTER env vars are set — dynaconf reads them at module load
    from pr_agent.agent.pr_agent import PRAgent
    from pr_agent.config_loader import get_settings

    # Load our project config on top of PR-Agent defaults
    config_path = Path(__file__).parent / "config" / "configuration.toml"
    secrets_path = Path(__file__).parent / "config" / ".secrets.toml"
    if config_path.exists():
        get_settings().load_file(str(config_path))
    if secrets_path.exists():
        get_settings().load_file(str(secrets_path))

    # Validate GitHub token
    github_token = get_settings().get("GITHUB.USER_TOKEN", None)
    if not github_token:
        print("ERROR: GITHUB_USER_TOKEN not set.")
        print("  → Add GITHUB_USER_TOKEN=<token> to .env")
        sys.exit(1)

    # Validate at least one LLM key
    gemini_key  = get_settings().get("GOOGLE_AI_STUDIO.GEMINI_API_KEY", None)
    groq_key    = get_settings().get("GROQ.KEY", None)
    openai_key  = get_settings().get("OPENAI.KEY", None)
    if not any([gemini_key, groq_key, openai_key]):
        print("ERROR: No LLM API key set.")
        print("  → Add GEMINI_API_KEY, GROQ_API_KEY, or OPENAI_API_KEY to .env")
        sys.exit(1)

    model = get_settings().config.model
    fallbacks = get_settings().config.get("fallback_models", [])
    print(f"Model    : {model}")
    print(f"Fallbacks: {fallbacks}")
    print(f"PR URL   : {pr_url}\n")

    agent = PRAgent()
    success = await agent.handle_request(pr_url, "review")
    if success:
        print("\nReview posted successfully.")
    else:
        print("\nReview failed — check logs above.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python run_review.py <PR_URL>")
        print("  e.g. python run_review.py https://github.com/owner/repo/pull/1")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
