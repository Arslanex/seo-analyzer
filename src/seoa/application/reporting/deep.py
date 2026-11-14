"""Deep-analysis report sections (belge 11): links, performance, images, indexability, visibility.

Pure functions: AuditRecord -> schema sections. Every section is either *measured* (with data) or
*not measured* (with a reason); a table is never emitted empty. Every string that came from a page or
from an external source goes through ``clean_text`` (and is autoescaped again by the template).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Literal

from seoa.application.reporting import schema as s
from seoa.domain import AuditRecord, FieldMetric, LinkRecord
from seoa.domain.i18n import CATALOG, reason_text, t
from seoa.domain.rules import registry
from seoa.domain.text import clean_text

# Row caps: the JSON report stays a sensible size; the API serves everything that was stored.
LINK_ROWS = 200
BROKEN_ROWS = 200
REDIRECT_ROWS = 200
DOMAINS = 15
PAGE_ROWS = 200
PERF_ROWS = 50
IMAGE_ROWS = 100
INDEX_ROWS = 200
LIST_CAP = 30
ORPHAN_ROWS = 100

# Core Web Vitals (web.dev) + Lighthouse guidance. (good <=, poor >). INP is field-only, not here.
THRESHOLDS: dict[str, tuple[float, float]] = {
    "lcp_ms": (2500, 4000),
    "cls": (0.1, 0.25),
    "fcp_ms": (1800, 3000),
    "ttfb_ms": (800, 1800),
    "tbt_ms": (200, 600),
}


def rate(metric: str, value: float | None) -> str | None:
    if value is None or metric not in THRESHOLDS:
        return None
    good, poor = THRESHOLDS[metric]
    return "good" if value <= good else ("needs-improvement" if value <= poor else "poor")


def _c(text: object, limit: int = 300) -> str:
    return clean_text(str(text))[:limit]


def _code(error: str | None) -> str | None:
    if not error or not error.strip():
        return None
    return error.split(":")[0].strip().split()[0]


def _kb(n: int | float | None) -> float:
    return round((n or 0) / 1024, 1)


def not_measured(lang: str, reason: str) -> dict[str, Any]:
    return {
        "status": "not_measured",
        "not_measured_reason": reason,
        "not_measured_text": reason_text(lang, reason),
    }


# --------------------------------------------------------------------------- scope note


# --------------------------------------------------------------------------- category checks


def check_rows(category_checks: Iterable[Any], lang: str) -> list[s.CheckRow]:
    rows: list[s.CheckRow] = []
    for ck in list(category_checks)[:120]:
        key = f"finding.{ck.check_id}"
        text = registry.message(key, lang) if key in registry.MESSAGES else ck.check_id
        rows.append(
            s.CheckRow(
                check_id=ck.check_id,
                message=_c(text),
                severity=ck.severity,
                weight=ck.weight,
                pass_ratio=max(0.0, min(1.0, ck.pass_ratio)),
                pages_affected=ck.pages_affected,
                pages_assessed=max(1, ck.pages_assessed),
                status=ck.status,
            )
        )
    return rows


# --------------------------------------------------------------------------- links


def _link_state(lk: LinkRecord) -> str:
    """Same verdicts as the analysis (a site that blocks bots, e.g. LinkedIn's 999, is not "broken")."""
    from seoa.application.analysis.links.graph import classify

    verdict = classify(lk.target_status, lk.error)
    if verdict == "broken":
        return "broken"
    if verdict == "blocked":
        return "blocked"
    if verdict in ("rejected", "unchecked"):
        return "unchecked"
    if lk.redirect_hops > 0 or (lk.target_status is not None and 300 <= lk.target_status < 400):
        return "redirect"
    return "ok" if lk.checked else "unchecked"


def _link_error_text(lang: str, err: str | None) -> str | None:
    if not err:
        return None
    code = _code(err) or "unknown"
    key = f"link.err.{code}"
    return t(lang, key) if key in CATALOG["en"] else t(lang, "link.err.unknown")


def _link_row(lk: LinkRecord, lang: str) -> s.LinkRow:
    return s.LinkRow(
        source_url=_c(lk.source_url, 2048),
        target_url=_c(lk.target_url, 2048),
        anchor=_c(lk.anchor, 120),
        kind=lk.kind,
        rel=[_c(r, 20) for r in lk.rel[:5]],
        zone=lk.zone,
        target_status=lk.target_status,
        final_url=_c(lk.final_url, 2048) if lk.final_url else None,
        redirect_hops=lk.redirect_hops,
        error=_code(lk.error),
        error_text=_link_error_text(lang, lk.error),
        state=_link_state(lk),  # type: ignore[arg-type]
    )


def links_section(rec: AuditRecord, lang: str) -> s.LinksSection:
    ls = rec.links
    if ls is None:
        return s.LinksSection(**not_measured(lang, "analysis-not-run"))
    rows = [_link_row(lk, lang) for lk in ls.links]
    broken_all = [r for r in rows if r.state == "broken"]
    redirect_all = [r for r in rows if r.state == "redirect"]
    pages_all = sorted(ls.pages, key=lambda p: (p.depth is None, p.depth or 0, p.url))
    pages = [
        s.LinkPageRow(
            url=_c(p.url, 2048),
            inlinks=p.inlinks,
            outlinks_internal=p.outlinks_internal,
            outlinks_external=p.outlinks_external,
            depth=p.depth,
            in_sitemap=p.in_sitemap,
        )
        for p in pages_all[:PAGE_ROWS]
    ]
    domains = [
        s.DomainCount(domain=_c(d.get("domain", ""), 253), count=int(d.get("count", 0)))
        for d in sorted(ls.external_domains, key=lambda d: -int(d.get("count", 0)))[:DOMAINS]
        if d.get("domain")
    ]
    summary = {
        "internal_total": ls.internal_total,
        "external_total": ls.external_total,
        "internal_unique": ls.internal_unique,
        "external_unique": ls.external_unique,
        "checked": ls.checked,
        "skipped": ls.skipped,
        "broken": ls.broken,
        "redirecting": ls.redirecting,
        "nofollow": ls.nofollow,
        "max_depth": ls.max_depth,
        "orphans": len(ls.orphans),
    }
    total = max(len(rows), ls.internal_total + ls.external_total)
    shown = rows[:LINK_ROWS]
    return s.LinksSection(
        status="measured",
        summary=summary,
        broken=broken_all[:BROKEN_ROWS],
        redirecting=redirect_all[:REDIRECT_ROWS],
        external_domains=domains,
        pages=pages,
        pages_total=len(ls.pages),
        orphans=[_c(u, 2048) for u in ls.orphans[:ORPHAN_ROWS]],
        links=shown,
        links_total=total,
        truncated=(
            ls.truncated
            or total > len(shown)
            or len(broken_all) > BROKEN_ROWS
            or len(redirect_all) > REDIRECT_ROWS
            or len(ls.pages) > PAGE_ROWS
        ),
    )


# --------------------------------------------------------------------------- performance + images


def _perf_error(lang: str, error: str | None) -> tuple[str | None, str | None]:
    code = _code(error)
    return code, (reason_text(lang, code) if code else None)


def performance_section(rec: AuditRecord, lang: str) -> s.PerfSection:
    if not rec.perf:
        return s.PerfSection(**not_measured(lang, "lab-unavailable"))
    rows: list[s.PerfRow] = []
    ordered = sorted(rec.perf, key=lambda p: (p.url, p.device != "desktop"))
    ok = [p for p in ordered if p.error is None]
    for p in ordered[:PERF_ROWS]:
        code, text = _perf_error(lang, p.error)
        by_type = [
            s.TypeShare(type=_c(k, 20), count=int(v.get("count", 0)), kb=_kb(v.get("bytes", 0)))
            for k, v in sorted(p.by_type.items(), key=lambda kv: -int(kv[1].get("bytes", 0)))
        ]
        mobile = None
        if p.mobile is not None:
            mobile = {
                _c(k, 40): (v if isinstance(v, (bool, int, float)) else _c(v, 80))
                for k, v in p.mobile.items()
            }
        metrics = {
            "ttfb_ms": p.ttfb_ms,
            "fcp_ms": p.fcp_ms,
            "lcp_ms": p.lcp_ms,
            "cls": p.cls,
            "tbt_ms": p.tbt_ms,
        }
        rows.append(
            s.PerfRow(
                url=_c(p.url, 2048),
                device=p.device,
                ttfb_ms=p.ttfb_ms,
                fcp_ms=p.fcp_ms,
                lcp_ms=p.lcp_ms,
                cls=p.cls,
                tbt_ms=p.tbt_ms,
                dom_content_loaded_ms=p.dom_content_loaded_ms,
                load_ms=p.load_ms,
                ratings={k: r for k, v in metrics.items() if (r := rate(k, v)) is not None},
                requests=p.total_requests,
                total_kb=_kb(p.total_bytes),
                html_kb=_kb(p.html_bytes),
                render_blocking=p.render_blocking,
                by_type=by_type,
                mobile=mobile,
                error=code,
                error_text=text,
            )
        )
    if not ok:
        code = next((c for c in (_code(p.error) for p in ordered) if c), "lab-unavailable")
        return s.PerfSection(**not_measured(lang, code))

    basis = [p for p in ok if p.device == "desktop"] or ok
    agg: dict[str, list[int]] = {}
    hosts: dict[str, list[int]] = {}
    for p in basis:
        for k, v in p.by_type.items():
            cur = agg.setdefault(_c(k, 20), [0, 0])
            cur[0] += int(v.get("count", 0))
            cur[1] += int(v.get("bytes", 0))
        for tp in p.third_party:
            host = _c(tp.get("host", ""), 253)
            if not host:
                continue
            cur = hosts.setdefault(host, [0, 0])
            cur[0] += int(tp.get("requests", 0))
            cur[1] += int(tp.get("bytes", 0))
    unc = list(dict.fromkeys(_c(u, 2048) for p in ok for u in p.uncompressed_text))
    nocache = list(dict.fromkeys(_c(u, 2048) for p in ok for u in p.no_cache_static))
    return s.PerfSection(
        status="measured",
        rows=rows,
        rows_total=len(ordered),
        by_type=[
            s.TypeShare(type=k, count=v[0], kb=_kb(v[1]))
            for k, v in sorted(agg.items(), key=lambda kv: -kv[1][1])
        ],
        third_party=[
            s.HostShare(host=h, requests=v[0], kb=_kb(v[1]))
            for h, v in sorted(hosts.items(), key=lambda kv: -kv[1][1])[:DOMAINS]
        ],
        uncompressed=unc[:LIST_CAP],
        no_cache=nocache[:LIST_CAP],
        lab_note=t(lang, "perf.lab"),
        truncated=len(ordered) > PERF_ROWS or len(unc) > LIST_CAP or len(nocache) > LIST_CAP,
    )


def _issue_text(check_id: str, lang: str) -> str:
    key = f"finding.{check_id}"
    return _c(registry.message(key, lang) if key in registry.MESSAGES else check_id, 200)


def images_section(rec: AuditRecord, lang: str) -> s.ImagesSection:
    ok = [p for p in rec.perf if p.error is None]
    if not ok:
        code = next((c for c in (_code(p.error) for p in rec.perf) if c), "lab-unavailable")
        return s.ImagesSection(**not_measured(lang, code))
    basis = [p for p in ok if p.device == "desktop"] or ok
    seen: dict[tuple[str, str], Any] = {}
    for p in basis:
        for im in p.images:
            seen.setdefault((im.page_url, im.src), im)
    imgs = sorted(seen.values(), key=lambda i: -(i.bytes or 0))

    def size(w: int | None, h: int | None) -> str | None:
        return f"{w}x{h}" if w and h else None

    rows = [
        s.ImageRow(
            page_url=_c(i.page_url, 2048),
            src=_c(i.src, 2048),
            format=_c(i.served_format, 12) if i.served_format else None,
            kb=_kb(i.bytes) if i.bytes is not None else None,
            natural=size(i.natural_w, i.natural_h),
            displayed=size(i.displayed_w, i.displayed_h),
            category=i.category,
            above_fold=i.above_fold,
            lazy=i.lazy,
            has_alt=i.has_alt,
            issues=[_c(x, 60) for x in i.issues[:8]],
            issue_texts=[_issue_text(x, lang) for x in i.issues[:8]],
        )
        for i in imgs[:IMAGE_ROWS]
    ]
    fmt: dict[str, list[int]] = {}
    for i in imgs:
        cur = fmt.setdefault(_c(i.served_format or "unknown", 12), [0, 0])
        cur[0] += 1
        cur[1] += int(i.bytes or 0)
    return s.ImagesSection(
        status="measured",
        rows=rows,
        rows_total=len(imgs),
        total_kb=_kb(sum(int(i.bytes or 0) for i in imgs)),
        by_format=[
            s.FormatShare(format=k, count=v[0], kb=_kb(v[1]))
            for k, v in sorted(fmt.items(), key=lambda kv: -kv[1][1])
        ],
        thresholds_note=t(lang, "img.thresholds"),
        truncated=len(imgs) > IMAGE_ROWS,
    )


# --------------------------------------------------------------------------- indexability


def _reason_text(lang: str, code: str) -> str:
    key = f"idx.reason.{code}"
    return t(lang, key) if key in CATALOG["en"] else _c(code, 60)


def indexability_section(rec: AuditRecord, lang: str) -> s.IndexabilitySection:
    if not rec.indexability:
        return s.IndexabilitySection(**not_measured(lang, "analysis-not-run"))
    rows = [
        s.IndexRow(
            url=_c(r.url, 2048),
            status=r.status,
            indexable=r.indexable,
            reasons=[_c(x, 60) for x in r.reasons[:8]],
            reason_texts=[_reason_text(lang, x) for x in r.reasons[:8]],
            canonical=_c(r.canonical, 2048) if r.canonical else None,
            in_sitemap=r.in_sitemap,
            inlinks=r.inlinks,
            depth=r.depth,
        )
        for r in sorted(rec.indexability, key=lambda r: (r.indexable, r.url))[:INDEX_ROWS]
    ]
    blocked = sum(1 for r in rec.indexability if not r.indexable)
    return s.IndexabilitySection(
        status="measured",
        rows=rows,
        rows_total=len(rec.indexability),
        indexable_count=len(rec.indexability) - blocked,
        blocked_count=blocked,
        note=t(lang, "idx.note"),
        truncated=len(rec.indexability) > INDEX_ROWS,
    )


# --------------------------------------------------------------------------- visibility


def _vis_error(lang: str, err: object) -> str:
    code = _code(str(err)) or "unknown"
    key = f"vis.err.{code}"
    if key in CATALOG["en"]:
        return t(lang, key)
    return t(lang, "vis.err.unknown", code=_c(code, 40))


def _day(value: object) -> str:
    return _c(value, 40)[:10]


def visibility_section(rec: AuditRecord, lang: str) -> s.VisibilitySection:
    v = rec.visibility
    if v is None:
        return s.VisibilitySection(**not_measured(lang, "visibility-unavailable"))
    items: list[s.VisItem] = []

    r = v.rdap or {}
    if r.get("error") or not (r.get("created") or r.get("age_days") is not None):
        items.append(
            s.VisItem(
                id="rdap",
                label=t(lang, "vis.rdap"),
                available=False,
                error_text=_vis_error(lang, r.get("error") or "unknown"),
            )
        )
    else:
        detail = (
            t(lang, "vis.registrar", name=_c(r["registrar"], 80)) if r.get("registrar") else None
        )
        items.append(
            s.VisItem(
                id="rdap",
                label=t(lang, "vis.rdap"),
                value=t(
                    lang,
                    "vis.created",
                    date=_day(r.get("created") or "—"),
                    days=r.get("age_days", "—"),
                ),
                detail=detail,
            )
        )

    w = v.wayback or {}
    if w.get("error") or not (w.get("first_capture") or w.get("captures")):
        items.append(
            s.VisItem(
                id="wayback",
                label=t(lang, "vis.wayback"),
                available=False,
                error_text=_vis_error(lang, w.get("error") or "no-captures"),
            )
        )
    else:
        items.append(
            s.VisItem(
                id="wayback",
                label=t(lang, "vis.wayback"),
                value=t(
                    lang,
                    "vis.wb.first",
                    first=_day(w.get("first_capture") or "—"),
                    last=_day(w.get("last_capture") or "—"),
                ),
                detail=t(lang, "vis.wb.count", n=w["captures"])
                if w.get("captures") is not None
                else None,
            )
        )

    cc = v.common_crawl or {}
    if cc.get("error") or cc.get("present") is None:
        items.append(
            s.VisItem(
                id="common_crawl",
                label=t(lang, "vis.common_crawl"),
                available=False,
                error_text=_vis_error(lang, cc.get("error") or "unknown"),
            )
        )
    else:
        coll = _c(cc.get("collection") or "—", 40)
        items.append(
            s.VisItem(
                id="common_crawl",
                label=t(lang, "vis.common_crawl"),
                value=(
                    t(lang, "vis.cc.present", collection=coll, pages=cc.get("pages_seen", "—"))
                    if cc["present"]
                    else t(lang, "vis.cc.absent", collection=coll)
                ),
            )
        )

    if rec.gsc is not None and rec.gsc.status == "ok":
        items.append(
            s.VisItem(
                id="search_console",
                label=t(lang, "vis.search_console"),
                value=t(lang, "vis.gsc.on"),
                detail=t(lang, "vis.gsc.see"),
            )
        )
    else:
        items.append(
            s.VisItem(
                id="search_console",
                label=t(lang, "vis.search_console"),
                value=t(lang, "vis.gsc.off"),
                detail=t(lang, "vis.gsc.how"),
                available=False,
            )
        )
    notes = []
    for code in v.notes[:12]:
        if code == "gsc-not-connected":  # shown by the Search Console row, from the real state
            continue
        key = f"vis.note.{_c(code, 60)}"
        notes.append(
            t(lang, key) if key in CATALOG["en"] else t(lang, "vis.note.unknown", code=_c(code, 60))
        )
    return s.VisibilitySection(
        status="measured",
        domain=_c(v.domain, 253),
        items=items,
        notes=notes,
        disclaimer=t(lang, "vis.disclaimer"),
    )


# --------------------------------------------------------------------------- Search Console

GSC_ROWS = 20
GSC_INSPECTIONS = 200
GSC_SITEMAPS = 50

_GSC_REASONS = {
    "not-connected": "gsc-not-connected",
    "not-configured": "gsc-not-configured",
    "property-not-found": "gsc-property-not-found",
    "no-permission": "gsc-no-permission",
    "error": "gsc-error",
}


def _gsc_row(r: Any) -> s.GscMetricRow:
    return s.GscMetricRow(
        key=_c(r.key, 2048),
        clicks=int(r.clicks),
        impressions=int(r.impressions),
        ctr_pct=round(float(r.ctr) * 100, 1),
        position=round(float(r.position), 1),
    )


def _same_canonical(a: str, b: str) -> bool:
    return a.strip().rstrip("/") == b.strip().rstrip("/")


def _inspection_row(i: Any, lang: str) -> s.GscInspectionRow:
    g, u = i.google_canonical, i.user_canonical
    code = _code(i.error)
    return s.GscInspectionRow(
        url=_c(i.url, 2048),
        indexed=i.indexed,
        coverage_state=_c(i.coverage_state, 120) if i.coverage_state else None,
        verdict=_c(i.verdict, 40) if i.verdict else None,
        google_canonical=_c(g, 2048) if g else None,
        user_canonical=_c(u, 2048) if u else None,
        canonical_mismatch=bool(g and u and not _same_canonical(g, u)),
        last_crawl=_day(i.last_crawl_time) if i.last_crawl_time else None,
        crawled_as=_c(i.crawled_as, 40) if i.crawled_as else None,
        robots_state=_c(i.robots_txt_state, 60) if i.robots_txt_state else None,
        fetch_state=_c(i.page_fetch_state, 60) if i.page_fetch_state else None,
        error=code,
        error_text=_vis_error(lang, i.error) if code else None,
    )


def gsc_section(rec: AuditRecord, lang: str) -> s.GscSection:
    g = rec.gsc
    status = g.status if g is not None else "not-connected"
    if g is None or status != "ok":
        nm = not_measured(lang, _GSC_REASONS[status])
        if status == "error" and g is not None and g.error:
            nm["not_measured_text"] = f"{nm['not_measured_text']} ({_c(_code(g.error) or '', 60)})"
        return s.GscSection(
            gsc_status=status,
            can_connect=status == "not-connected",
            account=_c(g.account, 254) if g is not None and g.account else None,
            property=_c(g.property, 2048) if g is not None and g.property else None,
            **nm,
        )
    ins = [_inspection_row(i, lang) for i in g.inspections[:GSC_INSPECTIONS]]
    return s.GscSection(
        status="measured",
        gsc_status="ok",
        account=_c(g.account, 254) if g.account else None,
        property=_c(g.property, 2048) if g.property else None,
        permission=_c(g.permission, 40) if g.permission else None,
        period_days=g.period_days,
        totals={_c(k, 20): float(v) for k, v in list(g.totals.items())[:8]},
        top_queries=[_gsc_row(r) for r in g.top_queries[:GSC_ROWS]],
        top_pages=[_gsc_row(r) for r in g.top_pages[:GSC_ROWS]],
        inspections=ins,
        inspections_total=len(g.inspections),
        indexed_count=sum(1 for i in g.inspections if i.indexed is True),
        not_indexed_count=sum(1 for i in g.inspections if i.indexed is False),
        mismatch_count=sum(1 for i in ins if i.canonical_mismatch),
        sitemaps=[
            s.GscSitemapRow(
                path=_c(m.path, 2048),
                last_submitted=_day(m.last_submitted) if m.last_submitted else None,
                last_downloaded=_day(m.last_downloaded) if m.last_downloaded else None,
                pending=m.is_pending,
                errors=m.errors,
                warnings=m.warnings,
            )
            for m in g.sitemaps[:GSC_SITEMAPS]
        ],
        note=t(lang, "gsc.note"),
        delay_note=t(lang, "gsc.delay", days=g.period_days),
        truncated=len(g.inspections) > GSC_INSPECTIONS
        or len(g.top_queries) > GSC_ROWS
        or len(g.top_pages) > GSC_ROWS
        or len(g.sitemaps) > GSC_SITEMAPS,
    )


# --------------------------------------------------------------------------- field data (CrUX)

# Same Core Web Vitals thresholds as ``integrations.psi.THRESHOLDS`` (+ web.dev values for FCP/TTFB).
FIELD_THRESHOLDS: dict[str, tuple[float, float]] = {
    "lcp": (2500.0, 4000.0),
    "inp": (200.0, 500.0),
    "cls": (0.1, 0.25),
    "fcp": (1800.0, 3000.0),
    "ttfb": (800.0, 1800.0),
}
_FIELD_ORDER = ("lcp", "inp", "cls", "fcp", "ttfb")
_FIELD_REASONS = {"no-data": "field-no-data", "no-api-key": "field-no-api-key"}


def _field_rating(
    metric: str, p75: float | None
) -> Literal["good", "needs-improvement", "poor"] | None:
    if p75 is None or metric not in FIELD_THRESHOLDS:
        return None
    good, poor = FIELD_THRESHOLDS[metric]
    return "good" if p75 <= good else ("needs-improvement" if p75 <= poor else "poor")


def _pct(v: float | None) -> float | None:
    return None if v is None else round(max(0.0, min(1.0, float(v))) * 100, 1)


def _field_value(metric: str, p75: float | None) -> str:
    if p75 is None:
        return "—"
    return f"{p75:.2f}" if metric == "cls" else f"{round(p75)} ms"


def field_section(rec: AuditRecord, lang: str) -> s.FieldSection:
    f = rec.field
    if f is None:
        return s.FieldSection(**not_measured(lang, "field-not-run"))
    if not f.metrics:
        code = _code(f.error) or "no-data"
        reason = _FIELD_REASONS.get(code, "field-error")
        nm = not_measured(lang, reason)
        if reason == "field-error" and f.error:
            nm["not_measured_text"] = f"{nm['not_measured_text']} ({_c(code, 60)})"
        return s.FieldSection(**nm)
    by: dict[str, FieldMetric] = {m.metric: m for m in f.metrics}
    rows = []
    for key in _FIELD_ORDER:
        m = by.get(key)
        if m is None:
            continue
        rows.append(
            s.FieldMetricRow(
                metric=m.metric,
                label=t(lang, f"field.m.{m.metric}"),
                p75=m.p75,
                p75_text=_field_value(m.metric, m.p75),
                rating=_field_rating(m.metric, m.p75) or m.rating,
                good_pct=_pct(m.good_share),
                needs_improvement_pct=_pct(m.needs_improvement_share),
                poor_pct=_pct(m.poor_share),
            )
        )
    period = f.period or {}
    return s.FieldSection(
        status="measured",
        scope=f.scope,
        form_factor=_c(f.form_factor, 20) if f.form_factor else None,
        period_first=_day(period["first"]) if period.get("first") else None,
        period_last=_day(period["last"]) if period.get("last") else None,
        metrics=rows,
        note=t(lang, "field.note"),
    )


def build_deep(rec: AuditRecord, lang: str) -> dict[str, Any]:
    return {
        "links": links_section(rec, lang),
        "performance": performance_section(rec, lang),
        "images": images_section(rec, lang),
        "indexability": indexability_section(rec, lang),
        "visibility": visibility_section(rec, lang),
        "gsc": gsc_section(rec, lang),
        "field": field_section(rec, lang),
    }
