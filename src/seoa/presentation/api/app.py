"""FastAPI application factory (single user, localhost, no auth: belge 09 s.16)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import APIRouter, FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response

from seoa.application.audit.protocol import AuditService
from seoa.presentation.api.errors import install_handlers
from seoa.presentation.api.routers import api, ui
from seoa.presentation.web.html import STATIC_DIR

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
    "connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'; object-src 'none'"
)
SECURITY_HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Cross-Origin-Opener-Policy": "same-origin",
}


GoogleStatus = Callable[[], dict[str, Any] | Awaitable[dict[str, Any]]]


def create_app(
    service: AuditService,
    *,
    google_router: APIRouter | None = None,
    google_status: GoogleStatus | None = None,
) -> FastAPI:
    """``google_router`` (OAuth routes) and ``google_status`` (home-page card) are optional."""

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await service.start()
        try:
            yield
        finally:
            await service.stop()

    app = FastAPI(
        title="SEO Analyzer",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,  # the Swagger UI loads assets from a CDN, which the CSP forbids
        redoc_url=None,
        openapi_url="/v1/openapi.json",
    )
    app.state.service = service
    app.state.google_status = google_status
    app.state.idempotency = {}  # (path:key) -> (body digest, status, payload)

    @app.middleware("http")
    async def security_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        for k, v in SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        if request.url.path.startswith("/v1/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        return {"status": "ok"}

    install_handlers(app)
    app.include_router(api)
    app.include_router(ui)
    if google_router is not None:
        app.include_router(google_router)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    return app
