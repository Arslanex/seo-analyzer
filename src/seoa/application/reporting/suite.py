"""Report sections for the Phase-A analysis modules (belge 12): technology, site setup, previews,
screenshots, readability, hreflang, schema suggestions, agentic readiness, and the one-look summary.

Same contract as ``deep``: a section is *measured* (with data) or *not measured* (with a reason);
a table is never emitted empty. Everything that came from a page goes through ``clean_text``.
The module blocks arrive as JSON in ``AuditRecord.extras[kind]`` and are re-validated here.
"""

from __future__ import annotations

from typing import Any, Literal, TypeVar

from pydantic import BaseModel, ValidationError

from seoa.application.reporting import schema as s
from seoa.application.reporting.deep import not_measured
from seoa.domain import AuditRecord
from seoa.domain.i18n import CATALOG, t
from seoa.domain.text import clean_text

LIST_CAP = 30
KEYWORD_CAP = 20
HREFLANG_ROWS = 100
SCHEMA_ITEMS = 12
JSON_LD_CAP = 6000
SCREENSHOT_FILES = ("desktop.jpg", "mobile.jpg")

M = TypeVar("M", bound=BaseModel)


def _c(text: object, limit: int = 300) -> str:
    return clean_text(str(text))[:limit]


def _label(lang: str, prefix: str, code: str) -> str:
    """Translated label for a stable code; the (cleaned) code itself when there is no entry."""
    key = f"{prefix}.{code}"
    return t(lang, key) if key in CATALOG["en"] else _c(code, 120)


def _codes(lang: str, prefix: str, details: str) -> str:
    return ", ".join(_label(lang, prefix, x.strip()) for x in details.split(",") if x.strip())


def _load(rec: AuditRecord, kind: str, model: type[M]) -> M | str:
    """The validated block, or the reason code why there is none."""
    raw = rec.extras.get(kind)
    if raw is None:
        return "suite-no-data"
    try:
        return model.model_validate(raw)
    except ValidationError:
        return "suite-bad-data"


def _why(rec: AuditRecord, *check_ids: str) -> str:
    """Reason a module produced nothing: its own NotChecked code when it left one."""
    for n in rec.not_checked:
        if n.check_id in check_ids:
            return n.reason_code
    return "suite-no-data"


def _nm(lang: str, reason: str) -> dict[str, Any]:
    return not_measured(lang, reason)


# --------------------------------------------------------------------------- technology


def techstack_section(rec: AuditRecord, lang: str) -> s.TechSection:
    from seoa.application.analysis.modules.techstack import TechStack

    data = _load(rec, "techstack", TechStack)
    if isinstance(data, str):
        return s.TechSection(**_nm(lang, data))
    if not data.items:
        return s.TechSection(**_nm(lang, "tech-none-detected"))
    groups: dict[str, list[s.TechRow]] = {}
    for it in data.items:
        groups.setdefault(it.category, []).append(
            s.TechRow(
                name=_c(it.name, 80),
                version=_c(it.version, 40) if it.version else None,
                confidence=it.confidence,
                evidence=_c(it.evidence, 160),
                website=_c(it.website, 200) if it.website else None,
            )
        )
    order = [c for c in CATEGORY_ORDER if c in groups] + sorted(set(groups) - set(CATEGORY_ORDER))
    return s.TechSection(
        status="measured",
        groups=[
            s.TechGroup(category=c, label=_label(lang, "tech.cat", c), items=groups[c][:LIST_CAP])
            for c in order
        ],
        total=len(data.items),
        note=t(lang, "tech.note"),
    )


CATEGORY_ORDER = (
    "cms",
    "ecommerce",
    "framework",
    "js-library",
    "ui",
    "server",
    "hosting",
    "cdn",
    "analytics",
    "tag-manager",
    "ads",
    "security",
    "font",
    "other",
)


# --------------------------------------------------------------------------- site setup


def _soft404(lang: str, d: dict[str, Any]) -> tuple[Literal["ok", "problem", "unknown"], str]:
    if not d:
        return "unknown", t(lang, "setup.soft404.unknown")
    if d.get("error") or d.get("detected") is None:
        return "unknown", t(lang, "setup.soft404.unknown")
    if d.get("detected") is True:
        return "problem", t(lang, "setup.soft404.problem", status=_c(d.get("final_status"), 10))
    return "ok", t(lang, "setup.soft404.ok", status=_c(d.get("final_status"), 10))


