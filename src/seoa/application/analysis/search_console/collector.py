"""Collect Search Console data for an audit and turn it into findings (belge 11 s.3.6).

``collect_gsc`` never raises: every failure becomes a ``GscData.status`` or a per-section
``error``, so a quota hit on URL Inspection still leaves the Performance numbers in the report.

URL Inspection quota is 2000 queries/day per property (600/min): an audit inspects the entry
URL plus at most ``inspect_limit`` sample URLs (default ``Settings.gsc_inspect_limit``).
"""

from __future__ import annotations

import asyncio
from typing import Any

from seoa.application.analysis.search_console import rules as rules_gsc  # noqa: F401  (registers rules and messages)
from seoa.application.analysis.search_console.property import resolve_property
from seoa.application.analysis.search_console.rankings import collect_rankings
from seoa.application.ports import GscError, SearchConsolePort
from seoa.domain import CheckOutput, GscData, GscInspection, GscRow, GscSitemap
from seoa.domain.rules.registry import make_finding
from seoa.domain.urls import url_key

TOTAL_TIMEOUT_S = 90.0
TOP_N = 20


def _row(r: dict[str, Any]) -> GscRow:
    keys = r.get("keys") or [""]
    return GscRow(
        key=str(keys[0]),
        clicks=int(r.get("clicks") or 0),
        impressions=int(r.get("impressions") or 0),
        ctr=float(r.get("ctr") or 0.0),
        position=float(r.get("position") or 0.0),
    )


def _inspection(url: str, result: dict[str, Any]) -> GscInspection:
    s = result.get("indexStatusResult")
    s = s if isinstance(s, dict) else {}
    coverage = s.get("coverageState")
    verdict = s.get("verdict")
    indexed: bool | None = None
    if isinstance(coverage, str):
        low = coverage.lower()
        indexed = "indexed" in low and "not indexed" not in low and "not-indexed" not in low
        if "currently not indexed" in low:
            indexed = False
    elif verdict == "PASS":
        indexed = True
    return GscInspection(
        url=url,
        verdict=verdict,
        coverage_state=coverage,
        indexing_state=s.get("indexingState"),
        robots_txt_state=s.get("robotsTxtState"),
        page_fetch_state=s.get("pageFetchState"),
        google_canonical=s.get("googleCanonical"),
        user_canonical=s.get("userCanonical"),
        last_crawl_time=s.get("lastCrawlTime"),
        crawled_as=s.get("crawledAs"),
        indexed=indexed,
    )


def _sitemap(s: dict[str, Any]) -> GscSitemap:
    return GscSitemap(
        path=str(s.get("path", "")),
        last_submitted=s.get("lastSubmitted"),
        last_downloaded=s.get("lastDownloaded"),
        is_pending=bool(s.get("isPending")),
        errors=int(s.get("errors") or 0),
        warnings=int(s.get("warnings") or 0),
    )


async def _inspect_all(
    client: SearchConsolePort, prop: str, urls: list[str]
) -> list[GscInspection]:
    sem = asyncio.Semaphore(3)

    async def one(u: str) -> GscInspection:
        async with sem:
            try:
                return _inspection(u, await client.inspect_url(prop, u))
            except GscError as exc:
                return GscInspection(url=u, error=exc.code)

    return list(await asyncio.gather(*(one(u) for u in urls)))


