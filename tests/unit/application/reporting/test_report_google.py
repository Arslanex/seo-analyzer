"""Search Console + CrUX field-data sections and the home-page Google card."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import lxml.html
import pytest

from seoa.application.reporting import build_report, check_report
from seoa.application.reporting import deep as deep_mod
from seoa.domain import i18n
from seoa.presentation.api import create_app
from seoa.presentation.web.html import render_report_html
from tests.support.fake_service import (
    XSS_EVIDENCE,
    XSS_EVIDENCE_2,
    FakeService,
    make_sample_record,
)

GSC_KINDS = ["not-connected", "not-configured", "property-not-found", "no-permission", "error"]


def _page(lang: str = "en", **kw):  # type: ignore[no-untyped-def]
    report = build_report(make_sample_record("gated", **kw), lang)
    html = render_report_html(report, lang)
    return report, html, lxml.html.fromstring(html)


# --------------------------------------------------------------------------- builder


def test_gsc_ok_section_has_totals_tables_and_inspection_summary() -> None:
    report, _, _ = _page(gsc="ok")
    g = report.gsc
    assert g.status == "measured" and g.gsc_status == "ok"
    assert g.property == "sc-domain:example.com" and g.permission == "siteOwner"
    assert g.totals["clicks"] == 1234
    assert g.top_queries[0].ctr_pct == 3.5 and g.top_pages
    assert (g.indexed_count, g.not_indexed_count, g.mismatch_count) == (1, 1, 1)
    assert [i.canonical_mismatch for i in g.inspections] == [False, True, False]
    assert g.inspections[2].error == "quota-exceeded" and g.inspections[2].error_text
    assert g.sitemaps[0].errors == 1
    assert "2-3" in deep_mod.gsc_section(make_sample_record("gated", gsc="ok"), "tr").delay_note


@pytest.mark.parametrize("kind", GSC_KINDS)
def test_gsc_unmeasured_states_carry_a_reason_and_no_rows(kind: str) -> None:
    report, _, _ = _page(gsc=kind)
    g = report.gsc
    assert g.status == "not_measured"
    assert g.not_measured_reason == f"gsc-{kind}" and (g.not_measured_text or "").strip()
    assert not (g.top_queries or g.top_pages or g.inspections or g.sitemaps)
    assert g.can_connect is (kind == "not-connected")


def test_gsc_absent_blob_reads_as_not_connected() -> None:
    report, _, _ = _page()  # old audits have no stored 'gsc'
    assert report.gsc.gsc_status == "not-connected" and report.gsc.can_connect


def test_field_ok_rates_p75_by_the_cwv_thresholds_and_shares_sum_sensibly() -> None:
    report, _, _ = _page(field="ok")
    f = report.field
    assert f.status == "measured" and f.scope == "origin" and f.form_factor == "PHONE"
    by = {m.metric: m for m in f.metrics}
    assert [m.metric for m in f.metrics] == ["lcp", "inp", "cls", "ttfb"]
    assert (by["lcp"].rating, by["inp"].rating, by["cls"].rating) == (
        "needs-improvement",
        "good",
        "poor",
    )
    assert by["cls"].p75_text == "0.31" and by["lcp"].p75_text == "3100 ms"
    assert by["ttfb"].good_pct is None  # no distribution: shown as an em dash, never as 0 %
    assert by["lcp"].good_pct + by["lcp"].needs_improvement_pct + by["lcp"].poor_pct == 100


def test_field_thresholds_match_the_psi_module() -> None:
    from seoa.application.analysis.performance import web_vitals

    for m, bounds in web_vitals.THRESHOLDS.items():
        assert deep_mod.FIELD_THRESHOLDS[m] == bounds


@pytest.mark.parametrize(
    ("kind", "reason"),
    [("no-data", "field-no-data"), ("no-api-key", "field-no-api-key"), ("error", "field-error")],
)
def test_field_unmeasured_reasons(kind: str, reason: str) -> None:
    report, _, _ = _page(field=kind)
    assert report.field.status == "not_measured" and report.field.not_measured_reason == reason
    assert not report.field.metrics


def test_field_not_run_reason() -> None:
    assert _page()[0].field.not_measured_reason == "field-not-run"


def test_data_sources_list_search_console_and_crux() -> None:
    ok = {d.id: d.status for d in _page(gsc="ok", field="ok")[0].data_sources}
    assert ok["gsc"] == "ok" and ok["crux"] == "ok"
    bad = {d.id: d.status for d in _page(gsc="error", field="error")[0].data_sources}
    assert bad["gsc"] == "failed" and bad["crux"] == "failed"
    miss = {d.id: d.status for d in _page(gsc="not-connected", field="no-data")[0].data_sources}
    assert miss["gsc"] == "missing" and miss["crux"] == "missing"


def test_scope_box_drops_the_indexing_item_only_when_search_console_is_ok() -> None:
    connected = _page(gsc="ok")[0].scope_note
    off = _page(gsc="not-connected")[0].scope_note
    assert connected is not None and off is not None
    assert not any("Indexing status" in i for i in connected.items)
    assert any("Indexing status" in i for i in off.items)
    # the sample audit also has ranking data when connected, so that item goes too
    assert not any("Rankings" in i for i in connected.items)
    assert any("Rankings" in i for i in off.items)
    for kept in ("Backlinks", "Keyword targeting", "Field speed", "competitors"):
        assert any(kept in i for i in connected.items)  # nothing measured these here
    assert "connect your Google account" in off.next_step
    assert "roadmap" not in off.next_step and "roadmap" not in connected.next_step


def test_visibility_search_console_item_follows_the_connection() -> None:
    def item(**kw):  # type: ignore[no-untyped-def]
        r = build_report(make_sample_record("gated", **kw), "en")
        return next(i for i in r.visibility.items if i.id == "search_console")

    assert item(gsc="ok").available and item(gsc="ok").value == "Connected"
    assert not item(gsc="not-connected").available


# --------------------------------------------------------------------------- html


def test_gsc_ok_html_shows_property_tables_and_text_status() -> None:
    _, html, root = _page(gsc="ok")
    sec = root.xpath("//section[@id='sec-gsc']")[0]
    text = sec.text_content()
    for needle in ("sc-domain:example.com", "siteOwner", "example widgets", "2-3 days", "1234"):
        assert needle in text, needle
    assert "informational" in text and "technical score" in text
    assert "Canonical differs" in text and "Submitted and indexed" in text
    # indexed is conveyed by words, not only by colour
    assert "Yes" in text.replace("yes", "Yes") and "No" in text.replace("no", "No")
    assert "/connect/google" not in html


@pytest.mark.parametrize("kind", GSC_KINDS)
def test_gsc_unmeasured_html_has_a_card_and_no_table(kind: str) -> None:
    _, _, root = _page(gsc=kind)
    sec = root.xpath("//section[@id='sec-gsc']")[0]
    assert not sec.xpath(".//table") and sec.xpath(".//*[contains(@class,'nm')]")


def test_connect_call_only_in_interactive_html_and_only_when_not_connected() -> None:
    report = build_report(make_sample_record("gated", gsc="not-connected"), "en")
    live = render_report_html(report, "en", interactive=True)
    static = render_report_html(report, "en", interactive=False)
    assert 'href="/connect/google"' in live and "/connect/google" not in static
    other = build_report(make_sample_record("gated", gsc="property-not-found"), "en")
    assert "/connect/google" not in render_report_html(other, "en")
    assert "add and verify" in render_report_html(other, "en").lower() or "Add and verify" in (
        render_report_html(other, "en")
    )


def test_field_html_separates_field_from_lab_and_uses_text_ratings() -> None:
    _, _, root = _page(field="ok")
    sec = root.xpath("//section[@id='sec-field']")[0]
    text = sec.text_content()
    assert "FIELD" in text and "LAB" in text and "real Chrome users" in text
    assert "needs improvement" in text and "good" in text and "poor" in text
    assert "55% / 30% / 15%" in text
    assert "Whole site" in text and "Phone" in text and "2026-10-10" in text
    assert sec.xpath(".//*[@role='img']")  # share bar has a text alternative


@pytest.mark.parametrize("kind", ["no-data", "no-api-key"])
def test_field_unmeasured_html_has_no_table(kind: str) -> None:
    _, _, root = _page(field=kind)
    sec = root.xpath("//section[@id='sec-field']")[0]
    assert not sec.xpath(".//table")
    assert root.xpath("//section[@id='sec-field']//*[contains(@class,'nm')]")


def test_scope_box_html_hides_the_indexing_item_when_connected() -> None:
    _, _, root = _page(gsc="ok")
    assert "Indexing status" not in root.xpath("//*[@id='scope-note']")[0].text_content()


def test_section_nav_links_resolve() -> None:
    _, _, root = _page(gsc="ok", field="ok")
    ids = set(root.xpath("//@id"))
    for href in root.xpath("//nav[@class='secnav']//a/@href"):
        assert href.lstrip("#") in ids, href


# --------------------------------------------------------------------------- quality gate


@pytest.mark.parametrize("gsc", [None, "ok", *GSC_KINDS])
@pytest.mark.parametrize("field", [None, "ok", "no-data", "no-api-key", "error"])
def test_quality_gate_passes_for_every_gsc_and_field_state(
    gsc: str | None, field: str | None
) -> None:
    record = make_sample_record("gated", gsc=gsc, field=field)
    report = build_report(record, "en")
    q = check_report(report, render_report_html(report, "en"), lang="en")
    assert q.status != "FAIL", q.checks


def test_quality_gate_rejects_rows_in_an_unmeasured_gsc_section() -> None:
    report = build_report(make_sample_record("gated", gsc="not-connected"), "en")
    report.gsc.top_queries = build_report(
        make_sample_record("gated", gsc="ok"), "en"
    ).gsc.top_queries
    q = check_report(report, lang="en")
    assert any(c.id == "deep.gsc" and c.status == "FAIL" for c in q.checks)


def test_quality_gate_requires_the_new_sections_in_the_page() -> None:
    report = build_report(make_sample_record("gated"), "en")
    html = render_report_html(report, "en").replace('id="sec-gsc"', 'id="x-gsc"')
    q = check_report(report, html, lang="en")
    assert any(c.id == "html.sections" and "gsc" in c.detail for c in q.checks)


def test_i18n_catalogs_have_identical_keys_and_new_keys_exist() -> None:
    assert i18n.missing_keys() == set()
    for key in ("sec.gsc", "sec.field", "gsc.note", "field.note", "home.google.title"):
        assert key in i18n.CATALOG["tr"] and key in i18n.CATALOG["en"]


# --------------------------------------------------------------------------- security


def test_third_party_gsc_text_is_escaped_in_html() -> None:
    _, html, root = _page(gsc="ok", xss=True)
    assert XSS_EVIDENCE not in html and XSS_EVIDENCE_2 not in html
    assert not root.xpath("//script[contains(., 'xss')]") and not root.xpath("//img[@onerror]")
    assert "&lt;script&gt;" in html


def test_long_gsc_lists_are_truncated_and_flagged() -> None:
    record = make_sample_record("gated", gsc="ok")
    assert record.gsc is not None
    record.gsc.top_queries = record.gsc.top_queries * 30
    report = build_report(record, "en")
    assert len(report.gsc.top_queries) == deep_mod.GSC_ROWS and report.gsc.truncated


# --------------------------------------------------------------------------- API + home card


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    service = FakeService()
    service.add(make_sample_record("gated", audit_id="aud_google01", gsc="ok", field="ok"))
    app = create_app(service)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as c:
        yield c


async def test_gsc_and_field_endpoints_serve_the_sections(client: httpx.AsyncClient) -> None:
    g = (await client.get("/v1/audits/aud_google01/gsc?lang=en")).json()
    assert g["status"] == "measured" and g["top_queries"] and g["inspections"]
    f = (await client.get("/v1/audits/aud_google01/field?lang=tr")).json()
    assert f["status"] == "measured" and [m["metric"] for m in f["metrics"]][0] == "lcp"
    old = (await client.get("/v1/audits/aud_sample0001/gsc")).json()
    assert old["status"] == "not_measured" and old["not_measured_reason"] == "gsc-not-connected"


async def test_report_json_includes_the_new_sections(client: httpx.AsyncClient) -> None:
    body = (await client.get("/v1/audits/aud_google01/report?format=json&lang=en")).json()
    assert body["gsc"]["status"] == "measured" and body["field"]["status"] == "measured"
    assert {d["id"] for d in body["data_sources"]} >= {"gsc", "crux"}


async def test_unknown_audit_gsc_is_a_404_problem(client: httpx.AsyncClient) -> None:
    r = await client.get("/v1/audits/aud_nope/gsc")
    assert r.status_code == 404 and r.headers["content-type"].startswith("application/problem+json")


def _home(
    status: dict[str, object] | None, query: str = "", *, awaitable: bool = False, path: str = "/"
):  # type: ignore[no-untyped-def]
    provider = None
    if status is not None:
        if awaitable:

            async def provider() -> dict[str, object]:  # type: ignore[misc]
                return status

        else:

            def provider() -> dict[str, object]:  # type: ignore[misc]
                return status

    app = create_app(FakeService(), google_status=provider)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost")

    async def get() -> str:
        async with client:
            return (await client.get(f"{path}?lang=tr{query}")).text

    return get()


async def test_home_card_is_hidden_without_a_status_provider() -> None:
    assert "g-title" not in await _home(None)


async def test_home_card_not_configured_points_to_the_setup_doc() -> None:
    html = await _home({"configured": False, "connected": False, "email": None}, path="/settings")
    assert "docs/google-setup.md" in html and "/connect/google" not in html


async def test_home_card_configured_not_connected_offers_connect() -> None:
    html = await _home(
        {"configured": True, "connected": False, "email": None}, awaitable=True, path="/settings"
    )
    assert 'href="/connect/google"' in html and "yalnızca okuma izni" in html.lower()
    assert "/disconnect/google" not in html


async def test_home_card_connected_shows_email_and_post_disconnect() -> None:
    html = await _home(
        {"configured": True, "connected": True, "email": "me@example.com"}, path="/settings"
    )
    root = lxml.html.fromstring(html)
    assert "me@example.com" in html
    form = root.xpath("//form[@action='/disconnect/google']")[0]
    assert form.get("method") == "post" and "Bağlantıyı kaldır" in form.text_content()


async def test_home_card_escapes_the_account_email() -> None:
    html = await _home(
        {"configured": True, "connected": True, "email": "<script>x</script>@a.b"}, path="/settings"
    )
    assert "<script>x</script>" not in html


@pytest.mark.parametrize(
    ("q", "shown"),
    [
        ("&google=connected", "Google hesabı bağlandı."),
        ("&google=disconnected", "Google bağlantısı kaldırıldı."),
    ],
)
async def test_home_message_for_connect_and_disconnect(q: str, shown: str) -> None:
    html = await _home({"configured": True, "connected": False, "email": None}, q)
    assert shown in html


async def test_unknown_google_message_is_ignored() -> None:
    html = await _home({"configured": True, "connected": False, "email": None}, "&google=<b>x</b>")
    assert "<b>x</b>" not in html and "Google hesabı bağlandı" not in html
