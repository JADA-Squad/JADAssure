"""FastAPI application entry point. Domain routers are registered here (AGENTS.md §7)."""

import pathlib
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import app.job_handlers  # noqa: F401  (registers handlers so the API can enqueue every kind)
from app.core import health, jobs_api
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.domains.access.router import auth_router, users_router
from app.domains.audit.router import router as audit_router
from app.domains.cases.router import corrections_router
from app.domains.cases.router import router as findings_router
from app.domains.connectors.router import router as connectors_router
from app.domains.contracts.router import router as agreements_router
from app.domains.ingestion.router import imports_router, sources_router
from app.domains.recovery.router import router as recovery_router
from app.domains.ingestion.router import router as ingestion_router
from app.domains.rules.router import router as rules_router
from app.domains.rules.runs_router import router as runs_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """With EMBEDDED_WORKER, run the job/heartbeat loop in a background thread (decision 0004 D-2)."""
    stop = threading.Event()
    thread = None
    if get_settings().embedded_worker:
        from app.worker import make_worker_id, run_loop

        thread = threading.Thread(target=run_loop, args=(stop, make_worker_id(":embedded")), daemon=True,
                                  name="jadassure-worker")
        thread.start()
    yield
    stop.set()
    if thread is not None:
        thread.join(timeout=10)


def _mount_frontend(app: FastAPI, dist: pathlib.Path) -> None:
    """Serve the built React app. Unknown non-API paths return index.html for client-side routing."""
    index = dist / "index.html"
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404, "Not found")
        candidate = (dist / path).resolve()
        if path and dist in candidate.parents and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(
        title="JADAssure API",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
        lifespan=lifespan,
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
    app.include_router(corrections_router)
    app.include_router(recovery_router)
    if settings.frontend_dist_path:
        dist = pathlib.Path(settings.frontend_dist_path).resolve()
        if (dist / "index.html").is_file():
            _mount_frontend(app, dist)  # registered last so every /api route wins
    return app


app = create_app()
