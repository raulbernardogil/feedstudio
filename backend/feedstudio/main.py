from __future__ import annotations

import time
import uuid
from pathlib import Path

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from feedstudio import __version__
from feedstudio.api import catalogs, channels, errors, rules, sources, system
from feedstudio.config import get_settings
from feedstudio.logging import configure_logging, log

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "static"


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(json_output=settings.environment != "test")
    app = FastAPI(
        title="Feed Studio API",
        version=__version__,
        description="Importación, transformación por reglas, validación y publicación de feeds XML de productos.",
    )
    errors.install(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_log(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        structlog.contextvars.bind_contextvars(request_id=request_id)
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        log.info("request", method=request.method, path=request.url.path, status=response.status_code,
                 ms=round((time.perf_counter() - started) * 1000, 1))
        structlog.contextvars.clear_contextvars()
        return response

    for module in (sources, catalogs, rules, channels, system):
        app.include_router(module.router)

    # Serve the built SPA when present (single-container deployment).
    if FRONTEND_DIST.exists():
        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            target = (FRONTEND_DIST / path).resolve()
            if path and FRONTEND_DIST in target.parents and target.is_file():
                return FileResponse(target)
            return FileResponse(FRONTEND_DIST / "index.html")

    return app


app = create_app()
