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
    demo_data_path: str = "/demo-data"
    # Lists the seeded DEMO accounts on the login page. Local demos only; keep false anywhere shared.
    show_demo_accounts: bool = False

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5-5"
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1"

    log_level: str = "INFO"

    # Deployment (decision 0004). Single-service hosting runs the worker loop inside the API process
    # and serves the built React app from FRONTEND_DIST_PATH.
    embedded_worker: bool = False
    frontend_dist_path: str | None = None
    seed_demo_on_start: bool = False

    @field_validator("database_url", "test_database_url")
    @classmethod
    def _psycopg_driver(cls, v: str | None) -> str | None:
        """Hosts such as Render hand out postgres:// URLs; SQLAlchemy needs the psycopg 3 driver named."""
        if v is None:
            return v
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix):]
        return v

    @field_validator("jwt_secret")
    @classmethod
    def _secret_must_be_real(cls, v: str) -> str:
        if v.strip() in _PLACEHOLDER_SECRETS or len(v) < 32:
            raise ValueError("JWT_SECRET must be set to a random value of at least 32 characters")
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
