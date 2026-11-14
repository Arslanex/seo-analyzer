"""Helpers shared by the routers: lookups, idempotency, report building."""

from __future__ import annotations

import hashlib
import json
from typing import Any
from urllib.parse import urlparse

from fastapi import Request

from seoa.application.reporting import build_report, check_report
from seoa.application.reporting.history import (
    HistoryInput,
    pick_previous,
)
from seoa.application.reporting.schema import AuditReport
from seoa.domain import AuditRecord, AuditStatus
from seoa.presentation.api.deps import Service
from seoa.presentation.api.errors import ApiError
from seoa.presentation.web.html import render_report_html

TERMINAL = {AuditStatus.PARTIAL, AuditStatus.COMPLETED, AuditStatus.FAILED, AuditStatus.CANCELED}


ACTIVE = {AuditStatus.QUEUED, AuditStatus.RUNNING}


async def get_or_404(service: Service, audit_id: str) -> AuditRecord:
    rec = await service.get_audit(audit_id)
    if rec is None:
        raise ApiError("not-found", 404, "No such audit.")
    return rec


def require_terminal(rec: AuditRecord) -> None:
    if rec.status not in TERMINAL:
        raise ApiError(
            "audit-not-ready",
            409,
            "The report is not ready yet.",
            extra={"audit_status": rec.status.value},
        )


def links_for(audit_id: str) -> dict[str, str]:
    base = f"/v1/audits/{audit_id}"
    return {
        "self": base,
        "report": f"{base}/report",
        "events": f"{base}/events",
        "page": f"/audits/{audit_id}",
    }


async def run_idempotent(
    request: Request, key: str | None, body: dict[str, Any], make: Any
) -> tuple[int, dict[str, Any]]:
    """Replay the first response for the same Idempotency-Key + body (belge 06 s.3.1)."""
    if not key:
        return await make()  # type: ignore[no-any-return]
    store: dict[str, tuple[str, int, dict[str, Any]]] = request.app.state.idempotency
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()
    scoped = f"{request.url.path}:{key}"
    if scoped in store:
        prev_digest, status, payload = store[scoped]
        if prev_digest != digest:
            raise ApiError(
                "idempotency-key-reuse",
                422,
                "The same Idempotency-Key was used with a different body.",
            )
        return status, payload
    status, payload = await make()
    store[scoped] = (digest, status, payload)
    return status, payload


async def history_for(service: Service, rec: AuditRecord) -> HistoryInput:
    """Earlier audits of the same site and the closest older finished one (same mode)."""
    host = urlparse(rec.target_url).hostname or ""
    entries = await service.list_site_audits(host, 50)
    previous: AuditRecord | None = None
    prev_id = pick_previous(rec.id, rec.mode.value, entries)
    if prev_id:
        previous = await service.get_audit(prev_id)
    return HistoryInput(entries=entries, previous=previous)


def report_for(
    rec: AuditRecord, lang: str, history: HistoryInput | None = None
) -> tuple[AuditReport, str]:
    report = build_report(rec, lang, history=history)
    html = render_report_html(report, lang)
    report.quality = check_report(report, html, lang=lang)
    if report.quality.status == "FAIL":
        raise ApiError(
            "report-invalid",
            500,
            "The report failed the quality gate and is not shown.",
            errors=[
                {"field": c.id, "reason": c.detail[:120]}
                for c in report.quality.checks
                if c.status == "FAIL"
            ],
        )
    return report, html
