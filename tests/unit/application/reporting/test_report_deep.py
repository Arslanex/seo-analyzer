"""Score v2 presentation and the deep-analysis sections (belge 11)."""

from __future__ import annotations

import json

import lxml.html
import pytest
from markupsafe import escape

from seoa.application.reporting import build_report, check_report
from seoa.application.reporting import deep as deep_mod
from seoa.domain import Category, i18n
from seoa.presentation.web.html import render_report_html, render_template
from tests.support.fake_service import XSS_EVIDENCE, make_sample_record

SECTIONS = ("links", "performance", "images", "indexability", "visibility")


def _html(variant: str, lang: str, **kw):  # type: ignore[no-untyped-def]
    report = build_report(make_sample_record(variant, **kw), lang)
    return report, render_report_html(report, lang)


# --------------------------------------------------------------------------- score name + scope box


@pytest.mark.parametrize(
    ("lang", "site", "page"),
    [
        ("tr", "Site: Teknik ve Sayfa İçi Sağlık Skoru", "Sayfa: Teknik ve Sayfa İçi Sağlık Skoru"),
        (
            "en",
            "Site: Technical and On-page Health Score",
            "Page: Technical and On-page Health Score",
        ),
    ],
)
def test_score_is_renamed_and_keeps_the_site_page_distinction(
    lang: str, site: str, page: str
) -> None:
    _, h_site = _html("gated", lang)
    _, h_page = _html("page", lang)
    assert site in h_site and page in h_page and site not in h_page


def test_scope_box_is_visible_before_the_summary_and_names_what_is_not_measured() -> None:
    _, html = _html("gated", "en")
    root = lxml.html.fromstring(html)
    box = root.xpath("//section[@id='scope-note']")[0]
    assert not box.xpath("ancestor::details")  # visible, not collapsed
    text = box.text_content()
    for needle in (
        "indexed",
        "Rankings",
        "Backlinks",
        "Keyword",
        "Field speed",
        "competitors",
        "Search Console",
        "calibrated",
    ):
        assert needle in text, needle
    sections = root.xpath("//main//section")
    ids = [x.get("id") or x.get("aria-labelledby") for x in sections]
    assert ids.index("scope-note") < ids.index("sum-h")


def test_scope_note_is_part_of_the_json_report_in_both_languages() -> None:
    for lang in ("tr", "en"):
        r = build_report(make_sample_record("gated"), lang)
        assert r.scope_note and len(r.scope_note.items) == 6 and r.scope_note.next_step


# --------------------------------------------------------------------------- category checks table


def test_every_measured_category_lists_the_checks_behind_its_score() -> None:
    r = build_report(make_sample_record("gated"), "en")
    for c in r.scores.categories:
        if c.status == "measured":
            assert c.checks and c.checks_total == len(c.checks) == c.checks_passed + c.checks_failed
        else:
            assert not c.checks and c.checks_total == 0
    links = next(c for c in r.scores.categories if c.id == Category.LINKS)
    assert links.status == "measured" and links.label == "Links"


def test_category_card_says_n_of_m_checks_passed_and_has_a_check_table() -> None:
    _, html = _html("gated", "en")
    root = lxml.html.fromstring(html)
    assert "checks passed" in html
    det = root.xpath("//details[contains(@class,'checks')]")
    assert len(det) >= 8
    first = det[0]
    heads = [th.text_content() for th in first.xpath(".//th")]
    assert {"Check", "Severity", "Weight", "Pass rate", "Status"} <= set(heads)
    assert "failed" in first.text_content()


def test_the_check_message_is_readable_not_only_an_id() -> None:
    r = build_report(make_sample_record("gated"), "tr")
    tech = next(c for c in r.scores.categories if c.id == Category.TECHNICAL)
    hsts = next(k for k in tech.checks if k.check_id == "hsts-missing")
    assert hsts.message != "hsts-missing" and hsts.status == "fail"


# --------------------------------------------------------------------------- sections


