"""HTTP routers, grouped by feature.

``api`` is the JSON API under ``/v1``; ``ui`` is the server-rendered pages.
"""

from fastapi import APIRouter

from seoa.presentation.api.routers import audit_pages, audits, home, meta, reports, settings

api = APIRouter(prefix="/v1")
for _router in (audits.router, reports.router, meta.router):
    api.include_router(_router)

ui = APIRouter()
for _router in (home.router, audit_pages.router, settings.router):
    ui.include_router(_router)

__all__ = ["api", "ui"]
