"""FastAPI application entry point. Domain routers are registered here (AGENTS.md §7)."""

from fastapi import FastAPI

import app.job_handlers  # noqa: F401  (registers handlers so the API can enqueue every kind)
from app.core import health, jobs_api
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.domains.access.router import auth_router, users_router
from app.domains.audit.router import router as audit_router
from app.domains.cases.router import router as findings_router
from app.domains.connectors.router import router as connectors_router
from app.domains.contracts.router import router as agreements_router
from app.domains.rules.router import router as rules_router
from app.domains.rules.runs_router import router as runs_router
from app.domains.ingestion.router import imports_router, sources_router
from app.domains.ingestion.router import router as ingestion_router


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
    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(audit_router)
    app.include_router(connectors_router)  # before sources_router: /data-sources/connector
    app.include_router(ingestion_router)
    app.include_router(sources_router)
    app.include_router(imports_router)
    app.include_router(jobs_api.router)
    app.include_router(agreements_router)
    app.include_router(rules_router)
    app.include_router(runs_router)
    app.include_router(findings_router)
    return app


app = create_app()