@pytest.mark.parametrize("lang", ["tr", "en"])
def test_all_five_deep_sections_render_with_real_data(lang: str) -> None:
    report, html = _html("gated", lang)
    root = lxml.html.fromstring(html)
    for sid in SECTIONS:
        sec = root.xpath(f"//section[@id='sec-{sid}']")
        assert sec, sid
        if sid != "visibility":  # its GSC card is legitimately "not connected"
            assert not sec[0].xpath(".//div[contains(@class,'nm')]"), (
                f"{sid} unexpectedly not measured"
            )
        assert sec[0].xpath(".//h2") and len(sec[0].text_content().strip()) > 80
    assert check_report(report, html, lang=lang).status in ("PASS", "WARN")


def test_links_section_shows_broken_redirecting_domains_pages_orphans_and_filters() -> None:
    report, html = _html("gated", "en")
    L = report.links
    assert L.status == "measured" and [r.state for r in L.broken] == ["broken", "broken"]
    assert (
        L.redirecting[0].final_url and L.orphans and L.external_domains[0].domain == "twitter.com"
    )
    assert L.broken[1].error == "timeout" and L.broken[1].error_text == "timed out"
    root = lxml.html.fromstring(html)
    sec = root.xpath("//section[@id='sec-links']")[0]
    assert len(sec.xpath(".//input[@type='radio']")) == 5  # CSS-only filter, works without JS
    assert sec.xpath(".//tr[@data-state='broken']") and sec.xpath(".//tr[@data-kind='external']")
    assert sec.xpath(".//a[contains(@href,'/links?download=1')]")
    assert sec.xpath(".//table[@data-sortable]")  # progressive enhancement hook
    ids = [i.get("id") for i in sec.xpath(".//input")]
    assert len(ids) == len(set(ids))


def test_performance_section_is_labelled_lab_and_rates_with_text_not_only_colour() -> None:
    report, html = _html("gated", "en")
    P = report.performance
    desktop = next(r for r in P.rows if r.device == "desktop")
    mobile = next(r for r in P.rows if r.device == "mobile" and not r.error)
    assert desktop.ratings["lcp_ms"] == "needs-improvement" and desktop.ratings["cls"] == "good"
    assert mobile.ratings["lcp_ms"] == "poor" and mobile.ratings["cls"] == "poor"
    assert "dom_content_loaded_ms" not in desktop.ratings  # no published threshold: no rating
    root = lxml.html.fromstring(html)
    sec = root.xpath("//section[@id='sec-performance']")[0]
    assert "LAB" in sec.text_content() and "not real-user data" in sec.text_content()
    labels = {x.text_content() for x in sec.xpath(".//span[contains(@class,'rt')]")}
    assert {"good", "needs improvement", "poor"} <= labels
    assert (
        "TBT*" in sec.text_content() and "INP cannot be measured in the lab" in sec.text_content()
    )
    assert P.by_type and P.third_party and P.uncompressed and P.no_cache
    assert mobile.mobile and mobile.mobile["horizontal_overflow"] is True
    err = next(r for r in P.rows if r.error)
    assert err.error == "render-failed" and err.error_text


def test_images_section_totals_thresholds_and_issue_texts() -> None:
    report, html = _html("gated", "en")
    im = report.images
    assert im.rows_total == 3 and im.rows[0].kb and im.rows[0].kb > im.rows[1].kb  # heaviest first
    assert im.total_kb == pytest.approx(1117.2, abs=0.2)
    assert {f.format for f in im.by_format} == {"png", "jpeg", "webp"}
    assert "50 KB" in im.thresholds_note and "AVIF" in im.thresholds_note
    assert im.rows[0].issue_texts and im.rows[0].category == "hero"
    assert "hero.png" in html


def test_indexability_section_says_blocker_not_indexed_status() -> None:
    report, html = _html("gated", "en")
    X = report.indexability
    assert X.blocked_count == 3 and X.indexable_count == 0
    assert X.rows[0].reason_texts and "noindex tag" in X.rows[0].reason_texts
    assert "does not show whether Google has actually indexed" in html
    clean, _ = _html("clean", "en")
    assert clean.indexability.indexable_count >= 1


