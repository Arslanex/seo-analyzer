"""Audit lifecycle endpoints: create, status, events, cancel, rerun, Q&A and files."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import (
    JSONResponse,
    Response,
    StreamingResponse,
)

from seoa.application.audit.protocol import AuditEvent
from seoa.domain import AuditStatus
from seoa.presentation.api.deps import Service
from seoa.presentation.api.errors import ApiError
from seoa.presentation.api.schemas import CreateAuditRequest, QARequest, RerunRequest
from seoa.presentation.api.support import (
    ACTIVE,
    TERMINAL,
    get_or_404,
    links_for,
    require_terminal,
    run_idempotent,
)

router = APIRouter()


SCREENSHOT_NAMES = frozenset({"desktop.jpg", "mobile.jpg"})


@router.post("/audits", status_code=202)
async def create_audit(
    request: Request,
    body: CreateAuditRequest,
    service: Service,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key", max_length=128)] = None,
) -> JSONResponse:
    async def make() -> tuple[int, dict[str, Any]]:
        for s in await service.list_audits(100):
            if s.target_url == body.url and s.mode == body.mode and s.status in ACTIVE:
                raise ApiError(
                    "audit-in-progress",
                    409,
                    "An audit for this target and mode is already running.",
                    extra={"existing": links_for(s.id)},
                )
        audit_id = await service.create_audit(
            body.url,
            body.mode,
            max_pages=body.max_pages,
            enable_llm=body.enable_llm,
            lang=body.lang,
            keywords=body.keywords,
            competitors=body.competitors,
        )
        if body.keywords or body.competitors:  # API callers who send nothing keep the saved ones
            await service.save_profile(body.url, body.keywords, body.competitors)
        return 202, {
            "id": audit_id,
            "status": AuditStatus.QUEUED.value,
            "links": links_for(audit_id),
        }

    status, payload = await run_idempotent(
        request, idempotency_key, body.model_dump(mode="json"), make
    )
    return JSONResponse(payload, status_code=status, headers={"Location": payload["links"]["self"]})


@router.get("/audits")
async def list_audits(
    service: Service, limit: Annotated[int, Query(ge=1, le=200)] = 50
) -> dict[str, Any]:
    rows = await service.list_audits(limit)
    return {
        "data": [r.model_dump(mode="json") for r in rows],
        "next_cursor": None,
        "has_more": False,
    }


@router.get("/audits/{audit_id}")
async def get_audit(audit_id: str, service: Service) -> dict[str, Any]:
    rec = await get_or_404(service, audit_id)
    sc = rec.scores
    running = next((s for s in rec.stages if s.status.value == "running"), None)
    return {
        "id": rec.id,
        "mode": rec.mode.value,
        "status": rec.status.value,
        "target_url": rec.target_url,
        "created_at": rec.created_at.isoformat(),
        "finished_at": rec.finished_at.isoformat() if rec.finished_at else None,
        "stage": running.stage.value if running else None,
        "stages": [{"stage": s.stage.value, "status": s.status.value} for s in rec.stages],
        "overall": sc.overall if sc else None,
        "coverage_pct": sc.coverage_pct if sc else None,
        "insufficient_data": bool(sc and sc.insufficient_data),
        "partial_available": rec.status in TERMINAL,
        "error": rec.error.split(":")[0] if rec.error else None,
        "parent_audit_id": rec.parent_audit_id,
        "links": links_for(rec.id),
    }


@router.get("/audits/{audit_id}/files/{name}", response_model=None)
async def get_file(audit_id: str, name: str, service: Service) -> Response:
    """Screenshots of an audit. Allow-list of names; the path never comes from the client."""
    if name not in SCREENSHOT_NAMES:
        raise ApiError("not-found", 404, "No such file.")
    await get_or_404(service, audit_id)
    path = service.file_path(audit_id, name)
    if path is None:
        raise ApiError("not-found", 404, "No such file.")
    return Response(
        path.read_bytes(),
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"},
    )


@router.get("/audits/{audit_id}/sitemap.xml", response_model=None)
async def get_sitemap_xml(audit_id: str, service: Service) -> Response:
    """The suggested sitemap of a site audit, as a download."""
    from seoa.application.analysis.modules.sitemap_gen import SitemapGenerated

    rec = await get_or_404(service, audit_id)
    require_terminal(rec)
    raw = rec.extras.get("sitemap_generated")
    try:
        data = SitemapGenerated.model_validate(raw) if raw is not None else None
    except ValueError:
        data = None
    if data is None or not data.xml:
        raise ApiError("not-found", 404, "No suggested sitemap for this audit.")
    return Response(
        data.xml,
        media_type="application/xml",
        headers={
            "Content-Disposition": 'attachment; filename="sitemap.xml"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, max-age=3600",
        },
    )


def _sse(ev: AuditEvent) -> str:
    kind = "stage" if ev.stage else "audit"
    return f"id: {ev.seq}\nevent: {kind}\ndata: {ev.model_dump_json()}\n\n"


@router.get("/audits/{audit_id}/events")
async def audit_events(
    audit_id: str,
    service: Service,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID", max_length=16)] = None,
    after: Annotated[int, Query(ge=0)] = 0,
) -> StreamingResponse:
    await get_or_404(service, audit_id)
    try:
        start = int(last_event_id) if last_event_id else after
    except ValueError:
        start = after

    async def gen() -> AsyncIterator[str]:
        yield "retry: 3000\n\n"
        async for ev in service.events(audit_id, start):
            yield _sse(ev)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/audits/{audit_id}/cancel")
async def cancel_audit(audit_id: str, service: Service) -> dict[str, Any]:
    await get_or_404(service, audit_id)
    ok = await service.cancel(audit_id)
    rec = await service.get_audit(audit_id)
    return {"id": audit_id, "canceled": ok, "status": rec.status.value if rec else None}


@router.post("/audits/{audit_id}/rerun", status_code=202)
async def rerun_audit(
    request: Request,
    audit_id: str,
    body: RerunRequest,
    service: Service,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key", max_length=128)] = None,
) -> JSONResponse:
    await get_or_404(service, audit_id)

    async def make() -> tuple[int, dict[str, Any]]:
        new_id = await service.rerun(audit_id, body.modules)
        return 202, {
            "id": new_id,
            "parent_audit_id": audit_id,
            "status": AuditStatus.QUEUED.value,
            "links": links_for(new_id),
        }

    status, payload = await run_idempotent(
        request, idempotency_key, {"audit": audit_id, **body.model_dump()}, make
    )
    return JSONResponse(payload, status_code=status, headers={"Location": payload["links"]["self"]})


@router.post("/audits/{audit_id}/qa")
async def ask(audit_id: str, body: QARequest, service: Service) -> dict[str, Any]:
    rec = await get_or_404(service, audit_id)
    require_terminal(rec)
    answer = await service.ask(audit_id, body.question)
    return answer.model_dump(mode="json")
