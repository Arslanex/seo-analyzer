"""Report and deep-analysis endpoints (findings, pages, links, performance, history ...)."""

from __future__ import annotations

from typing import Annotated, Any
from urllib.parse import urlparse

from fastapi import APIRouter, Path, Query, Request
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    Response,
)

from seoa.application.analysis.compare import compare
from seoa.application.reporting import build_report, deep, extra, suite
from seoa.application.reporting.history import (
    competitors_section,
    history_section,
)
from seoa.application.reporting.rankings import rankings_section
from seoa.domain import Category, Layer, Severity
from seoa.domain.i18n import reason_text
from seoa.presentation.api.deps import Service, pick_lang
from seoa.presentation.api.errors import ApiError
from seoa.presentation.api.schemas import MAX_URL
from seoa.presentation.api.support import get_or_404, history_for, report_for, require_terminal

router = APIRouter()


@router.get("/audits/{audit_id}/report", response_model=None)
async def get_report(
    request: Request,
    audit_id: str,
    service: Service,
    lang: str | None = None,
    format: Annotated[str, Query(pattern="^(json|html)$")] = "json",  # noqa: A002
) -> Response:
    rec = await get_or_404(service, audit_id)
    require_terminal(rec)
    lg = pick_lang(request, lang)
    report, html = report_for(rec, lg, await history_for(service, rec))
    if format == "html":
        return HTMLResponse(html)
    return JSONResponse(report.model_dump(mode="json"))


@router.get("/audits/{audit_id}/findings")
async def get_findings(
    audit_id: str,
    request: Request,
    service: Service,
    severity: Severity | None = None,
    category: Category | None = None,
    layer: Layer | None = None,
    scope: Annotated[str | None, Query(pattern="^(page|site)$")] = None,
    check_id: Annotated[str | None, Query(max_length=80)] = None,
    sort: Annotated[str, Query(pattern="^(severity|priority)$")] = "severity",
    lang: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query(max_length=16)] = None,
) -> dict[str, Any]:
    rec = await get_or_404(service, audit_id)
    require_terminal(rec)
    report = build_report(rec, pick_lang(request, lang))
    items = report.findings
    if severity:
        items = [f for f in items if f.severity == severity]
    if category:
        items = [f for f in items if f.category == category]
    if layer:
        items = [f for f in items if f.layer == layer]
    if scope:
        items = [f for f in items if f.scope == scope]
    if check_id:
        items = [f for f in items if f.check_id == check_id]
    if sort == "priority":
        prio = {r.finding_ids[0]: r.priority_score for r in report.recommendations}
        items = sorted(items, key=lambda f: -prio.get(f.id, 0))
    try:
        start = int(cursor) if cursor else 0
    except ValueError as exc:
        raise ApiError(
            "validation-error",
            422,
            "Invalid cursor.",
            errors=[{"field": "cursor", "reason": "invalid"}],
        ) from exc
    page = items[start : start + limit]
    more = start + limit < len(items)
    return {
        "data": [f.model_dump(mode="json") for f in page],
        "next_cursor": str(start + limit) if more else None,
        "has_more": more,
        "total": len(items),
    }


@router.get("/audits/{audit_id}/pages")
async def get_pages(audit_id: str, service: Service) -> dict[str, Any]:
    rec = await get_or_404(service, audit_id)
    return {
        "data": [
            {
                "url": p.url,
                "status": p.status,
                "role": p.sample_kind,
                "template": p.template_key,
                "error": p.error,
                "rendered": p.rendered,
            }
            for p in rec.pages
        ]
    }


def _section_json(sec: Any) -> dict[str, Any]:
    data: dict[str, Any] = sec.model_dump(mode="json")
    return data


@router.get("/audits/{audit_id}/links", response_model=None)
async def get_links(
    audit_id: str,
    request: Request,
    service: Service,
    kind: Annotated[str | None, Query(pattern="^(internal|external)$")] = None,
    broken: bool = False,
    source: Annotated[str | None, Query(max_length=MAX_URL)] = None,
    lang: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query(max_length=16)] = None,
    download: bool = False,
) -> Response:
    rec = await get_or_404(service, audit_id)
    require_terminal(rec)
    lg = pick_lang(request, lang)
    if rec.links is None:
        return JSONResponse(
            {
                "status": "not_measured",
                "reason": "analysis-not-run",
                "reason_text": reason_text(lg, "analysis-not-run"),
                "data": [],
                "total": 0,
                "next_cursor": None,
                "has_more": False,
            }
        )
    rows = [deep._link_row(lk, lg) for lk in rec.links.links]
    summary = rec.links.model_dump(mode="json", exclude={"links", "pages"})
    pages = [p.model_dump(mode="json") for p in rec.links.pages]
    if download:
        return JSONResponse(
            {
                "status": "measured",
                "summary": summary,
                "pages": pages,
                "links": [r.model_dump(mode="json") for r in rows],
            },
            headers={"Content-Disposition": f'attachment; filename="links-{audit_id}.json"'},
        )
    if kind:
        rows = [r for r in rows if r.kind == kind]
    if broken:
        rows = [r for r in rows if r.state == "broken"]
    if source:
        rows = [r for r in rows if r.source_url == source]
    try:
        start = int(cursor) if cursor else 0
    except ValueError as exc:
        raise ApiError(
            "validation-error",
            422,
            "Invalid cursor.",
            errors=[{"field": "cursor", "reason": "invalid"}],
        ) from exc
    page = rows[start : start + limit]
    more = start + limit < len(rows)
    return JSONResponse(
        {
            "status": "measured",
            "summary": summary,
            "pages": pages,
            "data": [r.model_dump(mode="json") for r in page],
            "total": len(rows),
            "next_cursor": str(start + limit) if more else None,
            "has_more": more,
        }
    )


