"""FastAPI application entrypoint for YAIRS."""

from __future__ import annotations

import logging
import time
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from src.api.dependencies import get_container, get_settings, get_workflow_executor
from src.api.errors import add_exception_handlers
from src.api.routes.generation import router as generation_router
from src.api.routes.health import router as health_router
from src.api.routes.intelligence import router as intelligence_router
from src.api.routes.research import router as research_router

logger = logging.getLogger("yairs.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize container on startup and cleanup on shutdown.

    On startup, resume any workflows that were left in 'pending', 'queued', or 'running' states.
    Workflows are resumed by spawning background threads that call the workflow executor.
    """
    container = get_container()

    # resume incomplete workflows from the DB if possible
    try:
        db = container.database_service
        if db:
            incomplete = db.get_workflows_by_status(["pending", "queued", "running"])
            if incomplete:
                logger.info("Resuming %d incomplete workflows on startup", len(incomplete))
                from threading import Thread

                executor = get_workflow_executor()
                for row in incomplete:
                    wf_id = row.get("workflow_id")
                    payload = row.get("payload") if row.get("payload") is not None else (json.loads(row.get("payload_json")) if row.get("payload_json") else {})
                    # Mark queued to avoid races
                    try:
                        db.update_workflow_record(wf_id, status="queued")
                    except Exception:
                        pass
                    def _run_in_thread(wid, pl):
                        try:
                            executor.run(wid, pl)
                        except Exception:
                            logger.exception("Resumed workflow %s failed", wid)
                    t = Thread(target=_run_in_thread, args=(wf_id, payload), daemon=True)
                    t.start()
    except Exception:
        logger.exception("Failed to resume workflows on startup")

    yield


def create_app() -> FastAPI:
    """Create and configure FastAPI app."""
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Production API for YouTube AI Research System agents and pipelines.",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    add_exception_handlers(app)

    @app.middleware("http")
    async def request_logging_middleware(request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.info(
            "request path=%s method=%s status=%s duration_ms=%s",
            request.url.path,
            request.method,
            response.status_code,
            duration_ms,
        )
        return response

    app.include_router(health_router)
    app.include_router(research_router)
    app.include_router(generation_router)
    app.include_router(intelligence_router)
    return app


app = create_app()
