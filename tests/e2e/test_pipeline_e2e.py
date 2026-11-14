"""End-to-end: the whole deterministic pipeline against a fake site (no network, no LLM)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from seoa.application.audit.service import LocalAuditService
from seoa.bootstrap import build_local_service
from seoa.config import Settings
from seoa.domain import AuditMode, AuditStatus, CheckOutput
from seoa.infrastructure import adapters
from tests.e2e.site import BASE, build
from tests.support.fixture_fetcher import FixtureFetcher


@pytest.fixture
async def svc(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    async def no_transport(
        entry_url, fr, fetcher
    ):  # TLS needs a real host; covered by test_transport
        return CheckOutput()

    monkeypatch.setattr(adapters, "run_transport", no_transport)
    settings = Settings(
        data_dir=tmp_path,
        render_enabled=False,
        visibility_enabled=False,
        anthropic_api_key=None,
        request_delay_s=0.0,
    )
    s = build_local_service(
        settings,
        fetcher=FixtureFetcher(
            build(),
            errors={"https://nowhere.test/": "unreachable", "http://nowhere.test/": "unreachable"},
        ),
        workers=1,
    )
    await s.start()
    yield s
    await s.stop()


async def _run(svc: LocalAuditService, url: str, mode: AuditMode, **kw):
    aid = await svc.create_audit(url, mode, enable_llm=False, **kw)
    stages = []
    async for ev in svc.events(aid):
        if ev.stage and ev.status and getattr(ev.status, "value", ev.status) == "done":
            stages.append(ev.stage.value)
    return aid, stages, await svc.get_audit(aid)


async def test_page_mode_end_to_end(svc: LocalAuditService) -> None:
    aid, stages, rec = await _run(svc, f"{BASE}/hakkimizda", AuditMode.PAGE)
    assert rec and rec.status == AuditStatus.COMPLETED, rec.error if rec else None
    assert stages == ["validate", "fetch_entry", "robots", "measure", "analyze", "score", "report"]
    assert rec.scores and rec.scores.overall is not None
    ids = {f.id for f in rec.findings}
    assert "missing-meta-description" in ids  # the page has none
    assert rec.lang == "tr" and len(rec.pages) == 1


async def test_site_mode_samples_fetches_scores_and_finds_site_issues(
    svc: LocalAuditService,
) -> None:
    aid, stages, rec = await _run(svc, BASE, AuditMode.SITE, max_pages=25)
    assert rec and rec.status in (AuditStatus.COMPLETED, AuditStatus.PARTIAL), (
        rec.error if rec else None
    )
    assert {"discovery", "sample", "fetch_pages"} <= set(stages)
    ids = {f.id for f in rec.findings}
    assert "duplicate-title" in ids  # two blog posts share a title
    assert "images-missing-alt" in ids or "images-missing-dimensions" in ids
    assert rec.coverage["pages_fetched"] >= 8 and rec.coverage["templates"]
    assert rec.scores and rec.scores.overall is not None and 0 < rec.scores.overall <= 100
    assert rec.scores.core_overall is not None
    statuses = {p.url: p.status for p in rec.pages}
    assert statuses.get(f"{BASE}/eski-sayfa") == 404 or f"{BASE}/eski-sayfa" not in statuses
    assert "page-status-4xx" in ids or f"{BASE}/eski-sayfa" not in statuses


async def test_unreachable_target_fails_cleanly(svc: LocalAuditService) -> None:
    aid, _, rec = await _run(svc, "https://nowhere.test/", AuditMode.PAGE)
    assert rec and rec.status == AuditStatus.FAILED and (rec.error or "").startswith("unreachable")
    assert rec.scores is None  # no number is invented for a site we could not reach


async def test_entry_404_is_reportable_and_caps_the_score(svc: LocalAuditService) -> None:
    aid, _, rec = await _run(svc, "https://demo.test/yok", AuditMode.PAGE)
    assert rec and rec.status == AuditStatus.COMPLETED
    assert rec.scores and rec.scores.gate and rec.scores.gate.cap == 40
    assert rec.scores.overall is None or rec.scores.overall <= 40


async def test_private_target_is_rejected_at_validation(svc: LocalAuditService) -> None:
    aid, _, rec = await _run(svc, "http://127.0.0.1:8080/", AuditMode.PAGE)
    assert rec and rec.status == AuditStatus.FAILED and "target-rejected" in (rec.error or "")


async def test_cancel_before_start(svc: LocalAuditService) -> None:
    svc._n_workers = 0
    for t in svc._tasks:
        t.cancel()
    await asyncio.gather(*svc._tasks, return_exceptions=True)
    svc._tasks = []
    aid = await svc.create_audit(BASE, AuditMode.SITE, enable_llm=False)
    assert await svc.cancel(aid) is True
    rec = await svc.get_audit(aid)
    assert rec and rec.status == AuditStatus.QUEUED


async def test_rerun_links_to_parent(svc: LocalAuditService) -> None:
    aid, _, _ = await _run(svc, f"{BASE}/hakkimizda", AuditMode.PAGE)
    new = await svc.rerun(aid, ["scan"])
    async for _ in svc.events(new):
        pass
    rec = await svc.get_audit(new)
    assert rec and rec.parent_audit_id == aid and rec.status == AuditStatus.COMPLETED


async def test_deep_analysis_results_are_stored_and_scored(svc: LocalAuditService) -> None:
    aid, stages, rec = await _run(svc, BASE, AuditMode.SITE, max_pages=25)
    assert rec and "analyze" in stages
    # link graph: the home page links to a URL that answers 404
    assert rec.links is not None and rec.links.internal_total > 10 and rec.links.broken >= 1
    assert "broken-internal-link" in {f.id for f in rec.findings}
    assert any(p.url == BASE + "/" and p.depth == 0 for p in rec.links.pages)
    # indexability table: every sampled page has a row, the 404 page is not indexable
    by_url = {r.url: r for r in rec.indexability}
    assert by_url[BASE + "/"].indexable is True
    if BASE + "/eski-sayfa" in by_url:
        assert by_url[BASE + "/eski-sayfa"].indexable is False
    # score v2: every measured category shows the checks behind its score
    assert rec.scores and rec.scores.score_version == "mvp-0.2"
    for c in rec.scores.categories:
        if c.measured:
            assert c.checks_total > 0 and c.checks_passed + c.checks_failed == c.checks_total
    # unmeasured categories say why instead of getting a number
    perf = next(c for c in rec.scores.categories if c.category.value == "performance")
    assert perf.score is None and perf.reason
    # schema: the demo site has Organization markup on the home page only
    assert next(c for c in rec.scores.categories if c.category.value == "schema").measured


async def test_crux_field_data_is_stored_scored_and_answers_inp(
    svc: LocalAuditService, monkeypatch: pytest.MonkeyPatch
) -> None:
    from seoa.domain import FieldData, FieldMetric

    async def fake_crux(url: str, origin: str) -> FieldData:
        return FieldData(
            scope="origin",
            metrics=[
                FieldMetric(metric="lcp", p75=3300, rating="needs-improvement"),
                FieldMetric(metric="inp", p75=420, rating="needs-improvement"),
                FieldMetric(metric="cls", p75=0.02, rating="good"),
            ],
        )

    async def no_psi(url: str):  # type: ignore[no-untyped-def]
        return None

    monkeypatch.setattr(adapters, "google_api_key", lambda: "test-key")
    monkeypatch.setattr(adapters, "run_crux", fake_crux)
    monkeypatch.setattr(adapters, "run_psi", no_psi)
    aid, _, rec = await _run(svc, f"{BASE}/hakkimizda", AuditMode.PAGE)
    assert (
        rec
        and rec.field is not None
        and {m.metric for m in rec.field.metrics} == {"lcp", "inp", "cls"}
    )
    ids = {f.id for f in rec.findings}
    assert (
        "cwv-lcp-needs-improvement" in ids
        and "cwv-inp-needs-improvement" in ids
        and "cwv-cls-poor" not in ids
    )
    assert not any(
        n.check_id.startswith("cwv-inp") for n in rec.not_checked
    )  # field data answered it
    assert rec.coverage.get("crux") is True and rec.coverage.get("psi") is False
