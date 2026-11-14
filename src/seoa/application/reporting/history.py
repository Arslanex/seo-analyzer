"""Report sections for history (belge 12 C1) and competitor comparison (C2).

``history`` is not part of the score: it only tells how this audit differs from the previous one of
the same site. It needs data from other audits, so the caller passes it in (``HistoryInput``); the
report builder itself stays a pure function of its inputs.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from seoa.application.analysis.compare import Comparison, Delta, FindingRef, compare
from seoa.application.audit.protocol import AuditSummary
from seoa.application.reporting import schema as s
from seoa.application.reporting.deep import not_measured
from seoa.domain import AuditRecord
from seoa.domain.i18n import t
from seoa.domain.rules import registry
from seoa.domain.text import clean_text

HISTORY_ROWS = 10
Direction = Literal["better", "worse", "same", "none"]
_FINISHED = ("completed", "partial")
_METRIC_ORDER = (
    "lcp_ms",
    "ttfb_ms",
    "total_bytes",
    "requests",
    "internal_links",
    "external_links",
    "broken_links",
    "indexable_pages",
)


@dataclass
class HistoryInput:
    """Other audits of the same site: the list (newest first) and the full previous record."""

    entries: list[AuditSummary] = field(default_factory=list)
    previous: AuditRecord | None = None


def pick_previous(audit_id: str, mode: str, entries: list[AuditSummary]) -> str | None:
    """Id of the closest older finished audit in the same mode (``entries`` is newest first)."""
    ids = [e.id for e in entries]
    if audit_id not in ids:
        return None
    for e in entries[ids.index(audit_id) + 1 :]:
        if e.mode.value == mode and e.status.value in _FINISHED and e.overall is not None:
            return e.id
    return None


def _c(text: object, limit: int = 300) -> str:
    return clean_text(str(text))[:limit]


def _num(v: float | None) -> str:
    return "—" if v is None else f"{v:.1f}".rstrip("0").rstrip(".")


def _ms(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v / 1000:.1f} s" if v >= 1000 else f"{round(v)} ms"


def _kb(v: float | None) -> str:
    return "—" if v is None else f"{round(v / 1024):,} KB".replace(",", ".")


def _count(v: float | None) -> str:
    return "—" if v is None else str(round(v))


_FORMAT = {
    "lcp_ms": _ms,
    "ttfb_ms": _ms,
    "total_bytes": _kb,
    "requests": _count,
    "internal_links": _count,
    "external_links": _count,
    "broken_links": _count,
    "indexable_pages": _count,
}


def _signed(delta: float | None, fmt: Callable[[float | None], str] = _num) -> str:
    if delta is None:
        return "—"
    if delta == 0:
        return "0"
    return ("+" if delta > 0 else "−") + fmt(abs(delta))


def _score_change(label: str, d: Delta) -> s.HistoryChange:
    direction: Direction = "none"
    if d.delta is not None:
        direction = "same" if d.delta == 0 else ("better" if d.delta > 0 else "worse")
    return s.HistoryChange(
        label=label, old=_num(d.old), new=_num(d.new), delta=_signed(d.delta), direction=direction
    )


def _finding_row(ref: FindingRef, lang: str) -> s.HistoryFinding:
    rule = registry.RULES.get(ref.rule_id)
    title = registry.message(rule.message_key, lang) if rule else ref.rule_id
    return s.HistoryFinding(
        rule_id=_c(ref.rule_id, 80),
        severity=ref.severity,
        title=_c(title, 200),
        url=_c(ref.url, 300) if ref.url else None,
    )


def _comparison_into(section: s.HistorySection, cmp: Comparison, lang: str) -> None:
    if not cmp.comparable:
        section.warning_text = " ".join(t(lang, f"hist.warn.{w}") for w in cmp.warnings)
    if cmp.overall is not None:
        section.scores.append(_score_change(t(lang, "hist.overall"), cmp.overall))
    if cmp.core_overall is not None and cmp.core_overall.new is not None:
        section.scores.append(_score_change(t(lang, "hist.core"), cmp.core_overall))
    for cd in cmp.categories:
        if cd.old is None and cd.new is None:
            continue
        section.scores.append(_score_change(t(lang, f"cat.{cd.category}"), cd))
    by_key = {m.key: m for m in cmp.metrics}
    for key in _METRIC_ORDER:
        m = by_key.get(key)
        if m is None:
            continue
        fmt = _FORMAT[key]
        direction: Direction = "none"
        if m.delta is not None:
            if m.delta == 0:
                direction = "same"
            elif m.improved is not None:
                direction = "better" if m.improved else "worse"
        section.metrics.append(
            s.HistoryChange(
                label=t(lang, f"hist.metric.{key}"),
                old=fmt(m.old),
                new=fmt(m.new),
                delta=_signed(m.delta, fmt),
                direction=direction,
            )
        )
    section.new_findings = [_finding_row(f, lang) for f in cmp.new_findings]
    section.resolved_findings = [_finding_row(f, lang) for f in cmp.resolved_findings]
    section.new_total, section.resolved_total = cmp.new_total, cmp.resolved_total
    section.persisting = cmp.persisting_count


def history_section(rec: AuditRecord, lang: str, hist: HistoryInput | None) -> s.HistorySection:
    if hist is None:
        return s.HistorySection(**not_measured(lang, "history-unavailable"))
    older = [e for e in hist.entries if e.id != rec.id]
    if not older:
        return s.HistorySection(**not_measured(lang, "first-audit"))
    section = s.HistorySection(status="measured", note=t(lang, "hist.note"))
    shown = hist.entries[:HISTORY_ROWS]
    if rec.id not in {e.id for e in shown}:  # the current one is always in the table
        shown = [*shown[: HISTORY_ROWS - 1], *(e for e in hist.entries if e.id == rec.id)]
    section.rows = [
        s.HistoryRow(
            id=e.id,
            url=_c(e.target_url),
            created_at=e.created_at,
            mode=e.mode.value,
            status=e.status.value,
            overall=e.overall,
            coverage_pct=e.coverage_pct,
            is_current=e.id == rec.id,
            href=f"/audits/{e.id}/report",
        )
        for e in shown
    ]
    section.rows_total = len(hist.entries)
    section.truncated = len(hist.entries) > len(section.rows)
    prev = hist.previous
    if prev is not None and prev.id != rec.id:
        section.previous_id = prev.id
        section.previous_at = prev.created_at
        section.previous_href = f"/audits/{prev.id}/report"
        _comparison_into(section, compare(prev, rec), lang)
    return section


# --------------------------------------------------------------------------- competitors


def _pct(v: float | None) -> str:
    return "—" if v is None else f"{v:g} %"


def _opt(v: object) -> str:
    return "—" if v is None else _c(v, 120)


_METRICS = (
    "score",
    "status",
    "title_len",
    "meta_len",
    "h1_count",
    "words",
    "schema",
    "images",
    "alt_pct",
    "canonical",
    "noindex",
    "ttfb",
    "html_kb",
    "links",
    "readability",
    "tech",
)


def competitors_section(rec: AuditRecord, lang: str) -> s.CompetitorsSection:
    from seoa.application.analysis.modules.competitors import CompetitorComparison, CompetitorRow
    from seoa.application.reporting.suite import _load, _why

    data = _load(rec, "competitors", CompetitorComparison)
    if isinstance(data, str):
        return s.CompetitorsSection(
            **not_measured(lang, _why(rec, "competitors") if data == "suite-no-data" else data)
        )
    if not data.rows:
        return s.CompetitorsSection(**not_measured(lang, _why(rec, "competitors")))

    def yn(v: bool | None) -> str:
        return "—" if v is None else t(lang, "idx.yes" if v else "idx.no")

    def values(r: CompetitorRow) -> list[str]:
        canon = {
            "self": t(lang, "comp.canon.self"),
            "other": t(lang, "comp.canon.other"),
            "none": t(lang, "comp.canon.none"),
        }
        links = "—" if r.internal_links is None else f"{r.internal_links} / {r.external_links}"
        read = (
            "—"
            if r.readability_score is None
            else f"{r.readability_score:g} ({t(lang, 'comp.formula.' + str(r.readability_formula))})"
        )
        return [
            _opt(r.score),
            _opt(r.status),
            _opt(r.title_len),
            _opt(r.meta_len),
            _opt(r.h1_count),
            _opt(r.words),
            ", ".join(_c(x, 40) for x in r.schema_types) or "—",
            _opt(r.images),
            _pct(r.images_alt_pct),
            canon.get(r.canonical or "", "—"),
            yn(r.noindex),
            _ms(r.ttfb_ms),
            _kb(r.html_bytes),
            links,
            read,
            ", ".join(_c(x, 40) for x in r.tech) or "—",
        ]

    def column(r: CompetitorRow) -> s.CompetitorColumn:
        note = None
        if r.error:
            note = t(lang, f"comp.err.{r.error}") if r.error in _KNOWN_ERRORS else _c(r.error, 60)
        elif r.title_len is None:
            note = t(lang, "comp.err.no-data")
        return s.CompetitorColumn(
            host=_c(r.host or r.url, 120),
            url=_c(r.final_url or r.url),
            is_you=r.is_you,
            note=note,
            values=values(r),
        )

    columns = ([column(data.you)] if data.you else []) + [column(r) for r in data.rows]
    skipped = [
        s.KV(label=_c(x.url, 200), value=t(lang, f"comp.skip.{x.reason}")) for x in data.skipped
    ]
    return s.CompetitorsSection(
        status="measured",
        metrics=[t(lang, f"comp.m.{m}") for m in _METRICS],
        columns=columns,
        skipped=skipped,
        note=t(lang, "comp.note"),
    )


_KNOWN_ERRORS = ("target-rejected", "timeout", "unreachable", "not-html")
