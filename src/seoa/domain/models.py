"""Domain models (belge 04 sozlesmesi). Enum degerleri belgelerle birebir aynidir."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class Severity(StrEnum):
    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    INFO = "Info"


SEVERITY_ORDER = (Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO)


class Category(StrEnum):
    TECHNICAL = "technical"
    ONPAGE = "onpage"
    LINKS = "links"
    CONTENT = "content"
    SCHEMA = "schema"
    PERFORMANCE = "performance"
    AI_READINESS = "ai_readiness"
    IMAGES = "images"


class Layer(StrEnum):
    A = "A"
    B = "B"


class AuditMode(StrEnum):
    SITE = "site"
    PAGE = "page"


class AuditStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PARTIAL = "partial"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class Stage(StrEnum):
    VALIDATE = "validate"
    FETCH_ENTRY = "fetch_entry"
    ROBOTS = "robots"
    DISCOVERY = "discovery"
    SAMPLE = "sample"
    FETCH_PAGES = "fetch_pages"
    RENDER = "render"
    MEASURE = "measure"
    ANALYZE = "analyze"
    SCORE = "score"
    ADVISE = "advise"
    SYNTHESIZE = "synthesize"
    REPORT = "report"


class StageStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    SKIPPED = "skipped"
    FAILED = "failed"


# --------------------------------------------------------------------------- fetch


class Hop(BaseModel):
    url: str
    status: int


class FetchResult(BaseModel):
    """Result of one validated HTTP fetch (belge 05 s.6.5)."""

    url: str
    final_url: str
    status: int | None = None
    headers: dict[str, str] = Field(default_factory=dict)  # lower-cased names
    redirect_chain: list[Hop] = Field(default_factory=list)
    content_type: str | None = None
    html: str | None = None  # decoded text body (None for non-HTML / failure)
    html_bytes: int = 0
    truncated: bool = False
    ttfb_ms: int | None = None
    total_ms: int | None = None
    error: str | None = None  # stable code, e.g. "unreachable", "target-rejected", "timeout"
    error_detail: str | None = None
    fetched_at: datetime | None = None


# --------------------------------------------------------------------------- findings


class Finding(BaseModel):
    """One deterministic finding (Layer A/B). Immutable once produced (belge 01 s.6)."""

    id: str
    rule_version: str = "1.0"
    category: Category
    layer: Layer = Layer.A
    severity: Severity
    severity_original: Severity | None = None
    severity_reason: str | None = None
    scope: Literal["page", "site"] = "page"
    url: str | None = None
    message_key: str
    message: str  # English default text, fixed (no page data)
    evidence: str | None = None  # <=200 chars, untrusted (comes from the page)
    count: int | None = None
    heuristic: bool = False
    confidence: Literal["high", "medium", "low"] = "high"
    recommendation_key: str | None = None
    effort: Literal["S", "M", "L"] | None = None
    impact: Literal["low", "medium", "high"] | None = None


class NotChecked(BaseModel):
    check_id: str
    reason_code: str  # belge 05 s.12 codes, e.g. "headers-unavailable", "language-unsupported"
    url: str | None = None


class CheckOutput(BaseModel):
    findings: list[Finding] = Field(default_factory=list)
    not_checked: list[NotChecked] = Field(default_factory=list)
    facts: dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------- scoring


class Penalty(BaseModel):
    """Points a failing rule cost its category (score v2: 100 * w * (1 - s) / sum(w))."""

    check_id: str
    severity: Severity
    points: float
    count: int = 1
    pages_affected: int = 1


class CheckResult(BaseModel):
    """One applicable check behind a category score ("show the checks behind every score")."""

    check_id: str
    severity: Severity
    weight: float
    pass_ratio: float  # 1.0 = passed everywhere it applied
    pages_affected: int = 0
    pages_assessed: int = 1
    status: Literal["pass", "warn", "fail"] = "pass"


class CategoryScore(BaseModel):
    category: Category
    weight: float
    score: float | None  # None when not measured
    measured: bool
    reason: str | None = None  # why not measured
    penalties: list[Penalty] = Field(default_factory=list)
    checks: list[CheckResult] = Field(default_factory=list)
    checks_total: int = 0
    checks_passed: int = 0
    checks_failed: int = 0


class Gate(BaseModel):
    check_id: str
    cap: int
    reason: str


class Scores(BaseModel):
    score_version: str
    overall: float | None  # None when insufficient data
    raw_overall: float | None = None
    coverage_pct: float
    insufficient_data: bool = False
    gate: Gate | None = None
    confidence: Literal["high", "medium", "low"] = "medium"
    categories: list[CategoryScore] = Field(default_factory=list)
    core_overall: float | None = None  # trend score from core sample only (belge 00 s.3.3)
    p25: float | None = None  # lower-quartile page score (site mode)


# --------------------------------------------------------------------------- layer C


class AdvisoryRecord(BaseModel):
    kind: Literal["eeat", "ai_readiness", "sxo"]
    page_url: str | None = None
    score: float | None = None
    label: Literal["exceptional", "strong", "moderate", "weak", "very_low"] | None = None
    coverage_pct: float | None = None
    factors: list[dict[str, Any]] = Field(default_factory=list)
    signals: list[dict[str, Any]] = Field(default_factory=list)
    observations: list[dict[str, Any]] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] = "low"
    rubric_version: str = ""
    prompt_version: str = ""
    error: str | None = None  # "unavailable: <reason>" when the module could not run


class AdviceRecord(BaseModel):
    finding_id: str
    url: str | None = None
    text: str


class SynthesisRecord(BaseModel):
    summary: str = ""
    links: list[dict[str, Any]] = Field(default_factory=list)  # [{finding_ids, text}]
    error: str | None = None


# --------------------------------------------------------------------------- deep analysis (belge 11)


class LinkRecord(BaseModel):
    source_url: str
    target_url: str  # normalised
    anchor: str = ""  # <= 120 chars
    kind: Literal["internal", "external"]
    rel: list[str] = Field(default_factory=list)  # nofollow, sponsored, ugc, ...
    zone: Literal["nav", "footer", "main", "other"] = "other"
    target_status: int | None = None
    final_url: str | None = None
    redirect_hops: int = 0
    error: str | None = None  # "timeout" | "unreachable" | "target-rejected" | ...
    checked: bool = False  # True when a status was obtained (sample or HEAD/GET)


class PageLinkStats(BaseModel):
    url: str
    outlinks_internal: int = 0
    outlinks_external: int = 0
    inlinks: int = 0  # from sampled pages only
    depth: int | None = None  # clicks from the entry page (BFS over the sampled graph)
    in_sitemap: bool | None = None


class LinkSummary(BaseModel):
    internal_total: int = 0
    external_total: int = 0
    internal_unique: int = 0
    external_unique: int = 0
    external_domains: list[dict[str, Any]] = Field(default_factory=list)  # [{domain, count}]
    checked: int = 0
    skipped: int = 0  # not checked because of the per-audit limit
    broken: int = 0
    redirecting: int = 0
    nofollow: int = 0
    max_depth: int | None = None
    orphans: list[str] = Field(default_factory=list)
    pages: list[PageLinkStats] = Field(default_factory=list)
    links: list[LinkRecord] = Field(default_factory=list)  # capped (<= 2000)
    truncated: bool = False


class ImageRecord(BaseModel):
    page_url: str
    src: str
    served_format: str | None = None  # webp | avif | jpeg | png | gif | svg | unknown
    bytes: int | None = None  # transferred (or content-length)
    natural_w: int | None = None
    natural_h: int | None = None
    displayed_w: int | None = None
    displayed_h: int | None = None
    has_alt: bool = True
    lazy: bool = False
    above_fold: bool = False
    category: Literal["thumbnail", "content", "hero"] = "content"
    issues: list[str] = Field(default_factory=list)  # check ids


class PagePerf(BaseModel):
    """Lab measurement of one page (this machine and network; not field data)."""

    url: str
    device: Literal["desktop", "mobile"] = "desktop"
    ttfb_ms: int | None = None
    fcp_ms: int | None = None
    lcp_ms: int | None = None
    cls: float | None = None
    tbt_ms: int | None = None  # sum of long-task time above 50 ms (proxy for TBT)
    dom_content_loaded_ms: int | None = None
    load_ms: int | None = None
    total_requests: int = 0
    total_bytes: int = 0  # transferred
    html_bytes: int = 0
    by_type: dict[str, dict[str, int]] = Field(
        default_factory=dict
    )  # {"script": {"count": 3, "bytes": 1234}}
    third_party: list[dict[str, Any]] = Field(default_factory=list)  # [{host, requests, bytes}]
    render_blocking: int = 0
    uncompressed_text: list[str] = Field(default_factory=list)  # URLs
    no_cache_static: list[str] = Field(default_factory=list)  # URLs
    mobile: dict[str, Any] | None = (
        None  # {horizontal_overflow, small_font_share, small_tap_targets, viewport_meta}
    )
    images: list[ImageRecord] = Field(default_factory=list)
    error: str | None = None  # "render-failed: ..." when the page could not be measured


class IndexabilityRow(BaseModel):
    url: str
    status: int | None = None
    indexable: bool = True
    reasons: list[str] = Field(
        default_factory=list
    )  # noindex, noindex-header, canonical-elsewhere, blocked-by-robots, status-4xx, status-5xx
    canonical: str | None = None
    in_sitemap: bool | None = None
    inlinks: int | None = None
    depth: int | None = None


class VisibilitySignals(BaseModel):
    """Public, keyless, informational signals. Never part of the score; never proof of indexing."""

    domain: str
    rdap: dict[str, Any] = Field(default_factory=dict)  # {created, age_days, registrar, error}
    wayback: dict[str, Any] = Field(
        default_factory=dict
    )  # {first_capture, last_capture, captures, error}
    common_crawl: dict[str, Any] = Field(
        default_factory=dict
    )  # {collection, present, pages_seen, error}
    search_console: dict[str, Any] = Field(default_factory=lambda: {"connected": False})
    notes: list[str] = Field(default_factory=list)


class GscRow(BaseModel):
    key: str  # query or page URL
    clicks: int = 0
    impressions: int = 0
    ctr: float = 0.0
    position: float = 0.0


class GscInspection(BaseModel):
    """URL Inspection result of one page (Google's own view of it)."""

    url: str
    verdict: str | None = None  # PASS | NEUTRAL | FAIL | VERDICT_UNSPECIFIED
    coverage_state: str | None = (
        None  # e.g. "Submitted and indexed", "Discovered - currently not indexed"
    )
    indexing_state: str | None = None
    robots_txt_state: str | None = None
    page_fetch_state: str | None = None
    google_canonical: str | None = None
    user_canonical: str | None = None
    last_crawl_time: str | None = None
    crawled_as: str | None = None
    indexed: bool | None = None
    error: str | None = None


class GscSitemap(BaseModel):
    path: str
    last_submitted: str | None = None
    last_downloaded: str | None = None
    is_pending: bool = False
    errors: int = 0
    warnings: int = 0


class KeywordRankRow(BaseModel):
    """What Search Console reports for one keyword the user asked about (last ``period_days``)."""

    keyword: str
    matched_query: str | None = (
        None  # set when no exact query matched and a containing one was used
    )
    impressions: int = 0
    clicks: int = 0
    ctr: float = 0.0
    position: float | None = None
    top_page: str | None = None  # the URL with the most impressions for this query
    status: Literal["ok", "no-data", "error"] = "no-data"
    error: str | None = None  # stable code (rate-limited, http-500, ...) when status == "error"


class RankingQuery(BaseModel):
    """A query from the property's own Search Console data that deserves attention."""

    query: str
    impressions: int = 0
    clicks: int = 0
    ctr: float = 0.0
    position: float = 0.0


class KeywordRankings(BaseModel):
    """Rankings of the user's keywords plus opportunities from the site's own queries.

    Informational: never part of the score. Search Console hides rare queries, so ``no-data`` does
    not mean "not ranking".
    """

    period_days: int = 28
    keywords_requested: int = 0
    rows: list[KeywordRankRow] = Field(default_factory=list)
    opportunities: list[RankingQuery] = Field(default_factory=list)
    low_ctr: list[RankingQuery] = Field(default_factory=list)
    error: str | None = None  # the opportunity query failed (keyword rows may still be there)


class GscData(BaseModel):
    """Search Console data for the audited site (only with the owner's authorisation)."""

    status: Literal[
        "ok", "not-connected", "not-configured", "property-not-found", "no-permission", "error"
    ] = "not-connected"
    account: str | None = None
    property: str | None = None  # sc-domain:example.com | https://example.com/
    permission: str | None = (
        None  # siteOwner | siteFullUser | siteRestrictedUser | siteUnverifiedUser
    )
    period_days: int = 28
    totals: dict[str, float] = Field(default_factory=dict)  # clicks, impressions, ctr, position
    top_queries: list[GscRow] = Field(default_factory=list)
    top_pages: list[GscRow] = Field(default_factory=list)
    inspections: list[GscInspection] = Field(default_factory=list)
    sitemaps: list[GscSitemap] = Field(default_factory=list)
    rankings: KeywordRankings | None = None  # absent in audits stored before keyword rankings
    error: str | None = None


class FieldMetric(BaseModel):
    metric: Literal["lcp", "inp", "cls", "fcp", "ttfb"]
    p75: float | None = None
    rating: Literal["good", "needs-improvement", "poor"] | None = None
    good_share: float | None = None
    needs_improvement_share: float | None = None
    poor_share: float | None = None


class FieldData(BaseModel):
    """Real-user data (Chrome UX Report, 28-day p75). Public data; no site owner authorisation."""

    source: Literal["crux"] = "crux"
    scope: Literal["url", "origin"] | None = None
    form_factor: str | None = None  # PHONE | DESKTOP | None (all)
    period: dict[str, str] | None = None  # {first, last}
    metrics: list[FieldMetric] = Field(default_factory=list)
    error: str | None = None  # "no-data" when the site has too little traffic; "no-api-key"; ...


# --------------------------------------------------------------------------- audit record


class PageRecord(BaseModel):
    id: str
    url: str
    final_url: str | None = None
    status: int | None = None
    sample_kind: Literal["core", "exploration"] = "core"
    template_key: str | None = None
    html_bytes: int | None = None
    ttfb_ms: int | None = None
    error: str | None = None
    rendered: bool = False
    is_spa: bool | None = None
    js_gap: dict[str, Any] | None = None
    title: str | None = None
    word_count: int | None = None
    page_score: float | None = None


class StageRecord(BaseModel):
    stage: Stage
    status: StageStatus
    started_at: datetime | None = None
    finished_at: datetime | None = None
    detail: str | None = None


class AuditRecord(BaseModel):
    """Everything the report builder and the API need about one audit."""

    id: str
    mode: AuditMode
    target_url: str
    final_origin: str | None = None
    status: AuditStatus
    business_type: str | None = None
    lang: str | None = None
    created_at: datetime
    finished_at: datetime | None = None
    rule_version: str = "1.0"
    score_version: str = "mvp-0.1"
    parent_audit_id: str | None = None
    coverage: dict[str, Any] = Field(default_factory=dict)
    budget: dict[str, Any] = Field(default_factory=dict)
    cost: dict[str, Any] = Field(default_factory=dict)
    stages: list[StageRecord] = Field(default_factory=list)
    pages: list[PageRecord] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    not_checked: list[NotChecked] = Field(default_factory=list)
    scores: Scores | None = None
    advisory: list[AdvisoryRecord] = Field(default_factory=list)
    advice: list[AdviceRecord] = Field(default_factory=list)
    synthesis: SynthesisRecord | None = None
    links: LinkSummary | None = None
    perf: list[PagePerf] = Field(default_factory=list)
    indexability: list[IndexabilityRow] = Field(default_factory=list)
    visibility: VisibilitySignals | None = None
    gsc: GscData | None = None
    field: FieldData | None = None
    extras: dict[str, Any] = Field(
        default_factory=dict
    )  # blocks of pluggable analysis modules, by kind
    error: str | None = None
