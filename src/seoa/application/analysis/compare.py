"""Compare two audits of the same site (belge 12 C1): score change, new / resolved / persisting
findings, and metric changes.

Pure function over two ``AuditRecord`` values. Scores are only compared when they are comparable:
the same ``score_version`` and the same mode. Otherwise the result says so (``warnings``) and carries
NO score numbers: a difference between two different scoring schemes would be meaningless.
Findings are keyed by (rule id, url); a site-wide finding has no url.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from seoa.domain import AuditRecord, Finding, Severity

LIST_CAP = 50
_SEVERITY_ORDER = {s: i for i, s in enumerate(Severity)}

Better = Literal["up", "down"]  # which direction is an improvement


class Delta(BaseModel):
    old: float | None = None
    new: float | None = None
    delta: float | None = None


class CategoryDelta(Delta):
    category: str


class MetricDelta(Delta):
    key: str  # stable code: lcp_ms, ttfb_ms, total_bytes, requests, ...
    improved: bool | None = None  # None: no direction (or unchanged / unknown)


class FindingRef(BaseModel):
    rule_id: str
    severity: str
    category: str
    url: str | None = None


class Comparison(BaseModel):
    old_id: str
    new_id: str
    comparable: bool
    warnings: list[str] = Field(default_factory=list)  # score-version-differs | mode-differs
    overall: Delta | None = None
    core_overall: Delta | None = None
    categories: list[CategoryDelta] = Field(default_factory=list)
    new_findings: list[FindingRef] = Field(default_factory=list)
    resolved_findings: list[FindingRef] = Field(default_factory=list)
    persisting_count: int = 0
    new_total: int = 0
    resolved_total: int = 0
    metrics: list[MetricDelta] = Field(default_factory=list)


def _delta(old: float | None, new: float | None) -> Delta:
    d = round(new - old, 1) if old is not None and new is not None else None
    return Delta(old=old, new=new, delta=d)


def _ref(f: Finding) -> FindingRef:
    return FindingRef(rule_id=f.id, severity=f.severity.value, category=f.category.value, url=f.url)


def _key(f: Finding) -> tuple[str, str]:
    return (f.id, f.url or "")


def _metrics(rec: AuditRecord) -> dict[str, float | None]:
    perf = next((p for p in rec.perf if not p.error), None)
    out: dict[str, float | None] = {
        "lcp_ms": perf.lcp_ms if perf else None,
        "ttfb_ms": perf.ttfb_ms if perf else None,
        "total_bytes": perf.total_bytes if perf else None,
        "requests": perf.total_requests if perf else None,
        "internal_links": None,
        "external_links": None,
        "broken_links": None,
        "indexable_pages": None,
    }
    if rec.links is not None:
        out["internal_links"] = rec.links.internal_total
        out["external_links"] = rec.links.external_total
        out["broken_links"] = rec.links.broken
    if rec.indexability:
        out["indexable_pages"] = sum(1 for r in rec.indexability if r.indexable)
    return out


# which way is better; links are not listed: more or fewer links is not good or bad by itself
_DIRECTION: dict[str, Better | None] = {
    "lcp_ms": "down",
    "ttfb_ms": "down",
    "total_bytes": "down",
    "requests": "down",
    "broken_links": "down",
    "indexable_pages": "up",
    "internal_links": None,
    "external_links": None,
}


def _score_version(rec: AuditRecord) -> str:
    return rec.scores.score_version if rec.scores else rec.score_version


def compare(old: AuditRecord, new: AuditRecord) -> Comparison:
    warnings: list[str] = []
    if _score_version(old) != _score_version(new):
        warnings.append("score-version-differs")
    if old.mode != new.mode:
        warnings.append("mode-differs")
    out = Comparison(old_id=old.id, new_id=new.id, comparable=not warnings, warnings=warnings)

    if out.comparable and old.scores is not None and new.scores is not None:
        out.overall = _delta(old.scores.overall, new.scores.overall)
        out.core_overall = _delta(old.scores.core_overall, new.scores.core_overall)
        before = {c.category.value: c.score if c.measured else None for c in old.scores.categories}
        for c in new.scores.categories:
            name = c.category.value
            d = _delta(before.get(name), c.score if c.measured else None)
            out.categories.append(CategoryDelta(category=name, **d.model_dump()))

    old_by = {_key(f): f for f in old.findings}
    new_by = {_key(f): f for f in new.findings}
    appeared = [f for k, f in new_by.items() if k not in old_by]
    gone = [f for k, f in old_by.items() if k not in new_by]
    # the worst first: that is what the reader looks at
    appeared.sort(key=lambda f: (_SEVERITY_ORDER[f.severity], f.id, f.url or ""))
    gone.sort(key=lambda f: (_SEVERITY_ORDER[f.severity], f.id, f.url or ""))
    out.new_total, out.resolved_total = len(appeared), len(gone)
    out.new_findings = [_ref(f) for f in appeared[:LIST_CAP]]
    out.resolved_findings = [_ref(f) for f in gone[:LIST_CAP]]
    out.persisting_count = len(new_by.keys() & old_by.keys())

    mo, mn = _metrics(old), _metrics(new)
    for key, direction in _DIRECTION.items():
        d = _delta(mo[key], mn[key])
        if d.old is None and d.new is None:
            continue
        improved: bool | None = None
        if d.delta and direction:
            improved = d.delta < 0 if direction == "down" else d.delta > 0
        out.metrics.append(MetricDelta(key=key, improved=improved, **d.model_dump()))
    return out
