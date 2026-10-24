"""CodeAtlas API entry point. Run with ``uvicorn app.main:app`` from ``backend/``."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api.routes import health, jobs, projects
from app.core.config import MB, Settings, get_settings
from app.core.errors import AppError, register_error_handlers
from app.core.middleware import BodySizeLimitMiddleware, SecurityHeadersMiddleware
from app.repositories.project_store import ProjectStore
from app.services.job_service import JobManager

ANALYZE_PATH = "/api/projects/analyze"
MULTIPART_OVERHEAD_BYTES = 1 * MB


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    store = ProjectStore(settings.project_ttl_seconds, settings.max_stored_projects, settings.max_stored_nodes)
    job_manager = JobManager(settings, store)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        # Cancel running analyses and delete their work directories on shutdown.
        job_manager.shutdown()

    docs_enabled = not settings.is_production
    app = FastAPI(
        title="CodeAtlas API",
        version=__version__,
        docs_url="/api/docs" if docs_enabled else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if docs_enabled else None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.store = store
    app.state.jobs = job_manager

    register_error_handlers(app, include_tracebacks=not settings.is_production)
    app.include_router(health.router)
    app.include_router(projects.router)
    app.include_router(jobs.router)

    @app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
    def unknown_api_route(request: Request) -> None:
        raise AppError("not_found", "Unknown API endpoint.", 404)

    if settings.serve_frontend and settings.frontend_dir.is_dir():
        app.mount("/", StaticFiles(directory=settings.frontend_dir, html=True), name="frontend")

    # Middleware added last runs first: headers wrap everything, then the body limit, then CORS.
    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["Content-Type"],
        )
    app.add_middleware(
        BodySizeLimitMiddleware,
        max_bytes=settings.max_upload_bytes + MULTIPART_OVERHEAD_BYTES,
        paths={ANALYZE_PATH},
    )
    app.add_middleware(SecurityHeadersMiddleware, exempt_prefixes=("/api/docs",) if docs_enabled else ())
    return app


app = create_app()
