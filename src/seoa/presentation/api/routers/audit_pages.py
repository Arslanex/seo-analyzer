"""Pages of one audit: progress, overview, analysis, search, rivals, plan, history and chat."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import (
    HTMLResponse,
    RedirectResponse,
    Response,
)

from seoa.application.reporting.schema import AuditReport
from seoa.domain import AuditRecord, Category, Severity
from seoa.domain.i18n import t as tr
from seoa.presentation.api.deps import Service, pick_lang
from seoa.presentation.api.errors import ApiError
from seoa.presentation.api.support import TERMINAL, history_for, report_for
from seoa.presentation.api.web_context import (
    app_ctx,
    ordered_categories,
    overview_stats,
)
from seoa.presentation.web.html import render_report_html, render_template

router = APIRouter()


# the 13 pipeline stages, grouped into the 8 steps the progress screen shows:
# (id, stages, percent at which the step starts, number of messages)
STAGE_GROUPS: list[tuple[str, list[str], int, int]] = [
    ("validate", ["validate"], 0, 2),
    ("entry", ["fetch_entry", "robots"], 8, 2),
    ("discover", ["discovery", "sample"], 18, 2),
    ("fetch", ["fetch_pages", "render"], 32, 2),
    ("checks", ["measure", "analyze"], 52, 3),
    ("score", ["score"], 68, 2),
    ("ai", ["advise", "synthesize"], 80, 2),
    ("report", ["report"], 92, 1),
]


STAGES = [
    "validate",
    "fetch_entry",
    "robots",
    "discovery",
    "sample",
    "fetch_pages",
    "render",
    "measure",
    "analyze",
    "score",
    "advise",
    "synthesize",
    "report",
]


@router.get("/audits/{audit_id}", response_model=None)
async def audit_page(
    request: Request, audit_id: str, service: Service, lang: str | None = None
) -> Response:
    lg = pick_lang(request, lang)
    rec = await service.get_audit(audit_id)
    if rec is None:
        raise ApiError("not-found", 404, "No such audit.")
    if rec.status in TERMINAL:
        report, _ = report_for(rec, lg, await history_for(service, rec))
        html = render_template(
            "app_overview.html",
            lg,
            title=f"{tr(lg, 'ov.title')} · {report.audit.requested_url}",
            page="overview",
            report=report,
            cats=ordered_categories(report),
            stats=overview_stats(report, lg),
            **await app_ctx(request, lg, active="overview", audit=rec),
        )
        return HTMLResponse(html)
    html = render_template(
        "audit.html",
        lg,
        title="SEO Analyzer",
        page="progress",
        audit_id=rec.id,
        audit_url=rec.target_url,
        audit_mode=rec.mode.value,
        stages=STAGES,
        groups=[
            {
                "id": gid,
                "stages": stages,
                "start": start,
                "label": tr(lg, f"prog.g.{gid}"),
                "messages": [tr(lg, f"prog.m.{gid}.{i}") for i in range(1, count + 1)],
            }
            for gid, stages, start, count in STAGE_GROUPS
        ],
        **await app_ctx(request, lg, active="progress", show_side=False),
    )
    return HTMLResponse(html)


@router.get("/audits/{audit_id}/report", response_model=None)
async def report_page(
    request: Request,
    audit_id: str,
    service: Service,
    lang: str | None = None,
    severity: Annotated[Severity | None, Query()] = None,
    category: Annotated[Category | None, Query()] = None,
) -> Response:
    rec = await service.get_audit(audit_id)
    if rec is None:
        raise ApiError("not-found", 404, "No such audit.")
    lg = pick_lang(request, lang)
    if rec.status not in TERMINAL:
        return RedirectResponse(f"/audits/{audit_id}?lang={lg}", status_code=303)
    report, _ = report_for(rec, lg, await history_for(service, rec))
    html = render_report_html(
        report,
        lg,
        severity=severity.value if severity else None,
        category=category.value if category else None,
    )
    return HTMLResponse(html)


async def _finished(
    request: Request, audit_id: str, service: Service, lang: str | None
) -> tuple[AuditRecord, AuditReport, str]:
    rec = await service.get_audit(audit_id)
    if rec is None:
        raise ApiError("not-found", 404, "No such audit.")
    lg = pick_lang(request, lang)
    report, _ = report_for(rec, lg, await history_for(service, rec))
    return rec, report, lg


# the report sections each analysis tab shows under its findings (partial, section id)
TAB_DETAILS: dict[str, list[tuple[str, str]]] = {
    "technical": [
        ("_suite.html", "sec-setup"),
        ("_suite.html", "sec-techstack"),
        ("_deep.html", "sec-indexability"),
        ("_suite.html", "sec-hreflang"),
        ("_extra.html", "sec-sitemapgen"),
    ],
    "onpage": [("_suite.html", "sec-previews"), ("_suite.html", "sec-screenshots")],
    "links": [("_deep.html", "sec-links")],
    "content": [("_suite.html", "sec-readability")],
    "schema": [("_suite.html", "sec-schemasug")],
    "performance": [("_deep.html", "sec-performance"), ("_deep.html", "sec-field")],
    "ai_readiness": [("_suite.html", "sec-agentic")],
    "images": [("_deep.html", "sec-images")],
}


@router.get("/audits/{audit_id}/analysis", response_model=None)
async def analysis_page(
    request: Request,
    audit_id: str,
    service: Service,
    lang: str | None = None,
    tab: Annotated[str | None, Query(max_length=40)] = None,
) -> Response:
    rec = await service.get_audit(audit_id)
    if rec is None:
        raise ApiError("not-found", 404, "No such audit.")
    lg = pick_lang(request, lang)
    if rec.status not in TERMINAL:
        return RedirectResponse(f"/audits/{audit_id}?lang={lg}", status_code=303)
    report, _ = report_for(rec, lg, await history_for(service, rec))
    cats = ordered_categories(report)
    current = next((c for c in cats if c.id.value == tab), None)
    if current is None:  # no or unknown tab: the weakest measured category, else the first
        measured = [c for c in cats if c.status != "not_measured" and c.score is not None]
        current = min(measured, key=lambda c: float(c.score or 0)) if measured else None
        current = current or (cats[0] if cats else None)
    shown = [f for f in report.findings if current and f.category == current.id]
    read_stats: list[Any] = []
    read_terms: list[Any] = []
    rd = report.readability
    if current is not None and current.id.value == "content" and rd.status == "measured":
        keep = {
            tr(lg, f"read.m.{k}") for k in ("words", "avg_sentence_words", "long_sentence_share")
        }
        read_stats = [*rd.scores[:1], *[kv for kv in rd.scores if kv.label in keep]]
        read_terms = rd.terms[:5]
    html = render_template(
        "app_analysis.html",
        lg,
        title=f"{tr(lg, 'an.title')} · {report.audit.requested_url}",
        page="analysis",
        report=report,
        cats_ordered=cats,
        read_stats=read_stats,
        read_terms=read_terms,
        tab=current.id.value if current else "",
        cat=current,
        findings=shown,
        rec_by_id={r.id: r for r in report.recommendations},
        details=TAB_DETAILS.get(current.id.value, []) if current else [],
        interactive=True,
        is_final=True,
        max_urls=10,
        **await app_ctx(request, lg, active="analysis", audit=rec),
    )
    return HTMLResponse(html)


# pages made of existing report sections: (nav key, title key, [(partial, section id)])
SECTION_PAGES: dict[str, tuple[str, list[tuple[str, str]]]] = {
    "search": (
        "nav.search",
        [
            ("_deep.html", "sec-gsc"),
            ("_extra.html", "sec-rankings"),
            ("_deep.html", "sec-indexability"),
            ("_deep.html", "sec-visibility"),
        ],
    ),
    "rivals": (
        "nav.rivals",
        [
            ("_history.html", "sec-competitors"),
            ("_extra.html", "sec-authority"),
            ("_extra.html", "sec-local"),
        ],
    ),
    "history": ("nav.history", [("_history.html", "sec-history")]),
}


async def _section_page(
    request: Request, audit_id: str, service: Service, lang: str | None, key: str
) -> Response:
    rec = await service.get_audit(audit_id)
    if rec is None:
        raise ApiError("not-found", 404, "No such audit.")
    lg = pick_lang(request, lang)
    if rec.status not in TERMINAL:
        return RedirectResponse(f"/audits/{audit_id}?lang={lg}", status_code=303)
    report, _ = report_for(rec, lg, await history_for(service, rec))
    title_key, sections = SECTION_PAGES[key]
    html = render_template(
        "app_sections.html",
        lg,
        title=f"{tr(lg, title_key)} · {report.audit.requested_url}",
        page=key,
        report=report,
        heading=tr(lg, title_key),
        sections=sections,
        interactive=True,
        is_final=True,
        max_urls=10,
        only=None,
        **await app_ctx(request, lg, active=key, audit=rec),
    )
    return HTMLResponse(html)


@router.get("/audits/{audit_id}/search", response_model=None)
async def search_page(
    request: Request, audit_id: str, service: Service, lang: str | None = None
) -> Response:
    return await _section_page(request, audit_id, service, lang, "search")


@router.get("/audits/{audit_id}/rivals", response_model=None)
async def rivals_page(
    request: Request, audit_id: str, service: Service, lang: str | None = None
) -> Response:
    return await _section_page(request, audit_id, service, lang, "rivals")


@router.get("/audits/{audit_id}/history", response_model=None)
async def history_page(
    request: Request, audit_id: str, service: Service, lang: str | None = None
) -> Response:
    return await _section_page(request, audit_id, service, lang, "history")


@router.get("/audits/{audit_id}/plan", response_model=None)
async def plan_page(
    request: Request, audit_id: str, service: Service, lang: str | None = None
) -> Response:
    rec = await service.get_audit(audit_id)
    if rec is None:
        raise ApiError("not-found", 404, "No such audit.")
    lg = pick_lang(request, lang)
    if rec.status not in TERMINAL:
        return RedirectResponse(f"/audits/{audit_id}?lang={lg}", status_code=303)
    report, _ = report_for(rec, lg, await history_for(service, rec))
    html = render_template(
        "app_plan.html",
        lg,
        title=f"{tr(lg, 'plan.title')} · {report.audit.requested_url}",
        page="plan",
        report=report,
        rec_by_id={r.id: r for r in report.recommendations},
        **await app_ctx(request, lg, active="plan", audit=rec),
    )
    return HTMLResponse(html)


@router.get("/audits/{audit_id}/chat", response_model=None)
async def chat_page(
    request: Request,
    audit_id: str,
    service: Service,
    lang: str | None = None,
    finding: Annotated[str | None, Query(max_length=120)] = None,
    new: bool = False,
) -> Response:
    rec = await service.get_audit(audit_id)
    if rec is None:
        raise ApiError("not-found", 404, "No such audit.")
    lg = pick_lang(request, lang)
    if rec.status not in TERMINAL:
        return RedirectResponse(f"/audits/{audit_id}?lang={lg}", status_code=303)
    report, _ = report_for(rec, lg, await history_for(service, rec))
    picked = report.finding(finding) if finding else None
    html = render_template(
        "app_chat.html",
        lg,
        title=f"{tr(lg, 'chat.title')} · {report.audit.requested_url}",
        page="chat",
        report=report,
        prefill=tr(lg, "chat.about_finding", id=picked.check_id) if picked else "",
        cite_map={
            f.id: {"tab": f.category.value, "label": tr(lg, f"tab.{f.category.value}")}
            for f in report.findings
        },
        suggestions=[tr(lg, "chat.s1"), tr(lg, "chat.s2"), tr(lg, "chat.s3")],
        history=[] if new else await service.list_qa(audit_id),
        **await app_ctx(request, lg, active="chat", audit=rec),
    )
    return HTMLResponse(html)