def site_setup_section(rec: AuditRecord, lang: str) -> s.SiteSetupSection:
    from seoa.application.analysis.modules.site_setup import SiteSetup

    data = _load(rec, "site_setup", SiteSetup)
    if isinstance(data, str):
        return s.SiteSetupSection(**_nm(lang, data))
    state, state_text = _soft404(lang, data.soft_404)
    c404 = (
        t(lang, "setup.custom404.unknown")
        if data.custom_404 is None
        else t(lang, "setup.custom404.yes" if data.custom_404 else "setup.custom404.no")
    )
    redirects = [
        s.RedirectRow(
            name=r.name,
            label=_label(lang, "setup.variant", r.name),
            variant_url=_c(r.variant_url, 300),
            status=r.status,
            final_url=_c(r.final_url, 300) if r.final_url else None,
            hops=r.hops,
            permanent=r.permanent,
            note=_label(lang, "reason", r.error.split(":")[0]) if r.error else None,
        )
        for r in data.redirects[:LIST_CAP]
    ]
    headers = [
        s.KV(label=_c(k, 60), value=_c(v, 200))
        for k, v in data.headers.items()
        if v not in (None, "")
    ][:LIST_CAP]
    hsts = data.hsts or {}
    if hsts.get("present"):
        parts = [
            f"max-age={_c(hsts.get('max_age') if hsts.get('max_age') is not None else '?', 12)}"
        ]
        if hsts.get("include_subdomains"):
            parts.append("includeSubDomains")
        if hsts.get("preload"):
            parts.append("preload")
        hsts_text = ", ".join(parts)
    else:
        hsts_text = t(lang, "setup.hsts.none")
    files = [
        s.FileRow(
            id=_c(k, 40),
            label=_label(lang, "setup.file", k),
            url=_c(p.url, 300),
            present=None if p.error else p.present,
            status=p.status,
            note=_c(p.detail, 160) if p.detail else (_c(p.error, 80) if p.error else None),
        )
        for k, p in list(data.files.items())[:LIST_CAP]
    ]
    return s.SiteSetupSection(
        status="measured",
        redirects=redirects,
        soft_404=state,
        soft_404_text=state_text,
        custom_404_text=c404,
        headers=headers,
        hsts_text=hsts_text,
        http_version_text=(
            t(lang, "setup.http.unknown")
            if data.http_version == "unknown"
            else _c(data.http_version, 20)
        ),
        files=files,
        skipped=[
            s.KV(label=_label(lang, "setup.variant", k), value=_label(lang, "reason", v))
            for k, v in data.skipped.items()
        ][:LIST_CAP],
        requests_made=data.requests_made,
    )


# --------------------------------------------------------------------------- previews


def _bool_text(lang: str, v: bool | None) -> str:
    return "—" if v is None else t(lang, "idx.yes" if v else "idx.no")


