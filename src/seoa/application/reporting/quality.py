"""Report quality gate (belge 06 s.8): FAIL blocks the report, WARN is logged and shown.

Deviation from belge 06 s.8.1 (documented): a message_key missing from the *report language*
catalog is WARN, not FAIL, as long as the English text exists. MVP robustness: a missing
translation must not hide a valid report.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

from lxml import etree
from lxml import html as lxml_html
from pydantic import ValidationError

from seoa.application.reporting import schema as s
from seoa.application.reporting.actionplan import find_cycles
from seoa.application.reporting.schema import AuditReport, Quality, QualityCheck
from seoa.domain import Severity, i18n
from seoa.domain.palette import BAND_STYLES, SEVERITY_STYLES
from seoa.domain.rules import registry

QualityResult = Quality
Status = Literal["PASS", "WARN", "FAIL"]


def _page_derived_strings(report: AuditReport) -> list[str]:
    out: list[str] = []
    for f in report.findings:
        if f.evidence:
            out.append(f.evidence.value)
        out.extend(f.urls)
    out.extend(p.url for p in report.pages)
    out.extend(p.title for p in report.pages if p.title)
    if report.synthesis:
        out.append(report.synthesis.summary)
    if report.advisory:
        for it in report.advisory.items:
            out.extend(str(q.get("quote") or "") for q in it.quotes)
            out.extend(
                str(o.get("text") or "") + str(o.get("quote") or "") for o in it.observations
            )
    for r in report.recommendations:
        out.extend(r.context)
    lk = report.links
    for row in (*lk.broken, *lk.redirecting, *lk.links):
        out.extend([row.source_url, row.target_url, row.anchor, row.final_url or ""])
    out.extend(p.url for p in lk.pages)
    out.extend(lk.orphans)
    out.extend(d.domain for d in lk.external_domains)
    for pr in report.performance.rows:
        out.append(pr.url)
    out.extend(report.performance.uncompressed)
    out.extend(report.performance.no_cache)
    out.extend(h.host for h in report.performance.third_party)
    for im in report.images.rows:
        out.extend([im.page_url, im.src, im.format or ""])
    for ix in report.indexability.rows:
        out.extend([ix.url, ix.canonical or ""])
    out.extend(it.value or "" for it in report.visibility.items)
    out.extend(it.detail or "" for it in report.visibility.items)
    gs = report.gsc
    for g in (*gs.top_queries, *gs.top_pages):
        out.append(g.key)
    for gi in gs.inspections:
        out.extend([gi.url, gi.google_canonical or "", gi.user_canonical or ""])
    out.extend(m.path for m in gs.sitemaps)
    for col in report.competitors.columns:
        out.extend([col.host, col.url, *col.values])
    out.extend(k.label for k in report.competitors.skipped)
    for hf in (*report.history.new_findings, *report.history.resolved_findings):
        out.extend([hf.title, hf.url or ""])
    out.extend(r.url for r in report.history.rows)
    return [s for s in out if s]


def _check_contract(report: AuditReport, add: _Adder) -> None:
    ov = report.scores.overall
    if ov.gate and ov.value is not None and ov.value > ov.gate.cap:
        add("contract.gate", "FAIL", "score exceeds the gate cap")
    if ov.display == "insufficient_data" and ov.value is not None:
        add("contract.insufficient", "FAIL", "insufficient data but a number is shown")
    if ov.coverage_pct < 60 and ov.value is not None:
        add("contract.coverage60", "FAIL", f"coverage {ov.coverage_pct} < 60 but a number is shown")
    if report.advisory is not None and report.advisory.counts_toward_overall is not False:
        add("contract.advisory", "FAIL", "advisory must not count toward the overall score")
    measured = [c for c in report.scores.categories if c.status != "not_measured"]
    for c in report.scores.categories:
        if c.status == "not_measured" and c.score is not None:
            add("contract.category", "FAIL", f"{c.id.value}: not_measured with a score")
    if measured and abs(sum(c.weight_effective or 0 for c in measured) - 100) > 1.0:
        add("contract.weights", "WARN", "effective weights do not sum to 100")
    for f in report.findings:
        if f.layer.value == "C" and f.severity is Severity.CRITICAL:
            add("contract.layerC", "FAIL", f"{f.check_id}: Layer C cannot be Critical")
        if not f.message.strip():
            add("contract.message", "FAIL", f"{f.check_id}: empty message")
    for c in report.scores.categories:
        if c.status != "not_measured" and c.checks_total != c.checks_passed + c.checks_failed:
            add("contract.checks", "FAIL", f"{c.id.value}: passed + failed != total")
        if c.status == "not_measured" and c.checks:
            add("contract.checks", "FAIL", f"{c.id.value}: not measured but lists checks")
    _check_deep(report, add)


def _suite_sections(report: AuditReport) -> dict[str, tuple[s.SectionState, int, int]]:
    tech, setup, prev = report.techstack, report.site_setup, report.previews
    shots, read, hl = report.screenshots, report.readability, report.hreflang
    sug, ag = report.schema_suggestions, report.agentic
    hist, comp = report.history, report.competitors
    n_tech = sum(len(g.items) for g in tech.groups)
    return {
        "techstack": (tech, n_tech, max(tech.total, n_tech)),
        "site_setup": (
            setup,
            len(setup.redirects) + len(setup.files),
            len(setup.redirects) + len(setup.files),
        ),
        "previews": (
            prev,
            len(prev.serp) + len(prev.social) + len(prev.social_image),
            len(prev.serp) + len(prev.social) + len(prev.social_image),
        ),
        "screenshots": (shots, len(shots.shots), len(shots.shots)),
        "readability": (
            read,
            len(read.scores) + len(read.terms),
            len(read.scores) + len(read.terms),
        ),
        "hreflang": (hl, len(hl.rows), hl.rows_total),
        "schema_suggestions": (sug, len(sug.items), sug.items_total),
        "agentic": (ag, len(ag.rows), len(ag.rows)),
        "history": (hist, len(hist.rows), hist.rows_total),
        "competitors": (comp, len(comp.columns), len(comp.columns)),
        "local": (
            report.local,
            len(report.local.phones) + len(report.local.addresses) + len(report.local.issues),
            len(report.local.phones) + len(report.local.addresses) + len(report.local.issues),
        ),
        "sitemap_gen": (
            report.sitemap_gen,
            report.sitemap_gen.urls_shown,
            report.sitemap_gen.urls_total,
        ),
        "authority": (report.authority, len(report.authority.items), len(report.authority.items)),
        "rankings": (
            report.rankings,
            len(report.rankings.rows)
            + len(report.rankings.opportunities)
            + len(report.rankings.low_ctr),
            len(report.rankings.rows)
            + len(report.rankings.opportunities)
            + len(report.rankings.low_ctr),
        ),
    }


def _deep_sections(report: AuditReport) -> dict[str, tuple[s.SectionState, int, int]]:
    """name -> (section, rows shown, rows total)."""
    lk, pf, im, ix = report.links, report.performance, report.images, report.indexability
    gs, fd = report.gsc, report.field
    return {
        "links": (lk, len(lk.links) + len(lk.pages), lk.links_total + lk.pages_total),
        "performance": (pf, len(pf.rows), pf.rows_total),
        "images": (im, len(im.rows), im.rows_total),
        "indexability": (ix, len(ix.rows), ix.rows_total),
        "visibility": (
            report.visibility,
            len(report.visibility.items),
            len(report.visibility.items),
        ),
        "gsc": (
            gs,
            len(gs.top_queries) + len(gs.top_pages) + len(gs.inspections) + len(gs.sitemaps),
            gs.inspections_total + len(gs.top_queries) + len(gs.top_pages) + len(gs.sitemaps),
        ),
        "field": (fd, len(fd.metrics), len(fd.metrics)),
        **_suite_sections(report),
    }


_HTML_SECTIONS = (
    "links",
    "performance",
    "images",
    "indexability",
    "visibility",
    "gsc",
    "field",
    "glance",
    "techstack",
    "setup",
    "previews",
    "screenshots",
    "readability",
    "hreflang",
    "schemasug",
    "agentic",
    "history",
    "competitors",
    "local",
    "sitemapgen",
    "authority",
    "rankings",
)


def _check_deep(report: AuditReport, add: _Adder) -> None:
    """A deep section is measured-with-data or not-measured-with-a-reason; never an empty table."""
    for name, (sec, shown, total) in _deep_sections(report).items():
        if sec.status == "not_measured":
            if shown:
                add(f"deep.{name}", "FAIL", "not measured but carries rows")
            if not sec.not_measured_reason or not (sec.not_measured_text or "").strip():
                add(f"deep.{name}", "FAIL", "not measured without a reason")
        elif shown > total:
            add(f"deep.{name}", "FAIL", "more rows shown than the total")
    if report.visibility.counts_toward_overall is not False:
        add("deep.visibility", "FAIL", "visibility signals must not count toward the score")
    if report.images.rows_total < len(report.images.rows):
        add("deep.images", "FAIL", "image rows exceed the total")


def _check_refs(report: AuditReport, add: _Adder) -> None:
    fids = {f.id for f in report.findings}
    rids = {r.id for r in report.recommendations}
    bad = [r.id for r in report.recommendations if not set(r.finding_ids) <= fids]
    bad += [f.id for f in report.findings if not set(f.recommendation_ids) <= rids]
    bad += [r.id for r in report.recommendations if not set(r.depends_on) <= rids]
    if bad:
        add("refs.resolve", "FAIL", f"unresolved references: {sorted(set(bad))[:5]}")
    placed = [it.recommendation_id for ph in report.action_plan.phases for it in ph.items]
    if sorted(placed) != sorted(rids):
        add("refs.plan", "FAIL", "every recommendation must appear in exactly one phase")
    if len(report.action_plan.phases) != 4:
        add("refs.phases", "FAIL", "the plan must have 4 phases")
    cyc = find_cycles(report.recommendations)
    if cyc:
        add("refs.cycle", "FAIL", f"dependency cycle: {cyc[:5]}")


def _check_text(report: AuditReport, lang: str, add: _Adder) -> None:
    if i18n.missing_keys():
        add("text.catalog", "FAIL", f"TR/EN UI catalogs differ: {sorted(i18n.missing_keys())[:5]}")
    gaps = []
    for f in report.findings:
        entry = registry.MESSAGES.get(f.message_key)
        if entry is None or not entry.get(lang):
            gaps.append(f.message_key)
    if gaps:
        add(
            "text.translation",
            "WARN",
            f"no {lang} text for: {sorted(set(gaps))[:5]} (English fallback used)",
        )


def _check_severity_map(add: _Adder) -> None:
    for mode in ("light", "dark"):
        fgs = {SEVERITY_STYLES[s][mode][0] for s in SEVERITY_STYLES}
        if len(fgs) != len(SEVERITY_STYLES):
            add("a11y.severity_colors", "FAIL", f"severity colours are not distinct ({mode})")
    if len({v["shape"] for v in SEVERITY_STYLES.values()}) != len(SEVERITY_STYLES):
        add("a11y.severity_shapes", "FAIL", "severity shapes are not distinct")
    if len(set(BAND_STYLES.values())) != len(BAND_STYLES):
        add("a11y.band_colors", "WARN", "score band colours are not distinct")


class _Adder:
    def __init__(self) -> None:
        self.checks: list[QualityCheck] = []

    def __call__(self, check_id: str, status: Status, detail: str = "") -> None:
        self.checks.append(QualityCheck(id=check_id, status=status, detail=detail))


def _check_html(
    report: AuditReport, doc: str, lang: str, sentinels: Iterable[str], add: _Adder
) -> None:
    try:
        root = lxml_html.fromstring(doc)
    except (etree.ParserError, ValueError) as exc:
        add("html.parse", "FAIL", str(exc))
        return
    if root.get("lang") != lang:
        add("html.lang", "WARN", f"html lang={root.get('lang')!r}, expected {lang!r}")
    if not (root.findtext(".//title") or "").strip():
        add("html.title", "WARN", "missing <title>")

    # escaping: raw page-derived markup must never appear verbatim
    raw_hits = [s for s in _page_derived_strings(report) if ("<" in s or ">" in s) and s in doc]
    raw_hits += [s for s in sentinels if s and s in doc]
    if raw_hits:
        add(
            "html.escaping",
            "FAIL",
            f"unescaped page-derived markup in output: {raw_hits[0][:60]!r}",
        )
    inline_scripts = [s for s in root.iter("script") if not s.get("src")]
    if inline_scripts:
        add("html.inline_script", "FAIL", f"{len(inline_scripts)} inline <script> element(s)")
    handlers = [
        str(a)
        for el in root.iter()
        if isinstance(el.tag, str)
        for a in el.attrib
        if str(a).lower().startswith("on")
    ]
    if handlers:
        add("html.event_handlers", "FAIL", f"event-handler attributes present: {handlers[:3]}")
    js_links = [
        el
        for el in root.iter()
        if isinstance(el.tag, str)
        and (el.get("href") or "").lower().startswith(("javascript:", "data:"))
    ]
    if js_links:
        add("html.js_links", "FAIL", "javascript:/data: links present")

    empties = [
        el.tag
        for el in root.iter()
        if isinstance(el.tag, str) and (el.get("href") == "" or el.get("src") == "")
    ]
    if empties:
        add("html.empty_refs", "WARN", f"empty href/src on {empties[:3]}")
    ids = [el.get("id") for el in root.iter() if isinstance(el.tag, str) and el.get("id")]
    dup = sorted({i for i in ids if i and ids.count(i) > 1})
    if dup:
        add("html.duplicate_ids", "WARN", f"duplicate ids: {dup[:5]}")
    levels = [
        int(el.tag[1])
        for el in root.iter()
        if isinstance(el.tag, str) and len(el.tag) == 2 and el.tag[0] == "h" and el.tag[1].isdigit()
    ]
    if any(b - a > 1 for a, b in zip(levels, levels[1:], strict=False)) or (
        levels and levels[0] != 1
    ):
        add("html.headings", "WARN", "heading hierarchy skips a level")
    for i, sec in enumerate(root.iter("section")):
        if len("".join(str(x) for x in sec.itertext()).strip()) < 20:
            add("html.empty_section", "WARN", f"section #{i} has almost no content")
    for tbl in root.iter("table"):
        if not tbl.xpath(".//th"):
            add("html.table_headers", "WARN", "table without header cells")
            break
    if not root.xpath("//main"):
        add("html.landmarks", "WARN", "no <main> landmark")
    if report.audit.status.value != "failed":
        for sid in _HTML_SECTIONS:
            if not root.xpath(f"//section[@id='sec-{sid}']"):
                add("html.sections", "FAIL", f"deep section '{sid}' is missing from the page")
        if not root.xpath("//*[@id='scope-note']"):
            add("html.scope_note", "FAIL", "the 'what this score does not measure' box is missing")


def check_report(
    report: AuditReport,
    html: str | None = None,
    *,
    lang: str | None = None,
    sentinels: Iterable[str] = (),
) -> Quality:
    lang = i18n.norm_lang(lang or report.audit.locale)
    add = _Adder()
    try:
        AuditReport.model_validate(report.model_dump(mode="json"))
    except ValidationError as exc:
        add("schema", "FAIL", str(exc.errors()[0])[:200])
    else:
        add("schema", "PASS")
    _check_contract(report, add)
    _check_refs(report, add)
    _check_text(report, lang, add)
    _check_severity_map(add)
    if html is not None:
        _check_html(report, html, lang, sentinels, add)
    statuses = {c.status for c in add.checks}
    overall: Status = "FAIL" if "FAIL" in statuses else "WARN" if "WARN" in statuses else "PASS"
    return Quality(status=overall, checks=[c for c in add.checks if c.status != "PASS"] or [])
