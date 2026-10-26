"""FastAPI application entry point. Domain routers are registered here (AGENTS.md §7)."""

from fastapi import FastAPI

from app.core import health
from app.core.config import get_settings
from app.core.logging import configure_logging


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(
        title="JADAssure API",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    app.include_router(health.router)
    return app


app = create_app()