def previews_section(rec: AuditRecord, lang: str) -> s.PreviewsSection:
    from seoa.application.analysis.modules.previews import Previews

    data = _load(rec, "previews", Previews)
    if isinstance(data, str):
        return s.PreviewsSection(**_nm(lang, data))
    serp = [
        s.SerpRow(
            device=p.device,
            device_label=_label(lang, "dev", p.device),
            display_url=_c(p.display_url, 200),
            title_shown=_c(p.title_shown, 200),
            title_truncated=p.title_truncated,
            description_shown=_c(p.description_shown, 400),
            description_truncated=p.description_truncated,
            description_missing=p.description_missing,
        )
        for p in data.serp
    ]
    card = data.social
    social = [
        s.KV(label=f"og:{_c(k, 30)}", value=_c(v, 200)) for k, v in sorted(card.og.items())
    ] + [
        s.KV(label=f"twitter:{_c(k, 30)}", value=_c(v, 200))
        for k, v in sorted(card.twitter.items())
    ]
    img = card.image
    image_rows: list[s.KV] = []
    if img.url:
        image_rows.append(s.KV(label=t(lang, "prev.img.url"), value=_c(img.url, 300)))
        image_rows.append(
            s.KV(label=t(lang, "prev.img.reach"), value=_bool_text(lang, img.reachable))
        )
        if img.width and img.height:
            image_rows.append(
                s.KV(label=t(lang, "prev.img.size"), value=f"{img.width}×{img.height}")
            )
        if img.ratio:
            image_rows.append(s.KV(label=t(lang, "prev.img.ratio"), value=f"{img.ratio:.2f}:1"))
        if img.bytes is not None:
            kb = round(img.bytes / 1024)
            image_rows.append(
                s.KV(
                    label=t(lang, "prev.img.weight"),
                    value=f"{'≥ ' if img.bytes_is_lower_bound else ''}{kb} KB",
                )
            )
        if img.error:
            image_rows.append(
                s.KV(
                    label=t(lang, "prev.img.error"),
                    value=_label(lang, "reason", img.error.split(":")[0]),
                )
            )
    if card.missing_og:
        social.append(
            s.KV(label=t(lang, "prev.missing"), value=", ".join(_c(x, 30) for x in card.missing_og))
        )
    if not serp and not social and not image_rows:
        return s.PreviewsSection(**_nm(lang, "suite-no-data"))
    return s.PreviewsSection(
        status="measured",
        serp=serp,
        social=social,
        social_image=image_rows,
        notes=[_label(lang, "prev.note", n) for n in data.notes],
    )


# --------------------------------------------------------------------------- screenshots


def screenshots_section(rec: AuditRecord, lang: str, audit_id: str) -> s.ScreenshotsSection:
    from seoa.application.analysis.modules.screenshots import Screenshots

    data = _load(rec, "screenshots", Screenshots)
    if isinstance(data, str):
        return s.ScreenshotsSection(
            **_nm(lang, _why(rec, "screenshots") if data == "suite-no-data" else data)
        )
    shots = [
        s.ShotRow(
            device=f.device,
            device_label=_label(lang, "dev", f.device),
            name=f.name,
            url=f"/v1/audits/{audit_id}/files/{f.name}",
            width=f.width,
            height=f.height,
            kb=round(f.bytes / 1024, 1),
        )
        for f in data.files
        if f.name in SCREENSHOT_FILES
    ]
    if not shots:
        reason = "screenshots-failed" if data.errors else "suite-no-data"
        return s.ScreenshotsSection(**_nm(lang, reason))
    fold = [
        s.FoldRow(
            device=d,
            device_label=_label(lang, "dev", d),
            h1_present=a.h1_present,
            h1_visible=a.h1_visible,
            cta_visible=a.cta_visible,
            text_chars=a.text_chars,
            overflow=a.horizontal_overflow,
            overlay_pct=round(a.overlay_share * 100, 1),
        )
        for d, a in data.above_fold.items()
    ]
    return s.ScreenshotsSection(
        status="measured",
        shots=shots,
        above_fold=fold,
        errors=[
            s.KV(label=_label(lang, "dev", k), value=_c(v, 120)) for k, v in data.errors.items()
        ],
    )


# --------------------------------------------------------------------------- readability


def _term_rows(items: list[dict[str, Any]]) -> list[s.KV]:
    out = []
    for it in items[:LIST_CAP]:
        name = it.get("term") or it.get("phrase") or it.get("text") or ""
        count = it.get("count", it.get("n", ""))
        if name:
            out.append(s.KV(label=_c(name, 80), value=_c(count, 12)))
    return out


