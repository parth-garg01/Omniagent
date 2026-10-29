from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NOVA_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./nova.db"
    llm_provider: str = "fake"
    llm_fallback_provider: str = ""  # empty = no fallback (default)
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-5-5"
    data_root: str = ""  # dir containing data/ and evals/; auto-detected in a checkout
    session_ttl_hours: int = 24
    max_upload_bytes: int = 2_000_000
    cookie_secure: bool = False
    max_message_chars: int = 4000
    context_max_messages: int = 20
    login_max_attempts: int = 5
    login_window_seconds: int = 300
    chunk_size: int = 600
    chunk_overlap: int = 100
    retrieval_min_score: float = 0.2
    max_tool_iterations: int = 3

    @field_validator("llm_provider", "llm_fallback_provider")
    @classmethod
    def _known_provider(cls, v: str) -> str:
        if v not in {"", "fake", "anthropic"}:
            raise ValueError(f"unknown provider: {v}")
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