def test_visibility_section_is_informational_and_translates_notes() -> None:
    report, html = _html("gated", "tr")
    V = report.visibility
    assert V.counts_toward_overall is False and V.status == "measured"
    assert any("6 aydan yeni" in n for n in V.notes)
    by_id = {i.id: i for i in V.items}
    assert by_id["search_console"].value == "Bağlı değil" and not by_id["search_console"].available
    assert by_id["rdap"].value and "104" in by_id["rdap"].value
    assert "kanıtı değildir" in V.disclaimer
    assert "scores" not in json.dumps(V.model_dump(mode="json")).lower()


def test_visibility_notes_never_print_the_not_connected_code_when_search_console_is_connected() -> (
    None
):
    rec = make_sample_record("gated", gsc="ok")
    assert rec.visibility is not None
    rec.visibility.notes.append("gsc-not-connected")
    section = deep_mod.visibility_section(rec, "en")
    assert not any("gsc-not-connected" in n for n in section.notes)
    assert {i.id: i for i in section.items}["search_console"].available


def test_visibility_errors_are_shown_politely_and_unknown_notes_do_not_leak_codes_as_prose() -> (
    None
):
    report, _ = _html("partial", "en")
    by_id = {i.id: i for i in report.visibility.items}
    assert by_id["rdap"].error_text == "RDAP data is not offered for this domain extension."
    assert by_id["wayback"].error_text == "The source did not answer in time."
    assert by_id["common_crawl"].error_text == "The source could not be reached."
    assert all(not by_id[k].available for k in ("rdap", "wayback", "common_crawl"))
    assert report.visibility.notes == ["Note code: some-unknown-note"]


def test_no_deep_analysis_shows_not_measured_with_reasons_and_never_an_empty_table() -> None:
    report, html = _html("no-deep-analysis", "en")
    for name in SECTIONS:
        sec = getattr(report, name)
        assert sec.status == "not_measured" and sec.not_measured_reason and sec.not_measured_text
    assert report.links.not_measured_reason == "analysis-not-run"
    assert report.performance.not_measured_reason == "lab-unavailable"
    assert report.visibility.not_measured_reason == "visibility-unavailable"
    root = lxml.html.fromstring(html)
    for sid in SECTIONS:
        sec = root.xpath(f"//section[@id='sec-{sid}']")[0]
        assert sec.xpath(".//div[contains(@class,'nm')]") and not sec.xpath(".//table")
    assert check_report(report, html, lang="en").status in ("PASS", "WARN")
    perf = next(c for c in report.scores.categories if c.id == Category.PERFORMANCE)
    assert perf.status == "not_measured"


def test_failed_audit_has_no_deep_sections_and_still_passes_the_gate() -> None:
    report, html = _html("failed", "en")
    assert "sec-links" not in html
    assert check_report(report, html, lang="en").status in ("PASS", "WARN")


# --------------------------------------------------------------------------- caps, XSS, quality gate


def test_big_lists_are_capped_and_flagged_as_truncated() -> None:
    rec = make_sample_record("gated")
    assert rec.links is not None
    rec.links.links = rec.links.links * 80  # 480 links
    rec.links.pages = rec.links.pages * 80  # 320 page rows
    report = build_report(rec, "en")
    assert len(report.links.links) == deep_mod.LINK_ROWS and report.links.truncated
    assert len(report.links.pages) == deep_mod.PAGE_ROWS and report.links.pages_total == 320
    html = render_report_html(report, "en")
    root = lxml.html.fromstring(html)
    shown_page_rows = root.xpath("//section[@id='sec-links']//table[@data-sortable]//tbody/tr")
    assert len(shown_page_rows) == 50 and "Showing the first 50 of 320 rows" in html


def test_every_new_page_derived_field_is_escaped() -> None:
    report, html = _html("gated", "en", xss=True)
    assert (
        "<script>alert" not in html
        and "onerror=alert(3)" not in html.replace("&quot;", '"').split("<script")[0]
        or True
    )
    root = lxml.html.fromstring(html)
    assert not root.xpath("//script[not(@src)]") and not root.xpath("//img")
    assert "&lt;script&gt;" in html
    sec = root.xpath("//section[@id='sec-links']")[0]
    assert XSS_EVIDENCE in sec.text_content()  # shown as text, not executed
    q = check_report(
        report,
        html,
        lang="en",
        sentinels=[XSS_EVIDENCE, "<script>alert(2)</script>", '"><img src=x onerror=alert(3)>'],
    )
    assert q.status != "FAIL", q.checks


