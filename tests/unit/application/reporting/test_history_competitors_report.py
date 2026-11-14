"""C1/C2 in the report and the API: history, comparison, site audit list, competitors section."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path

import httpx
import lxml.html
import pytest

from seoa.application.analysis.modules.competitors import CompetitorComparison, CompetitorRow
from seoa.application.audit.protocol import AuditSummary
from seoa.application.reporting import build_report, check_report
from seoa.application.reporting.history import HistoryInput, history_section, pick_previous
from seoa.application.rules_loader import load_all_rules
from seoa.bootstrap import build_local_service
from seoa.config import Settings
from seoa.domain import AuditMode, AuditRecord, AuditStatus, NotChecked
from seoa.domain.i18n import missing_keys
from seoa.infrastructure.persistence import Repo
from seoa.presentation.api import create_app
from seoa.presentation.web.html import render_report_html
from tests.support.fake_service import FakeService, make_sample_record

XSS = '<script>alert("c1")</script>'
AUD = "aud_sample0001"


def _rec(aid: str, minutes: int = 0, **kw: object) -> AuditRecord:
    load_all_rules()
    rec = make_sample_record("gated", audit_id=aid)
    rec.created_at = rec.created_at + timedelta(minutes=minutes)
    for k, v in kw.items():
        setattr(rec, k, v)
    return rec


def _summary(rec: AuditRecord) -> AuditSummary:
    return AuditSummary(
        id=rec.id,
        target_url=rec.target_url,
        mode=rec.mode,
        status=rec.status,
        overall=rec.scores.overall if rec.scores else None,
        coverage_pct=rec.scores.coverage_pct if rec.scores else None,
        created_at=rec.created_at,
    )


def test_catalog_parity() -> None:
    assert missing_keys() == set()


# --------------------------------------------------------------------------- history


def test_history_without_input_or_with_a_single_audit_says_why() -> None:
    rec = _rec("a")
    assert history_section(rec, "en", None).not_measured_reason == "history-unavailable"
    only = HistoryInput(entries=[_summary(rec)])
    sec = history_section(rec, "en", only)
    assert sec.status == "not_measured" and sec.not_measured_reason == "first-audit"
    assert sec.rows == [] and (sec.not_measured_text or "").strip()


def test_pick_previous_takes_the_closest_older_finished_scored_audit_of_the_same_mode() -> None:
    cur, failed, other_mode, good, older = (
        _rec("cur", 50),
        _rec("failed", 40, status=AuditStatus.FAILED),
        _rec("other", 30, mode=AuditMode.PAGE),
        _rec("good", 20),
        _rec("older", 10),
    )
    cur.mode = good.mode = older.mode = failed.mode = AuditMode.SITE
    entries = [_summary(r) for r in (cur, failed, other_mode, good, older)]
    assert pick_previous("cur", "site", entries) == "good"
    assert pick_previous("older", "site", entries) is None
    assert pick_previous("unknown", "site", entries) is None


def test_history_section_has_rows_and_a_comparison() -> None:
    old, new = _rec("old", 0), _rec("new", 10)
    old.scores.overall = 50.0  # type: ignore[union-attr]
    new.scores.overall = 62.0  # type: ignore[union-attr]
    hist = HistoryInput(entries=[_summary(new), _summary(old)], previous=old)
    sec = history_section(new, "en", hist)
    assert sec.status == "measured" and sec.previous_id == "old"
    assert [r.is_current for r in sec.rows] == [True, False]
    overall = sec.scores[0]
    assert (overall.old, overall.new, overall.delta, overall.direction) == (
        "50",
        "62",
        "+12",
        "better",
    )
    assert sec.counts_toward_overall is False


def test_history_with_different_score_versions_shows_a_warning_and_no_numbers() -> None:
    old, new = _rec("old", 0), _rec("new", 10)
    old.scores.score_version = "mvp-0.1"  # type: ignore[union-attr]
    sec = history_section(new, "tr", HistoryInput([_summary(new), _summary(old)], old))
    assert sec.warning_text and sec.scores == []


def test_history_rows_are_capped_and_the_current_audit_stays_in() -> None:
    recs = [_rec(f"r{i}", i) for i in range(15)]
    cur = recs[0]  # the oldest: it falls outside the newest 10 but must be listed
    entries = [_summary(r) for r in sorted(recs, key=lambda r: r.created_at, reverse=True)]
    sec = history_section(cur, "en", HistoryInput(entries=entries))
    assert len(sec.rows) == 10 and sec.rows_total == 15 and sec.truncated
    assert any(r.is_current for r in sec.rows)


def test_history_html_is_clean_and_quality_gate_passes() -> None:
    old, new = _rec("old", 0), _rec("new", 10)
    hist = HistoryInput(entries=[_summary(new), _summary(old)], previous=old)
    for lang in ("tr", "en"):
        report = build_report(new, lang, history=hist)
        html = render_report_html(report, lang)
        quality = check_report(report, html, lang=lang)
        assert not [c for c in quality.checks if c.status == "FAIL"], quality
        root = lxml.html.fromstring(html)
        assert root.xpath("//section[@id='sec-history']//table")
        assert root.xpath("//nav[@class='secnav']//a[@href='#sec-history']")
        assert root.xpath("//button[@data-action-post and @data-modules='all']")
        assert "/audits/old/report" in html


def test_rescan_button_is_not_in_the_static_report() -> None:
    rec = _rec("a")
    html = render_report_html(build_report(rec, "en"), "en", interactive=False)
    assert 'data-modules="all"' not in html


def test_history_findings_are_escaped() -> None:
    old, new = _rec("old", 0), _rec("new", 10)
    assert new.findings
    new.findings[0].url = f"https://example.com/{XSS}"
    old.findings = []
    hist = HistoryInput(entries=[_summary(new), _summary(old)], previous=old)
    report = build_report(new, "en", history=hist)
    html = render_report_html(report, "en")
    assert XSS not in html
    assert not [c for c in check_report(report, html, lang="en").checks if c.status == "FAIL"]


# --------------------------------------------------------------------------- competitors


def _comp_record(**row: object) -> AuditRecord:
    base = dict(url="https://rival.example/", host="rival.example", status=200, score=70.0)
    data = CompetitorComparison(
        you=CompetitorRow(url="https://example.com/", host="example.com", is_you=True, status=200),
        rows=[CompetitorRow(**{**base, **row})],  # type: ignore[arg-type]
    )
    return _rec("c", extras={"competitors": data.model_dump()})


def test_competitors_not_measured_reasons() -> None:
    rec = _rec("c")
    sec = build_report(rec, "en").competitors
    assert sec.status == "not_measured" and sec.not_measured_reason == "suite-no-data"
    rec.not_checked.append(NotChecked(check_id="competitors", reason_code="no-competitors"))
    sec = build_report(rec, "tr").competitors
    assert sec.not_measured_reason == "no-competitors" and "3" in (sec.not_measured_text or "")


def test_competitors_table_puts_you_first_and_never_changes_the_score() -> None:
    plain = _rec("p")
    rec = _comp_record(tech=["WordPress"], schema_types=["Organization"], title_len=30, h1_count=1)
    a, b = build_report(plain, "en"), build_report(rec, "en")
    assert a.scores.overall.value == b.scores.overall.value
    sec = b.competitors
    assert sec.status == "measured"
    assert [c.is_you for c in sec.columns] == [True, False]
    assert all(len(c.values) == len(sec.metrics) for c in sec.columns)
    html = render_report_html(b, "en")
    root = lxml.html.fromstring(html)
    assert root.xpath("//section[@id='sec-competitors']//th[contains(@class,'you')]")
    assert "rival.example" in html and "WordPress" in html
    assert not [c for c in check_report(b, html, lang="en").checks if c.status == "FAIL"]


def test_competitor_text_from_the_page_is_escaped() -> None:
    rec = _comp_record(host=XSS, tech=[XSS], schema_types=[XSS], url=f"https://x.example/{XSS}")
    report = build_report(rec, "en")
    html = render_report_html(report, "en")
    assert XSS not in html
    assert not [c for c in check_report(report, html, lang="en").checks if c.status == "FAIL"]


def test_competitor_error_row_explains_itself() -> None:
    rec = _comp_record(error="target-rejected", status=None, score=None)
    col = build_report(rec, "en").competitors.columns[1]
    assert col.note and "safety" in col.note


# --------------------------------------------------------------------------- API


@pytest.fixture
def service() -> FakeService:
    svc = FakeService()
    old = _rec("aud_old", 0, target_url="https://example.com/")
    new = _rec("aud_new", 10, target_url="https://www.example.com/")
    svc.add(old)
    svc.add(new)
    svc.add(_rec("aud_other", 5, target_url="https://notexample.com/"))
    return svc


@pytest.fixture
async def client(service: FakeService) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(service)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as c:
        yield c


async def test_site_audits_lists_the_same_host_only(client: httpx.AsyncClient) -> None:
    r = await client.get("/v1/sites/example.com/audits")
    ids = [a["id"] for a in r.json()["data"]]
    assert "aud_new" in ids and "aud_old" in ids and "aud_other" not in ids
    assert ids.index("aud_new") < ids.index("aud_old")  # newest first
    assert (await client.get("/v1/sites/bad%20host/audits")).status_code == 422


async def test_compare_endpoint(client: httpx.AsyncClient) -> None:
    r = await client.get("/v1/audits/aud_new/compare/aud_old")
    assert r.status_code == 200
    b = r.json()
    assert b["old_id"] == "aud_old" and b["new_id"] == "aud_new" and b["comparable"] is True
    assert b["overall"]["delta"] == 0
    assert (await client.get("/v1/audits/aud_new/compare/nope")).status_code == 404
    other = await client.get("/v1/audits/aud_new/compare/aud_other")
    assert other.status_code == 422 and other.json()["code"] == "not-same-site"


async def test_report_shows_history_and_the_endpoint_matches(client: httpx.AsyncClient) -> None:
    html = (await client.get("/v1/audits/aud_new/report?format=html&lang=en")).text
    root = lxml.html.fromstring(html)
    assert root.xpath("//section[@id='sec-history']//table")
    b = (await client.get("/v1/audits/aud_new/history?lang=en")).json()
    assert b["status"] == "measured" and b["previous_id"] in ("aud_old", AUD)


async def test_first_audit_of_a_site_has_no_history(client: httpx.AsyncClient) -> None:
    b = (await client.get("/v1/audits/aud_other/history?lang=en")).json()
    assert b["status"] == "not_measured" and b["not_measured_reason"] == "first-audit"


async def test_competitors_endpoint(client: httpx.AsyncClient) -> None:
    b = (await client.get(f"/v1/audits/{AUD}/competitors?lang=en")).json()
    assert b["status"] == "not_measured"


# --------------------------------------------------------------------------- repo and service


async def test_repo_site_audits_match_the_host_exactly(tmp_path: Path) -> None:
    repo = Repo(tmp_path / "t.sqlite", tmp_path / "obj")
    await repo.open()
    try:
        for url in (
            "https://example.com/",
            "https://WWW.Example.com/page",
            "https://notexample.com/",
            "https://example.com.evil.test/",
            "https://other.test/?u=example.com",
        ):
            await repo.create_audit(url=url, mode=AuditMode.PAGE, options={}, seed=1)
        got = await repo.list_site_audits("www.example.com")
        assert sorted(a.target_url for a in got) == [
            "https://WWW.Example.com/page",
            "https://example.com/",
        ]
        assert await repo.list_site_audits("") == []
        assert len(await repo.list_site_audits("example.com", limit=1)) == 1
    finally:
        await repo.close()


async def test_rerun_keeps_keywords_and_competitors(tmp_path: Path) -> None:
    svc = build_local_service(
        Settings(data_dir=tmp_path, anthropic_api_key=None, render_enabled=False)
    )
    await svc.repo.open()  # not started: no worker, so nothing is fetched
    try:
        first = await svc.create_audit(
            "https://example.com/",
            AuditMode.PAGE,
            keywords=["seo"],
            competitors=["https://rival.example/"],
            lang="en",
        )
        again = await svc.rerun(first, ["all"])
        opts = await svc.repo.get_option(again)
        assert opts["keywords"] == ["seo"] and opts["competitors"] == ["https://rival.example/"]
        rec = await svc.repo.load_record(again)
        assert rec is not None and rec.parent_audit_id == first
    finally:
        await svc.repo.close()
