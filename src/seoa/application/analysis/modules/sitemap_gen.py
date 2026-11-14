"""Suggested sitemap.xml (belge 12 C5), site audits only.

Built from the sampled pages that are fit for a sitemap: HTTP 200, reached without a redirect
(the URL is the final URL), no ``noindex`` (meta robots/googlebot or ``X-Robots-Tag``), and a
canonical that names the page itself (or none). ``<lastmod>`` is written only when the server sent
a ``Last-Modified`` header: no date is invented. At most 50 000 URLs (the protocol limit).

The sample is a SAMPLE (at most the audit's page limit): the file lists what was seen, not the
whole site, and the comparison with the site's existing sitemap is limited the same way. Pages
blocked by robots.txt are NOT excluded here (the audit's own indexability table covers that).

No findings: this is data for the report (a copy-paste draft and a download).
"""

from __future__ import annotations

from datetime import UTC
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin
from xml.sax.saxutils import escape

from pydantic import BaseModel, Field

from seoa.application.analysis.links.indexability import (
    _meta_noindex,
    _same_page,
    header_directives,
)
from seoa.application.analysis.plugin import AnalysisInputs, ModuleResult, register_module
from seoa.application.analysis.types import AnalysisPage
from seoa.domain import AuditMode, NotChecked
from seoa.domain.urls import url_key

MAX_URLS = 50_000
LIST_CAP = 100
NS = "http://www.sitemaps.org/schemas/sitemap/0.9"


class ExcludedPage(BaseModel):
    url: str
    reason: str  # stable code: status-4xx, status-5xx, redirected, noindex, noindex-header, canonical-elsewhere, fetch-error


class SitemapGenerated(BaseModel):
    xml: str = ""
    urls_total: int = 0
    urls: list[str] = Field(default_factory=list)  # first LIST_CAP, in file order
    with_lastmod: int = 0
    existing_sitemap: bool = False
    missing_from_sitemap: list[str] = Field(default_factory=list)  # fit for a sitemap, not in yours
    missing_total: int = 0
    in_sitemap_not_indexable: list[ExcludedPage] = Field(default_factory=list)
    in_sitemap_not_indexable_total: int = 0
    excluded: list[ExcludedPage] = Field(default_factory=list)
    excluded_total: int = 0
    pages_in_sample: int = 0
    sample_limited: bool = True
    truncated: bool = False


def _lastmod(headers: dict[str, str]) -> str | None:
    raw = headers.get("last-modified", "").strip()
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).strftime("%Y-%m-%d")


def exclusion_reason(p: AnalysisPage) -> str | None:
    """Why this page does not belong in a sitemap; None when it does."""
    if p.error or p.status is None:
        return "fetch-error"
    if p.status >= 500:
        return "status-5xx"
    if p.status >= 400:
        return "status-4xx"
    if p.status != 200:
        return "redirected"
    if p.final_url and url_key(p.final_url) != url_key(p.url):
        return "redirected"
    if _meta_noindex(p):
        return "noindex"
    xrt = p.headers.get("x-robots-tag", "")
    if xrt and header_directives(xrt) & {"noindex", "none"}:
        return "noindex-header"
    if p.parsed is not None and p.parsed.canonical:
        canonical = urljoin(p.effective_url, p.parsed.canonical)
        if not (_same_page(canonical, p.effective_url) or _same_page(canonical, p.url)):
            return "canonical-elsewhere"
    return None


def render_xml(entries: list[tuple[str, str | None]]) -> str:
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', f'<urlset xmlns="{NS}">']
    for url, lastmod in entries:
        lines.append("  <url>")
        lines.append(f"    <loc>{escape(url)}</loc>")
        if lastmod:
            lines.append(f"    <lastmod>{lastmod}</lastmod>")
        lines.append("  </url>")
    lines.append("</urlset>")
    return "\n".join(lines) + "\n"


def build_sitemap(pages: list[AnalysisPage], sitemap_urls: set[str]) -> SitemapGenerated:
    out = SitemapGenerated(existing_sitemap=bool(sitemap_urls))
    sm_keys = {url_key(u) for u in sitemap_urls}
    entries: list[tuple[str, str | None]] = []
    seen: set[str] = set()
    excluded: list[ExcludedPage] = []
    not_indexable: list[ExcludedPage] = []
    missing: list[str] = []
    for p in pages:
        key = url_key(p.effective_url)
        if key in seen:
            continue
        seen.add(key)
        out.pages_in_sample += 1
        reason = exclusion_reason(p)
        in_sm = url_key(p.url) in sm_keys or key in sm_keys
        if reason is not None:
            excluded.append(ExcludedPage(url=p.url, reason=reason))
            if in_sm:
                not_indexable.append(ExcludedPage(url=p.url, reason=reason))
            continue
        if len(entries) >= MAX_URLS:
            out.truncated = True
            continue
        lm = _lastmod(p.headers)
        entries.append((p.effective_url, lm))
        if sm_keys and not in_sm:
            missing.append(p.effective_url)
    entries.sort(key=lambda e: e[0])
    out.xml = render_xml(entries)
    out.urls_total = len(entries)
    out.urls = [u for u, _ in entries[:LIST_CAP]]
    out.with_lastmod = sum(1 for _, lm in entries if lm)
    out.missing_total = len(missing)
    out.missing_from_sitemap = missing[:LIST_CAP]
    out.in_sitemap_not_indexable_total = len(not_indexable)
    out.in_sitemap_not_indexable = not_indexable[:LIST_CAP]
    out.excluded_total = len(excluded)
    out.excluded = excluded[:LIST_CAP]
    return out


class SitemapGenModule:
    name = "sitemap_gen"
    kind = "sitemap_generated"
    timeout_s = 15.0

    async def run(self, inp: AnalysisInputs) -> ModuleResult:
        if inp.mode != AuditMode.SITE:
            return ModuleResult(
                kind=self.kind,
                not_checked=[NotChecked(check_id=self.kind, reason_code="site-mode-only")],
            )
        data = build_sitemap(inp.pages, inp.sitemap_urls)
        if data.urls_total == 0:
            return ModuleResult(
                kind=self.kind,
                not_checked=[NotChecked(check_id=self.kind, reason_code="no-eligible-pages")],
            )
        return ModuleResult(kind=self.kind, data=data)


register_module(SitemapGenModule())

__all__ = [
    "SitemapGenModule",
    "SitemapGenerated",
    "build_sitemap",
    "exclusion_reason",
    "render_xml",
]
