"""Application settings, read only from environment variables (NFR-10)."""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PLACEHOLDER_SECRETS = {"", "change-me"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    database_url: str
    test_database_url: str | None = None

    jwt_secret: str
    jwt_expires_minutes: int = 480
    allow_signup: bool = True

    worker_poll_seconds: float = 2.0
    worker_heartbeat_stale_seconds: int = 30

    document_store_path: str = "/data/documents"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5-5"

    log_level: str = "INFO"

    @field_validator("jwt_secret")
    @classmethod
    def _secret_must_be_real(cls, v: str) -> str:
        if v.strip() in _PLACEHOLDER_SECRETS or len(v) < 32:
            raise ValueError("JWT_SECRET must be set to a random value of at least 32 characters")
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
