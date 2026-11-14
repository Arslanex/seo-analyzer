"""Thin adapters between the orchestrator and the check/crawl/render/LLM modules.

Everything the orchestrator needs from another module goes through here, so a
module's API change is fixed in one place and the orchestrator stays readable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from seoa.application.ports import FetcherLike
from seoa.config import Settings
from seoa.domain import (
    AdviceRecord,
    AdvisoryRecord,
    AuditRecord,
    CheckOutput,
    FetchResult,
    Finding,
    NotChecked,
    SynthesisRecord,
)

# ----------------------------------------------------------------------------- parsing & page checks


def parse(html: str, url: str) -> Any:
    from seoa.domain.parsing.html import parse_html

    return parse_html(html, url)


def run_page_checks(fr: FetchResult, parsed: Any, lang: str | None) -> CheckOutput:
    from seoa.domain.rules.page_checks import run_page_checks as _run

    return _run(fr, parsed, lang=lang)


def run_schema_checks(parsed: Any, url: str) -> CheckOutput:
    from seoa.domain.rules.schema_checks import run_schema_checks as _run

    return _run(parsed, url)


# ----------------------------------------------------------------------------- site checks


@dataclass
class RobotsView:
    available: bool
    findings: list[Finding] = field(default_factory=list)
    not_checked: list[NotChecked] = field(default_factory=list)
    sitemaps: list[str] = field(default_factory=list)
    raw: Any = None


async def run_robots(
    origin: str, entry_url: str, fetcher: FetcherLike, bot_name: str
) -> RobotsView:
    from seoa.application.site.robots import run_robots_checks

    res = await run_robots_checks(origin, entry_url, fetcher, bot_name)
    return RobotsView(
        available=res.status != "unreachable",
        findings=list(res.output.findings),
        not_checked=list(res.output.not_checked),
        sitemaps=list(res.sitemaps),
        raw=res,
    )


def robots_allows(view: RobotsView, bot_name: str, url: str) -> bool:
    from seoa.application.site.robots import can_fetch

    if not view.available or view.raw is None:
        return True  # RFC 9309 treats 5xx as "disallow all", but the entry URL itself was already fetched
    return can_fetch(view.raw.rules, bot_name, url)


@dataclass
class SitemapView:
    urls: list[Any]
    findings: list[Finding]
    not_checked: list[NotChecked]
    found: bool


async def discover_sitemaps(
    origin: str, fetcher: FetcherLike, robots_sitemaps: list[str]
) -> SitemapView:
    from seoa.application.crawl.sitemap import discover_sitemaps as _d

    res = await _d(origin, fetcher, robots_sitemaps)
    return SitemapView(
        list(res.urls), list(res.output.findings), list(res.output.not_checked), res.found
    )


async def run_transport(entry_url: str, fr: FetchResult, fetcher: FetcherLike) -> CheckOutput:
    from seoa.infrastructure.http.transport import run_transport_checks

    return await run_transport_checks(entry_url, fr, fetcher)


# ----------------------------------------------------------------------------- rendering


def is_spa(html: str | None) -> bool:
    from seoa.infrastructure.rendering.spa import is_spa as _is

    return _is(html)


def js_gap(raw: str, rendered: str) -> dict[str, Any] | None:
    from seoa.infrastructure.rendering.js_gap import js_gap as _g

    g = _g(raw, rendered)
    if g is None:
        return None
    d = g.to_dict()
    d["gap"] = bool(g.significant)
    return d


def js_gap_reasons(gap: dict[str, Any]) -> list[str]:
    return list(gap.get("reasons", []))


async def render(renderer: Any, url: str) -> Any:
    return await renderer.render(url)


# ----------------------------------------------------------------------------- layer C


class LLMProvider:
    """Hands out a per-audit LLMClient (budget scope = audit id)."""

    def __init__(
        self, settings: Settings, *, transport: Any = None, audit_cap_usd: float = 0.75
    ) -> None:
        self.settings = settings
        self._transport = transport
        self.audit_cap = audit_cap_usd

    def for_audit(self, aid: str) -> Any:
        from seoa.infrastructure.llm.client import LLMClient

        return LLMClient(
            settings=self.settings, transport=self._transport, scope=aid, scope_cap=self.audit_cap
        )

    def spent(self, aid: str | None = None) -> float:
        from seoa.infrastructure.llm.budget import BudgetGuard

        return BudgetGuard().spent(aid)

    def snapshot(self) -> dict[str, float]:
        from seoa.infrastructure.llm.budget import BudgetGuard

        return BudgetGuard().snapshot()


async def answer_question(
    provider: LLMProvider, audit_id: str, report: dict[str, Any], question: str, lang: str
) -> Any:
    """Answer a question about a finished audit (grounded in its report, with citations)."""
    from seoa.infrastructure.llm.qa import answer_question as _answer

    return await _answer(provider.for_audit(f"qa-{audit_id}"), report, question, lang)


async def llm_ping(provider: LLMProvider | None) -> str:
    """One tiny real call with the saved key: ok | missing | rejected | rate-limited |
    unreachable | budget | other. Costs a fraction of a cent and is recorded in the ledger."""
    import uuid

    from pydantic import BaseModel

    from seoa.infrastructure.llm.budget import BudgetExceeded
    from seoa.infrastructure.llm.client import LLMUnavailable

    class _Ping(BaseModel):
        ok: bool

    if provider is None:
        return "missing"
    try:
        await provider.for_audit("settings-test").call_structured(
            "ping",
            "Answer with ok set to true.",
            "ping",
            _Ping,
            max_tokens=40,
            cache_key_parts=(uuid.uuid4().hex,),  # never answered from the cache
        )
    except BudgetExceeded:
        return "budget"
    except LLMUnavailable as exc:
        text = str(exc)
        if "Authentication" in text or "PermissionDenied" in text:
            return "rejected"
        if "RateLimit" in text:
            return "rate-limited"
        if "Connection" in text or "Timeout" in text:
            return "unreachable"
        return "other"
    return "ok"


async def fetch_authority(host: str, key: str) -> Any:
    """Domain authority estimate from OpenPageRank (a third-party number, never scored)."""
    from seoa.infrastructure.integrations.openpagerank import fetch_authority as _fetch

    return await _fetch(host, key=key)


def _ai_facts(ctx: dict[str, Any]) -> dict[str, Any]:
    robots = ctx["robots"].raw
    crawlers = [
        {
            "token": c.token,
            "capability": c.capability,
            "root_allowed": c.root_allowed,
            "group": c.group,
        }
        for c in (getattr(robots, "ai_crawlers", []) or [])
    ]
    entry = ctx["pages"].get(ctx["entry_url"])
    return {
        "ai_crawlers": crawlers,
        "llms_txt_present": getattr(robots, "llms_txt_present", None),
        "js_dependent": bool(entry and entry.js_gap and entry.js_gap.get("gap")),
        "is_spa": bool(entry and entry.is_spa),
    }


def _llm_pages(ctx: dict[str, Any], limit: int) -> list[str]:
    """Entry page first, then one representative per template (core pages with usable HTML)."""
    chosen = [ctx["entry_url"]]
    seen = {ctx["pages"][ctx["entry_url"]].template_key}
    for url, p in ctx["pages"].items():
        if len(chosen) >= limit:
            break
        fr = ctx["fetches"].get(url)
        if (
            url in chosen
            or p.sample_kind != "core"
            or not fr
            or not fr.html
            or (fr.status or 0) >= 400
        ):
            continue
        if p.template_key in seen:
            continue
        seen.add(p.template_key)
        chosen.append(url)
    return chosen


async def run_advisory(
    provider: LLMProvider, ctx: dict[str, Any], settings: Settings, aid: str
) -> list[AdvisoryRecord]:
    from seoa.infrastructure.llm.ai_readiness import run_ai_commentary
    from seoa.infrastructure.llm.eeat import run_eeat
    from seoa.infrastructure.llm.input import build_content_input

    client = provider.for_audit(aid)
    lang_out = ctx["opts"].get("lang", "tr")
    out: list[AdvisoryRecord] = []
    for i, url in enumerate(_llm_pages(ctx, settings.llm_max_pages)):
        fr = ctx["fetches"][url]
        html = ctx.get("rendered", {}).get(url) or fr.html or ""
        parsed = ctx["parsed"].get(url)
        facts = {
            "https": fr.final_url.startswith("https://"),
            "word_count": getattr(parsed, "word_count", None),
            "schema_types": getattr(parsed, "schema_types", []),
            "status": fr.status,
        }
        ci = build_content_input(html, fr.final_url, fr.headers, lang=ctx.get("lang"), facts=facts)
        rec = await run_eeat(client, ci, output_language=lang_out, today=datetime.now(UTC).date())
        out.append(rec.model_copy(update={"page_url": url}))
        if i == 0:
            com = await run_ai_commentary(client, ci, _ai_facts(ctx), output_language=lang_out)
            out.append(com.model_copy(update={"page_url": url}))
    return out


def category_label(cat: str, lang: str) -> str:
    """Human label in the output language: the model must not translate raw keys like "onpage"."""
    from seoa.domain.i18n import t

    return t(lang, f"cat.{cat}")


def _scores_summary(ctx: dict[str, Any]) -> dict[str, Any]:
    sc = ctx["scores"]
    lang = ctx["opts"].get("lang", "tr")
    return {
        "overall": sc.overall,
        "coverage_pct": sc.coverage_pct,
        "insufficient_data": sc.insufficient_data,
        "gate": sc.gate.model_dump() if sc.gate else None,
        "categories": [
            {
                "category": c.category.value,
                "label": category_label(c.category.value, lang),
                "score": c.score,
                "measured": c.measured,
            }
            for c in sc.categories
        ],
    }


async def run_synthesis(
    provider: LLMProvider,
    ctx: dict[str, Any],
    top_findings: list[dict[str, Any]],
    lang: str,
    aid: str,
) -> tuple[SynthesisRecord, list[AdviceRecord]]:
    from seoa.infrastructure.llm.synthesize import run_synthesis as _run

    client = provider.for_audit(aid)
    return await _run(
        client, scores_summary=_scores_summary(ctx), findings=top_findings, output_language=lang
    )


async def llm_cost(provider: LLMProvider, aid: str) -> dict[str, Any]:
    return {"llm_usd": round(provider.spent(aid), 6)}


# ----------------------------------------------------------------------------- report gate


async def validate_report(rec: AuditRecord) -> None:
    """Final gate: the stored record must build a valid report (FAIL blocks, WARN is tolerated)."""
    from seoa.application.reporting.builder import build_report
    from seoa.application.reporting.quality import check_report

    report = build_report(rec, "en")
    q = check_report(report)
    if q.status == "FAIL":
        bad = [f"{c.id}: {c.detail}" for c in q.checks if c.status == "FAIL"][:3]
        raise RuntimeError(f"report quality gate failed: {bad}")


# ----------------------------------------------------------------------------- deep analysis (belge 11)


def analysis_pages(ctx: dict[str, Any]) -> list[Any]:
    from seoa.application.analysis.types import AnalysisPage

    out = []
    for url, page in ctx["pages"].items():
        fr = ctx["fetches"].get(url)
        out.append(
            AnalysisPage(
                url=url,
                final_url=page.final_url,
                status=page.status,
                headers=dict(fr.headers) if fr else {},
                parsed=ctx.get("parsed", {}).get(url),
                sample_kind=page.sample_kind,
                error=page.error,
            )
        )
    return out


async def run_links(
    pages: list[Any], ctx: dict[str, Any], fetcher: FetcherLike, settings: Settings
) -> Any:
    from seoa.application.analysis.links.graph import analyze_links

    robots = ctx["robots"].raw
    return await analyze_links(
        pages,
        entry_url=ctx["entry_url"],
        sitemap_urls=ctx.get("sitemap_set", set()),
        fetcher=fetcher,
        robots_rules=getattr(robots, "rules", None),
        bot_name=settings.bot_name,
        mode=ctx["mode"].value,
        max_external_checks=settings.max_external_link_checks,
    )


def build_indexability(
    pages: list[Any], ctx: dict[str, Any], link_stats: dict[str, Any], settings: Settings
) -> list[Any]:
    from seoa.application.analysis.links.indexability import build_indexability as _b

    robots = ctx["robots"].raw
    return _b(
        pages,
        sitemap_urls=ctx.get("sitemap_set", set()),
        link_stats=link_stats,
        robots_rules=getattr(robots, "rules", None),
        bot_name=settings.bot_name,
    )


def find_duplicates(pages: list[Any]) -> CheckOutput:
    from seoa.application.analysis.links.duplicates import find_duplicates as _f

    return _f(pages)


async def collect_visibility(domain: str) -> Any:
    from seoa.infrastructure.integrations.visibility import collect_visibility as _c

    return await _c(domain)


async def measure_perf(renderer: Any, targets: list[tuple[str, str]]) -> list[Any]:
    """Lab measurement of (url, device) pairs; the renderer limits concurrency itself."""
    import asyncio

    from seoa.infrastructure.rendering.perf import measure_page

    return list(await asyncio.gather(*(measure_page(renderer, u, device=d) for u, d in targets)))  # type: ignore[arg-type]


def perf_checks(perfs: list[Any]) -> CheckOutput:
    from seoa.application.analysis.performance.checks import perf_checks as _p

    return _p(perfs)


async def run_psi(url: str) -> CheckOutput | None:
    from seoa.infrastructure.integrations.psi import run_psi as _run

    return await _run(url)


async def run_crux(url: str, origin: str) -> Any:
    from seoa.infrastructure.integrations.crux import fetch_crux

    return await fetch_crux(url, origin)


def field_checks(field: Any, url: str) -> CheckOutput:
    from seoa.infrastructure.integrations.crux import field_checks as _f

    return _f(field, url)


def google_api_key() -> str | None:
    from seoa.infrastructure.integrations.psi import api_key

    return api_key()
