from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # GitHub
    github_app_id: int = 0
    github_private_key_path: str = "private-key.pem"
    github_webhook_secret: str = ""
    github_token: str = ""  # Personal Access Token (dev/test)

    # LLM providers
    gemini_api_key: str = ""
    groq_api_key: str = ""
    openai_api_key: str = ""

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False


settings = Settings()