def readability_section(rec: AuditRecord, lang: str) -> s.ReadabilitySection:
    from seoa.application.analysis.modules.readability import ReadabilityData

    data = _load(rec, "readability", ReadabilityData)
    if isinstance(data, str):
        return s.ReadabilitySection(**_nm(lang, data))
    r = data.readability or {}
    scores: list[s.KV] = []
    if isinstance(r.get("score"), (int, float)):
        scores.append(
            s.KV(
                label=_label(lang, "read.formula", str(r.get("formula", ""))),
                value=f"{float(r['score']):.1f}"
                + (f" · {_label(lang, 'read.val', str(r['label']))}" if r.get("label") else ""),
            )
        )
    if isinstance(r.get("grade"), (int, float)):
        scores.append(s.KV(label=t(lang, "read.m.grade"), value=f"{float(r['grade']):.1f}"))
    for key in ("words", "sentences", "paragraphs", "avg_sentence_words", "avg_syllables_per_word"):
        if isinstance(r.get(key), (int, float)):
            scores.append(s.KV(label=t(lang, f"read.m.{key}"), value=_c(r[key], 12)))
    if isinstance(r.get("long_sentence_share"), (int, float)):
        scores.append(
            s.KV(
                label=t(lang, "read.m.long_sentence_share"),
                value=f"{round(float(r['long_sentence_share']) * 100)}%",
            )
        )
    terms = _term_rows(data.terms)
    phrases = _term_rows(data.phrases)
    if not scores and not terms:
        return s.ReadabilitySection(
            **_nm(lang, _why(rec, "readability") if not data.language else "language-unsupported")
        )
    kws = [
        s.KeywordRow(
            keyword=_c(k.keyword, 80),
            in_title=k.in_title,
            in_h1=k.in_h1,
            in_description=k.in_description,
            in_url=k.in_url,
            in_first_100_words=k.in_first_100_words,
            in_subheadings=k.in_subheadings,
            occurrences=k.occurrences,
            density_percent=round(k.density_percent, 2),
        )
        for k in data.keywords[:KEYWORD_CAP]
    ]
    return s.ReadabilitySection(
        status="measured",
        language=_c(data.language, 10) if data.language else None,
        scores=scores,
        terms=terms,
        phrases=phrases,
        keywords=kws,
        keywords_not_measured_text=None if kws else t(lang, "read.kw.none"),
        suggested_targets=[_c(x, 80) for x in data.suggested_targets[:10]],
        notes=[_label(lang, "read.note", n) for n in data.notes],
    )


# --------------------------------------------------------------------------- hreflang


def hreflang_section(rec: AuditRecord, lang: str) -> s.HreflangSection:
    from seoa.application.analysis.modules.hreflang import HreflangReport

    data = _load(rec, "hreflang", HreflangReport)
    if isinstance(data, str):
        return s.HreflangSection(
            **_nm(lang, _why(rec, "hreflang") if data == "suite-no-data" else data)
        )
    if not data.applicable or not data.pages:
        return s.HreflangSection(
            **_nm(lang, "hreflang-not-applicable"),
            notes=[_label(lang, "hreflang.note", n) for n in data.notes],
        )
    rows = [
        s.HreflangRow(
            url=_c(p.url, 300),
            html_lang=_c(p.html_lang, 20),
            canonical=_c(p.canonical, 300) if p.canonical else None,
            entries=[
                s.KV(label=_c(e.lang, 20) + ("" if e.valid else " ⚠"), value=_c(e.href, 300))
                for e in p.entries[:LIST_CAP]
            ],
            issues=[_label(lang, "hreflang.issue", i) for i in p.issues],
        )
        for p in data.pages[:HREFLANG_ROWS]
    ]
    return s.HreflangSection(
        status="measured",
        languages=[_c(x, 20) for x in data.languages[:LIST_CAP]],
        has_x_default=data.has_x_default,
        rows=rows,
        rows_total=len(data.pages),
        unchecked=data.unchecked,
        notes=[_label(lang, "hreflang.note", n) for n in data.notes],
    )


# --------------------------------------------------------------------------- schema suggestions


def schema_suggest_section(rec: AuditRecord, lang: str) -> s.SchemaSuggestSection:
    from seoa.application.analysis.modules.schema_suggest import SchemaSuggestions

    data = _load(rec, "schema_suggestions", SchemaSuggestions)
    if isinstance(data, str):
        return s.SchemaSuggestSection(**_nm(lang, data))
    if not data.items:
        return s.SchemaSuggestSection(
            **_nm(lang, "schema-nothing-to-suggest"),
            notes=[_label(lang, "schemasug.note", n) for n in data.notes],
        )
    items = [
        s.SchemaItem(
            url=_c(i.url, 300),
            type=_c(i.type, 60),
            reason=_c(i.reason, 300),
            json_ld=clean_text(i.json_ld)[:JSON_LD_CAP],
            complete=i.complete,
            missing_fields=[_c(x, 60) for x in i.missing_fields[:LIST_CAP]],
            rich_result_note=_c(i.rich_result_note, 300),
            warning=_c(i.warning, 300),
        )
        for i in data.items[:SCHEMA_ITEMS]
    ]
    return s.SchemaSuggestSection(
        status="measured",
        items=items,
        items_total=len(data.items),
        truncated=len(data.items) > SCHEMA_ITEMS,
        notes=[_label(lang, "schemasug.note", n) for n in data.notes],
    )


