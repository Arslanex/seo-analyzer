"""Keyword rankings from Search Console: collection, aggregation, report section (belge 12 B1)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import lxml.html

from seoa.application.analysis.search_console.collector import collect_gsc
from seoa.application.analysis.search_console.rankings import (
    MAX_KEYWORDS,
    _aggregate,
    clean_keywords,
    collect_rankings,
    opportunity_lists,
)
from seoa.application.reporting import build_report, check_report
from seoa.application.reporting.rankings import rankings_section
from seoa.domain import GscData, KeywordRankings
from seoa.infrastructure.integrations.google_oauth import HttpResult
from seoa.infrastructure.integrations.gsc import SITES_URL, GscClient
from seoa.presentation.web.html import render_report_html
from tests.support.fake_service import XSS_EVIDENCE, XSS_EVIDENCE_2, make_sample_record
from tests.support.google_support import FakeHttp, make_oauth

SITE = "sc-domain:example.com"
SITES = {"siteEntry": [{"siteUrl": SITE, "permissionLevel": "siteOwner"}]}


def _row(q: str, page: str | None, imp: int, clk: int, pos: float) -> dict[str, Any]:
    keys = [q] if page is None else [q, page]
    return {"keys": keys, "impressions": imp, "clicks": clk, "ctr": clk / imp, "position": pos}


def _client(tmp: Path, analytics: Any) -> tuple[GscClient, FakeHttp]:
    def h(m: str, u: str, kw: dict[str, Any]) -> HttpResult:
        if u == SITES_URL:
            return HttpResult(200, SITES)
        if "searchAnalytics" in u:
            return analytics(kw["json_body"])  # type: ignore[no-any-return]
        if u.endswith("/sitemaps"):
            return HttpResult(200, {})
        return HttpResult(200, {"inspectionResult": {}})

    http = FakeHttp(h)
    return GscClient(make_oauth(tmp, http, connected=True), http=http), http


def _filter(body: dict[str, Any]) -> str | None:
    groups = body.get("dimensionFilterGroups")
    return groups[0]["filters"][0]["expression"] if groups else None


# --------------------------------------------------------------------------- pure parts


def test_clean_keywords_dedupes_trims_and_caps() -> None:
    kws = clean_keywords(["  Widgets ", "widgets", "", "a  b"] + [f"k{i}" for i in range(20)])
    assert kws[:2] == ["Widgets", "a b"] and len(kws) == MAX_KEYWORDS
    assert clean_keywords(None) == []


def test_aggregate_prefers_exact_query_and_weights_position() -> None:
    rows = [
        _row("Widgets", "https://e.com/a", 100, 10, 4.0),
        _row("widgets", "https://e.com/b", 300, 30, 8.0),
        _row("buy widgets", "https://e.com/c", 9000, 90, 2.0),
    ]
    r = _aggregate("widgets", rows)
    assert r.status == "ok" and r.matched_query is None
    assert r.impressions == 400 and r.clicks == 40 and r.position == 7.0
    assert r.top_page == "https://e.com/b" and r.ctr == 0.1


def test_aggregate_falls_back_to_containing_query_and_names_it() -> None:
    rows = [
        _row("buy widgets", "https://e.com/c", 50, 1, 9.0),
        _row("big widgets", "https://e.com/d", 80, 2, 12.0),
    ]
    r = _aggregate("widgets", rows)
    assert r.matched_query == "big widgets" and r.impressions == 80


def test_aggregate_empty_is_no_data() -> None:
    assert _aggregate("x", []).status == "no-data"
    assert _aggregate("x", [{"keys": ["only-query"]}]).status == "no-data"


def test_turkish_dotted_i_is_not_folded_into_a_match_by_accident() -> None:
    r = _aggregate("istanbul", [_row("İstanbul otel", "https://e.com/", 10, 1, 3.0)])
    assert r.matched_query == "İstanbul otel"


def test_opportunity_and_low_ctr_rules() -> None:
    rows = [
        _row("close", None, 500, 15, 6.0),  # opportunity, CTR 3% is fine
        _row("page2", None, 200, 1, 15.0),  # opportunity
        _row("tiny", None, 10, 0, 6.0),  # too few impressions
        _row("top", None, 400, 40, 1.5),  # fine CTR (10%)
        _row("bad-top", None, 1000, 20, 2.0),  # 2% at position 2: low
        _row("bad-mid", None, 600, 3, 7.0),  # 0.5% at position 7: low
        _row("deep", None, 900, 9, 40.0),  # far away: neither
    ]
    opps, low = opportunity_lists(rows)
    assert [o.query for o in opps] == ["bad-mid", "close", "page2"]
    assert [q.query for q in low] == ["bad-top", "bad-mid"]


# --------------------------------------------------------------------------- collection


async def test_collect_rankings_request_budget_and_filters(tmp_path: Path) -> None:
    def analytics(body: dict[str, Any]) -> HttpResult:
        kw = _filter(body)
        if kw is None:
            return HttpResult(200, {"rows": [_row("close", None, 500, 5, 6.0)]})
        return HttpResult(200, {"rows": [_row(kw, "https://example.com/p", 100, 5, 3.0)]})

    c, http = _client(tmp_path, analytics)
    out = await collect_rankings(c, SITE, [f"kw{i}" for i in range(15)], 28)
    assert out.keywords_requested == MAX_KEYWORDS and len(out.rows) == MAX_KEYWORDS
    calls = [x for x in http.calls if "searchAnalytics" in x[1]]
    assert len(calls) == MAX_KEYWORDS + 1  # one per keyword + one opportunity query
    filtered = [x[2]["json_body"] for x in calls if "dimensionFilterGroups" in x[2]["json_body"]]
    assert all(b["dimensions"] == ["query", "page"] for b in filtered)
    assert all(
        b["dimensionFilterGroups"][0]["filters"][0]["operator"] == "contains" for b in filtered
    )
    assert [o.query for o in out.opportunities] == ["close"]


async def test_rate_limit_stops_remaining_keywords_without_crashing(tmp_path: Path) -> None:
    def analytics(body: dict[str, Any]) -> HttpResult:
        kw = _filter(body)
        if kw == "k0":
            return HttpResult(429)
        return HttpResult(200, {"rows": []})

    c, http = _client(tmp_path, analytics)
    out = await collect_rankings(c, SITE, ["k0", "k1", "k2", "k3", "k4", "k5"], 28)
    by = {r.keyword: r for r in out.rows}
    assert by["k0"].status == "error" and by["k0"].error == "rate-limited"
    assert any(r.error == "rate-limited" for r in out.rows)
    assert all(r.status in ("error", "no-data") for r in out.rows)


async def test_failing_opportunity_list_keeps_keyword_rows(tmp_path: Path) -> None:
    def analytics(body: dict[str, Any]) -> HttpResult:
        if _filter(body) is None:
            return HttpResult(500)
        return HttpResult(200, {"rows": [_row("kw", "https://example.com/", 10, 1, 5.0)]})

    c, _ = _client(tmp_path, analytics)
    out = await collect_rankings(c, SITE, ["kw"], 28)
    assert out.rows[0].status == "ok" and out.error == "http-500" and not out.opportunities


async def test_collect_gsc_attaches_rankings_and_works_without_keywords(tmp_path: Path) -> None:
    def analytics(body: dict[str, Any]) -> HttpResult:
        if _filter(body) is not None:
            return HttpResult(200, {"rows": [_row("seo", "https://example.com/", 90, 9, 4.0)]})
        return HttpResult(200, {"rows": [_row("seo", None, 90, 9, 4.0)]})

    c, _ = _client(tmp_path, analytics)
    d = await collect_gsc(c, entry_url="https://example.com/", sample_urls=[], keywords=["seo"])
    assert d.status == "ok" and d.rankings is not None
    assert d.rankings.rows[0].status == "ok" and d.rankings.rows[0].position == 4.0
    d2 = await collect_gsc(c, entry_url="https://example.com/", sample_urls=[])
    assert (
        d2.rankings is not None and d2.rankings.keywords_requested == 0 and d2.rankings.rows == []
    )


def test_old_gsc_blob_without_rankings_still_loads() -> None:
    d = GscData.model_validate_json('{"status": "ok", "period_days": 28}')
    assert d.rankings is None
    assert KeywordRankings.model_validate({}).rows == []


# --------------------------------------------------------------------------- report


def test_section_not_measured_states() -> None:
    off = rankings_section(make_sample_record("gated", gsc="not-connected"), "en")
    assert off.status == "not_measured" and off.not_measured_reason == "rankings-gsc-required"
    assert "cannot be measured reliably" in (off.not_measured_text or "")
    assert not off.rows and not off.opportunities
    none = rankings_section(make_sample_record("gated"), "tr")
    assert none.not_measured_reason == "rankings-gsc-required"
    bad = rankings_section(make_sample_record("gated", gsc="no-permission"), "en")
    assert bad.not_measured_reason == "gsc-no-permission"

    rec = make_sample_record("gated", gsc="ok")
    assert rec.gsc is not None
    rec.gsc.rankings = None
    assert rankings_section(rec, "en").not_measured_reason == "rankings-not-run"
    rec.gsc.rankings = KeywordRankings()
    assert rankings_section(rec, "en").not_measured_reason == "rankings-no-keywords"


def test_section_without_keywords_still_lists_opportunities() -> None:
    rec = make_sample_record("gated", gsc="ok")
    assert rec.gsc is not None and rec.gsc.rankings is not None
    rec.gsc.rankings.rows = []
    rec.gsc.rankings.keywords_requested = 0
    sec = rankings_section(rec, "en")
    assert sec.status == "measured" and sec.opportunities and sec.keywords_note


def test_section_measured_texts_and_statuses() -> None:
    sec = rankings_section(make_sample_record("gated", gsc="ok"), "en")
    assert sec.status == "measured" and sec.counts_toward_overall is False
    by = {r.keyword: r for r in sec.rows}
    assert by["widgets"].status == "ok" and by["widgets"].ctr_pct == 1.9
    assert "does not mean you do not rank" in by["rare thing"].status_text
    assert "rate limit" in by["limited"].status_text
    tr = rankings_section(make_sample_record("gated", gsc="ok"), "tr")
    assert (
        "sıralamadığınız anlamına gelmez"
        in {r.keyword: r for r in tr.rows}["rare thing"].status_text
    )


def test_html_has_section_nav_and_passes_the_quality_gate() -> None:
    report = build_report(make_sample_record("gated", gsc="ok"), "en")
    html = render_report_html(report, "en")
    root = lxml.html.fromstring(html)
    assert root.xpath("//section[@id='sec-rankings']//table")
    assert root.xpath("//a[@href='#sec-rankings']")
    q = check_report(report, html, lang="en")
    assert not [c for c in q.checks if c.status == "FAIL"]


def test_html_not_measured_card_has_no_table() -> None:
    report = build_report(make_sample_record("gated"), "en")
    root = lxml.html.fromstring(render_report_html(report, "en"))
    assert root.xpath("//section[@id='sec-rankings']//*[contains(@class,'nm')]")
    assert not root.xpath("//section[@id='sec-rankings']//table")


def test_attacker_controlled_query_text_is_escaped() -> None:
    rec = make_sample_record("gated", gsc="ok", xss=True)
    report = build_report(rec, "en")
    html = render_report_html(report, "en")
    assert XSS_EVIDENCE not in html and XSS_EVIDENCE_2 not in html
    q = check_report(report, html, lang="en", sentinels=[XSS_EVIDENCE, XSS_EVIDENCE_2])
    assert not [c for c in q.checks if c.status == "FAIL"]