async def _deep_endpoint(
    audit_id: str, request: Request, service: Service, lang: str | None, name: str
) -> dict[str, Any]:
    rec = await get_or_404(service, audit_id)
    require_terminal(rec)
    lg = pick_lang(request, lang)
    sections = {
        "perf": deep.performance_section,
        "images": deep.images_section,
        "indexability": deep.indexability_section,
        "visibility": deep.visibility_section,
        "gsc": deep.gsc_section,
        "field": deep.field_section,
        "techstack": suite.techstack_section,
        "site-setup": suite.site_setup_section,
        "previews": suite.previews_section,
        "readability": suite.readability_section,
        "hreflang": suite.hreflang_section,
        "schema-suggestions": suite.schema_suggest_section,
        "agentic": suite.agentic_section,
        "competitors": competitors_section,
        "local": extra.local_section,
        "sitemap-suggestion": extra.sitemap_gen_section,
        "authority": extra.authority_section,
        "rankings": rankings_section,
    }
    if name == "screenshots":
        return _section_json(suite.screenshots_section(rec, lg, rec.id))
    return _section_json(sections[name](rec, lg))


@router.get("/audits/{audit_id}/perf")
async def get_perf(
    audit_id: str, request: Request, service: Service, lang: str | None = None
) -> dict[str, Any]:
    return await _deep_endpoint(audit_id, request, service, lang, "perf")


@router.get("/audits/{audit_id}/images")
async def get_images(
    audit_id: str, request: Request, service: Service, lang: str | None = None
) -> dict[str, Any]:
    return await _deep_endpoint(audit_id, request, service, lang, "images")


@router.get("/audits/{audit_id}/indexability")
async def get_indexability(
    audit_id: str, request: Request, service: Service, lang: str | None = None
) -> dict[str, Any]:
    return await _deep_endpoint(audit_id, request, service, lang, "indexability")


@router.get("/audits/{audit_id}/visibility")
async def get_visibility(
    audit_id: str, request: Request, service: Service, lang: str | None = None
) -> dict[str, Any]:
    return await _deep_endpoint(audit_id, request, service, lang, "visibility")


@router.get("/audits/{audit_id}/gsc")
async def get_gsc(
    audit_id: str, request: Request, service: Service, lang: str | None = None
) -> dict[str, Any]:
    return await _deep_endpoint(audit_id, request, service, lang, "gsc")


@router.get("/audits/{audit_id}/field")
async def get_field(
    audit_id: str, request: Request, service: Service, lang: str | None = None
) -> dict[str, Any]:
    return await _deep_endpoint(audit_id, request, service, lang, "field")


for _name in (
    "techstack",
    "site-setup",
    "previews",
    "screenshots",
    "readability",
    "hreflang",
    "schema-suggestions",
    "agentic",
    "competitors",
    "local",
    "sitemap-suggestion",
    "authority",
    "rankings",
):

    def _make(name: str) -> Any:
        async def endpoint(
            audit_id: str, request: Request, service: Service, lang: str | None = None
        ) -> dict[str, Any]:
            return await _deep_endpoint(audit_id, request, service, lang, name)

        endpoint.__name__ = f"get_{name.replace('-', '_')}"
        return endpoint

    router.add_api_route(f"/audits/{{audit_id}}/{_name}", _make(_name), methods=["GET"])


@router.get("/audits/{audit_id}/history")
async def get_history(
    audit_id: str, request: Request, service: Service, lang: str | None = None
) -> dict[str, Any]:
    rec = await get_or_404(service, audit_id)
    require_terminal(rec)
    lg = pick_lang(request, lang)
    return _section_json(history_section(rec, lg, await history_for(service, rec)))


@router.get("/audits/{audit_id}/compare/{other_id}")
async def compare_audits(audit_id: str, other_id: str, service: Service) -> dict[str, Any]:
    """What changed from ``other_id`` (the earlier audit) to ``audit_id``."""
    new = await get_or_404(service, audit_id)
    old = await get_or_404(service, other_id)
    require_terminal(new)
    require_terminal(old)
    if _site_key(old.target_url) != _site_key(new.target_url):
        raise ApiError("not-same-site", 422, "The two audits are not of the same site.")
    return compare(old, new).model_dump(mode="json")


@router.get("/sites/{host}/audits")
async def site_audits(
    host: Annotated[str, Path(pattern=r"^[A-Za-z0-9.\-]{1,253}$")],
    service: Service,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> dict[str, Any]:
    rows = await service.list_site_audits(host, limit)
    return {"host": host.lower(), "data": [r.model_dump(mode="json") for r in rows]}


def _site_key(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host