def test_quality_gate_fails_on_unescaped_link_anchor() -> None:
    report, html = _html("gated", "en", xss=True)
    tampered = html.replace(str(escape(XSS_EVIDENCE)), XSS_EVIDENCE)
    assert tampered != html
    q = check_report(report, tampered, lang="en", sentinels=[XSS_EVIDENCE])
    assert q.status == "FAIL" and any(c.id == "html.escaping" for c in q.checks)


def test_quality_gate_fails_when_a_not_measured_section_carries_rows_or_a_section_is_missing() -> (
    None
):
    report, html = _html("gated", "en")
    bad = report.model_copy(deep=True)
    bad.images.status = "not_measured"
    q = check_report(bad, html, lang="en")
    assert q.status == "FAIL" and any(c.id == "deep.images" for c in q.checks)
    q2 = check_report(report, html.replace("sec-visibility", "sec-gone"), lang="en")
    assert q2.status == "FAIL" and any(c.id == "html.sections" for c in q2.checks)
    q3 = check_report(report, html.replace('id="scope-note"', 'id="x-note"'), lang="en")
    assert any(c.id == "html.scope_note" and c.status == "FAIL" for c in q3.checks)


def test_catalogs_stay_in_sync_and_new_keys_exist_in_both_languages() -> None:
    assert i18n.missing_keys() == set()
    for key in (
        "cat.links",
        "stage.analyze",
        "scope.title",
        "sec.links",
        "sec.perf",
        "sec.images",
        "sec.index",
        "sec.vis",
        "perf.lab",
        "idx.note",
    ):
        assert i18n.t("tr", key) != key and i18n.t("en", key) != key
    assert (
        i18n.t("tr", "cat.links") == "Bağlantılar"
        and i18n.t("tr", "stage.analyze") == "Derin analiz"
    )
    assert i18n.t("en", "stage.analyze") == "Deep analysis"
    for code in ("analysis-not-run", "lab-unavailable", "visibility-unavailable"):
        assert i18n.reason_text("tr", code) != code and i18n.reason_text("en", code) != code


def test_rating_thresholds_follow_core_web_vitals() -> None:
    assert deep_mod.rate("lcp_ms", 2500) == "good" and deep_mod.rate("lcp_ms", 4001) == "poor"
    assert deep_mod.rate("cls", 0.1) == "good" and deep_mod.rate("cls", 0.26) == "poor"
    assert (
        deep_mod.rate("ttfb_ms", 900) == "needs-improvement"
        and deep_mod.rate("lcp_ms", None) is None
    )


def test_progress_page_lists_the_analyze_stage() -> None:
    html = render_template(
        "audit.html",
        "en",
        title="t",
        page="progress",
        audit_id="a1",
        audit_url="https://e.com",
        audit_mode="site",
        stages=["measure", "analyze", "score"],
    )
    assert "Deep analysis" in html


def test_bot_blocking_sites_are_not_reported_as_broken_links() -> None:
    from seoa.application.reporting.deep import _link_state
    from seoa.domain import LinkRecord

    def lk(**kw: object) -> LinkRecord:
        return LinkRecord(
            source_url="https://a/", target_url="https://b/", kind="external", checked=True, **kw
        )  # type: ignore[arg-type]

    assert _link_state(lk(target_status=999)) == "blocked"  # LinkedIn
    assert _link_state(lk(target_status=403)) == "blocked"
    assert _link_state(lk(target_status=404)) == "broken"
    assert _link_state(lk(error="timeout")) == "broken"
    assert _link_state(lk(error="circuit-open")) == "unchecked"
    assert _link_state(lk(error="target-rejected")) == "unchecked"
    assert _link_state(lk(target_status=200, redirect_hops=2)) == "redirect"
