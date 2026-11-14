"""Indexability table (belge 11 s.3.4): can this page be indexed, and if not, why?

Pure function over what the audit already fetched. It answers the *measurable* half of "why
does my site not show up": is anything on the page or in the response blocking indexing? It
does NOT say whether a page *is* indexed (that needs Search Console).

Reasons (a page with any of them is not indexable):
``noindex`` (robots/googlebot meta), ``noindex-header`` (X-Robots-Tag), ``canonical-elsewhere``,
``blocked-by-robots``, ``status-4xx``, ``status-5xx``, ``fetch-error``.

A canonical that differs from the page only by trailing slash, ``www.`` or scheme names the
same page and is not a problem.
"""

from __future__ import annotations

from urllib.parse import urljoin, urlparse

from seoa.application.analysis.types import AnalysisPage
from seoa.application.site.robots import RobotsRules, can_fetch
from seoa.domain import IndexabilityRow, PageLinkStats
from seoa.domain.parsing.html import url_match_key
from seoa.domain.urls import url_key

_VALUED_DIRECTIVES = frozenset(
    {"max-snippet", "max-image-preview", "max-video-preview", "unavailable_after"}
)
_APPLIES = frozenset({"", "googlebot"})


def header_directives(value: str) -> set[str]:
    """Directives of an X-Robots-Tag value that apply to everyone or to Googlebot.

    ``"noindex, googlebot: nofollow, bingbot: noindex"`` -> ``{"noindex", "nofollow"}``.
    A token ``agent: directive`` switches the agent for the tokens that follow it.
    """
    agent = ""
    out: set[str] = set()
    for token in value.lower().split(","):
        token = token.strip()
        if not token:
            continue
        if ":" in token:
            left, _, right = token.partition(":")
            left, right = left.strip(), right.strip()
            if left in _VALUED_DIRECTIVES:
                continue  # max-snippet:20 and friends carry a value, not an agent
            agent, token = left, right
        if agent in _APPLIES and token:
            out.add(token)
    return out


def _meta_noindex(page: AnalysisPage) -> bool:
    if page.parsed is None:
        return False
    for name, _prop, content in page.parsed.meta_tags:
        if name.lower() in ("robots", "googlebot"):
            tokens = {t.strip().lower() for t in content.split(",")}
            if tokens & {"noindex", "none"}:
                return True
    return False


def _same_page(a: str, b: str) -> bool:
    """Equal after ignoring trailing slash, ``www.`` and scheme."""

    def norm(u: str) -> str:
        p = urlparse(url_match_key(u))
        host = p.hostname or ""
        host = host[4:] if host.startswith("www.") else host
        port = f":{p.port}" if p.port and p.port not in (80, 443) else ""
        return f"{host}{port}{p.path}?{p.query}"

    return norm(a) == norm(b)


def build_indexability(
    pages: list[AnalysisPage],
    *,
    sitemap_urls: set[str],
    link_stats: dict[str, PageLinkStats],
    robots_rules: RobotsRules | None,
    bot_name: str,
) -> list[IndexabilityRow]:
    sm_keys = {url_key(u) for u in sitemap_urls}
    stats_by_key = {url_key(u): s for u, s in link_stats.items()}
    rows: list[IndexabilityRow] = []
    for p in pages:
        reasons: list[str] = []
        if p.error or p.status is None:
            reasons.append("fetch-error")
        elif p.status >= 500:
            reasons.append("status-5xx")
        elif p.status >= 400:
            reasons.append("status-4xx")
        if _meta_noindex(p):
            reasons.append("noindex")
        xrt = p.headers.get("x-robots-tag", "")
        if xrt and header_directives(xrt) & {"noindex", "none"}:
            reasons.append("noindex-header")
        canonical: str | None = None
        if p.parsed is not None and p.parsed.canonical:
            canonical = urljoin(p.effective_url, p.parsed.canonical)
            if not (_same_page(canonical, p.effective_url) or _same_page(canonical, p.url)):
                reasons.append("canonical-elsewhere")
        if robots_rules is not None and not can_fetch(robots_rules, bot_name or "*", p.url):
            reasons.append("blocked-by-robots")
        st = link_stats.get(p.url) or stats_by_key.get(url_key(p.url))
        rows.append(
            IndexabilityRow(
                url=p.url,
                status=p.status,
                indexable=not reasons,
                reasons=reasons,
                canonical=canonical,
                in_sitemap=(
                    (url_key(p.url) in sm_keys or url_key(p.effective_url) in sm_keys)
                    if sm_keys
                    else None
                ),
                inlinks=st.inlinks if st else None,
                depth=st.depth if st else None,
            )
        )
    return rows