# --------------------------------------------------------------------------- agentic


def agentic_section(rec: AuditRecord, lang: str) -> s.AgenticSection:
    from seoa.application.analysis.modules.agentic import AgenticReadiness

    data = _load(rec, "agentic", AgenticReadiness)
    if isinstance(data, str):
        return s.AgenticSection(**_nm(lang, data))
    if not data.checks:
        return s.AgenticSection(**_nm(lang, "suite-no-data"))
    rows = [
        s.AgenticRow(
            id=c.id,
            label=_label(lang, "agentic.check", c.id),
            status=c.status,
            detail=_codes(lang, "agentic.detail", c.detail) if c.detail else "",
        )
        for c in data.checks
    ]
    return s.AgenticSection(
        status="measured",
        rows=rows,
        fraction=_c(data.fraction, 12),
        note=t(lang, "agentic.note"),
        notes=[_label(lang, "agentic.llms", n) for n in data.llms_txt_notes],
    )


# --------------------------------------------------------------------------- one look


def _ms_text(v: float | int | None) -> str:
    if v is None:
        return "—"
    return f"{v / 1000:.1f} s" if v >= 1000 else f"{round(v)} ms"


def glance_section(rec: AuditRecord, lang: str, tech: s.TechSection) -> s.GlanceSection:
    items: list[s.KV] = []
    sc = rec.scores
    if sc is not None:
        items.append(
            s.KV(
                label=t(lang, "glance.score"),
                value=f"{sc.overall:.0f} / 100"
                if sc.overall is not None
                else t(lang, "glance.insufficient"),
            )
        )
    perf = next((p for p in rec.perf if not p.error), None)
    if perf is not None:
        items.append(s.KV(label=t(lang, "glance.lcp"), value=_ms_text(perf.lcp_ms)))
        items.append(s.KV(label=t(lang, "glance.ttfb"), value=_ms_text(perf.ttfb_ms)))
        items.append(
            s.KV(
                label=t(lang, "glance.weight"),
                value=f"{round(perf.total_bytes / 1024):,} KB".replace(",", "."),
            )
        )
        items.append(s.KV(label=t(lang, "glance.requests"), value=str(perf.total_requests)))
    if rec.indexability:
        ok = sum(1 for r in rec.indexability if r.indexable)
        items.append(
            s.KV(label=t(lang, "glance.indexable"), value=f"{ok} / {len(rec.indexability)}")
        )
    if rec.links is not None:
        lk = rec.links
        items.append(
            s.KV(label=t(lang, "glance.links"), value=f"{lk.internal_total} / {lk.external_total}")
        )
        items.append(s.KV(label=t(lang, "glance.broken"), value=str(lk.broken)))
    if tech.status == "measured":
        names = [i.name for g in tech.groups[:4] for i in g.items[:1]]
        if names:
            items.append(s.KV(label=t(lang, "glance.tech"), value=", ".join(names)))
    counts = {"CRITICAL": 0, "HIGH": 0}
    for f in rec.findings:
        if f.severity.value in counts:
            counts[f.severity.value] += 1
    items.append(
        s.KV(label=t(lang, "glance.issues"), value=f"{counts['CRITICAL']} / {counts['HIGH']}")
    )
    return s.GlanceSection(status="measured", items=items)


def build_suite(rec: AuditRecord, lang: str) -> dict[str, Any]:
    tech = techstack_section(rec, lang)
    return {
        "glance": glance_section(rec, lang, tech),
        "techstack": tech,
        "site_setup": site_setup_section(rec, lang),
        "previews": previews_section(rec, lang),
        "screenshots": screenshots_section(rec, lang, rec.id),
        "readability": readability_section(rec, lang),
        "hreflang": hreflang_section(rec, lang),
        "schema_suggestions": schema_suggest_section(rec, lang),
        "agentic": agentic_section(rec, lang),
    }