async def _collect(
    client: SearchConsolePort,
    entry_url: str,
    sample_urls: list[str],
    inspect_limit: int,
    days: int,
    keywords: list[str] | None = None,
) -> GscData:
    status = client.oauth.status(client.user_id)
    if not status["configured"]:
        return GscData(status="not-configured", period_days=days)
    if not status["connected"]:
        return GscData(status="not-connected", period_days=days)
    data = GscData(status="ok", account=status.get("email"), period_days=days)
    try:
        props = await client.list_properties()
    except GscError as exc:
        if exc.code == "not-connected":
            return GscData(status="not-connected", period_days=days)
        return GscData(status="error", account=data.account, period_days=days, error=exc.code)
    res = resolve_property(entry_url, props)
    if res.property is None:
        reason = "no-permission" if res.reason == "no-permission" else "property-not-found"
        return GscData(status=reason, account=data.account, period_days=days)  # type: ignore[arg-type]
    data.property, data.permission = res.property, res.permission
    prop = res.property

    urls: list[str] = []
    seen: set[str] = set()
    for u in [entry_url, *sample_urls][: inspect_limit + 1]:
        k = url_key(u)
        if k not in seen:
            seen.add(k)
            urls.append(u)

    async def perf() -> None:
        try:
            tot = await client.search_analytics(prop, days=days, row_limit=1)
            if tot:
                t = _row(tot[0])
                data.totals = {
                    "clicks": t.clicks,
                    "impressions": t.impressions,
                    "ctr": t.ctr,
                    "position": t.position,
                }
            else:
                data.totals = {"clicks": 0, "impressions": 0, "ctr": 0.0, "position": 0.0}
        except GscError as exc:
            data.error = data.error or f"performance: {exc.code}"
            return
        try:
            data.top_queries = [
                _row(r)
                for r in await client.search_analytics(
                    prop, days=days, dimensions=["query"], row_limit=TOP_N
                )
            ]
            data.top_pages = [
                _row(r)
                for r in await client.search_analytics(
                    prop, days=days, dimensions=["page"], row_limit=TOP_N
                )
            ]
        except GscError as exc:
            data.error = data.error or f"performance: {exc.code}"

    async def sitemaps() -> None:
        try:
            data.sitemaps = [_sitemap(s) for s in await client.list_sitemaps(prop)]
        except GscError as exc:
            data.error = data.error or f"sitemaps: {exc.code}"

    async def inspect() -> None:
        data.inspections = await _inspect_all(client, prop, urls)

    async def rankings() -> None:
        data.rankings = await collect_rankings(client, prop, keywords, days)

    await asyncio.gather(perf(), sitemaps(), inspect(), rankings())
    return data


async def collect_gsc(
    client: SearchConsolePort,
    *,
    entry_url: str,
    sample_urls: list[str],
    inspect_limit: int = 10,
    days: int = 28,
    keywords: list[str] | None = None,
) -> GscData:
    try:
        async with asyncio.timeout(TOTAL_TIMEOUT_S):
            return await _collect(client, entry_url, sample_urls, inspect_limit, days, keywords)
    except TimeoutError:
        return GscData(status="error", period_days=days, error="timeout")
    except Exception as exc:  # noqa: BLE001  one integration must never break the audit
        return GscData(
            status="error", period_days=days, error=f"internal-error: {type(exc).__name__}"
        )


def findings(gsc: GscData) -> CheckOutput:
    out = CheckOutput()
    if gsc.status != "ok":
        return out
    for i in gsc.inspections:
        if i.error:
            continue
        if i.indexed is False:
            out.findings.append(
                make_finding("gsc-page-not-indexed", url=i.url, evidence=i.coverage_state)
            )
        if (
            i.google_canonical
            and i.user_canonical
            and url_key(i.google_canonical) != url_key(i.user_canonical)
        ):
            out.findings.append(
                make_finding(
                    "gsc-canonical-mismatch",
                    url=i.url,
                    evidence=f"declared {i.user_canonical}; Google chose {i.google_canonical}",
                )
            )
        if (i.robots_txt_state or "").upper() == "DISALLOWED":
            out.findings.append(
                make_finding("gsc-robots-blocked", url=i.url, evidence=i.robots_txt_state)
            )
        fetch = (i.page_fetch_state or "").upper()
        if fetch and fetch not in ("SUCCESSFUL", "PAGE_FETCH_STATE_UNSPECIFIED"):
            out.findings.append(make_finding("gsc-fetch-failed", url=i.url, evidence=fetch))
    bad = [s for s in gsc.sitemaps if s.errors > 0]
    if bad:
        out.findings.append(
            make_finding(
                "gsc-sitemap-errors",
                evidence=f"{bad[0].path}: {bad[0].errors} errors",
                count=len(bad),
            )
        )
    if not gsc.sitemaps and "sitemaps" not in (gsc.error or ""):
        out.findings.append(make_finding("gsc-sitemap-not-submitted"))
    if (
        gsc.totals
        and gsc.totals.get("impressions", 1) == 0
        and "performance" not in (gsc.error or "")
    ):
        out.findings.append(
            make_finding(
                "gsc-no-impressions", evidence=f"{gsc.period_days} days", confidence="medium"
            )
        )
    out.facts["gsc_property"] = gsc.property
    return out
