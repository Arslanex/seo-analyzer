from __future__ import annotations

import json
import os
import re
from pathlib import Path

import lxml.html
import pytest
from markupsafe import escape

from seoa.application.reporting import build_report, check_report
from seoa.domain import Severity
from seoa.domain.rules import registry
from seoa.presentation.web.html import (
    BAND_STYLES,
    SEVERITY_STYLES,
    TEMPLATES_DIR,
    render_report_html,
    severity_css,
)
from tests.support.fake_service import XSS_EVIDENCE, XSS_EVIDENCE_2, make_sample_record

VARIANTS = ["gated", "clean", "insufficient", "partial", "failed", "page", "canceled"]
GOLDEN = Path(__file__).parents[2] / "golden" / "report"


def _render(variant: str, lang: str, **kw):  # type: ignore[no-untyped-def]
    report = build_report(make_sample_record(variant, **kw), lang)
    return report, render_report_html(report, lang)


@pytest.mark.parametrize("lang", ["tr", "en"])
@pytest.mark.parametrize("variant", VARIANTS)
def test_every_variant_renders_and_passes_the_quality_gate(variant: str, lang: str) -> None:
    report, html = _render(variant, lang)
    root = lxml.html.fromstring(html)  # well-formed enough for lxml
    assert root.get("lang") == lang
    assert len(root.xpath("//h1")) == 1 and root.xpath("//main")
    q = check_report(report, html, lang=lang)
    assert q.status in ("PASS", "WARN"), q.checks
    assert all(c.status != "FAIL" for c in q.checks)


def test_html_has_no_inline_script_or_event_handlers() -> None:
    _, html = _render("gated", "tr")
    root = lxml.html.fromstring(html)
    assert [s for s in root.iter("script") if not s.get("src")] == []
    assert not [
        a for el in root.iter() if isinstance(el.tag, str) for a in el.attrib if a.startswith("on")
    ]


def test_xss_markup_in_every_page_derived_field_is_escaped() -> None:
    report, html = _render("gated", "en", xss=True)
    assert XSS_EVIDENCE not in html and XSS_EVIDENCE_2 not in html
    assert "&lt;script&gt;" in html and "&lt;img" in html
    root = lxml.html.fromstring(html)
    assert not root.xpath("//script[not(@src)]") and not root.xpath("//img")
    q = check_report(report, html, lang="en", sentinels=[XSS_EVIDENCE, XSS_EVIDENCE_2])
    assert q.status != "FAIL"


def test_quality_gate_fails_on_unescaped_evidence() -> None:
    report, html = _render("gated", "en", xss=True)
    tampered = html.replace(str(escape(XSS_EVIDENCE)), XSS_EVIDENCE)
    assert tampered != html
    q = check_report(report, tampered, lang="en", sentinels=[XSS_EVIDENCE])
    assert q.status == "FAIL" and "html.escaping" in {c.id for c in q.checks}


def test_quality_gate_fails_on_inline_script_and_event_handler() -> None:
    report, html = _render("clean", "en")
    bad = html.replace("</body>", "<script>alert(1)</script><a href='#' onclick='x()'>x</a></body>")
    ids = {c.id for c in check_report(report, bad, lang="en").checks}
    assert {"html.inline_script", "html.event_handlers"} <= ids


def test_quality_gate_warns_on_structure_problems() -> None:
    report, html = _render("clean", "en")
    bad = html.replace(
        "</main>",
        '<h6 id="dup">x</h6><h6 id="dup">y</h6><a href="">e</a><section></section></main>',
    )
    checks = {c.id: c.status for c in check_report(report, bad, lang="en").checks}
    assert {
        checks.get(k)
        for k in ("html.headings", "html.empty_refs", "html.empty_section", "html.duplicate_ids")
    } == {"WARN"}


def test_quality_contract_failures_are_detected() -> None:
    report, _ = _render("gated", "en")
    report.scores.overall.value = 99  # above the gate cap; bypass validators
    report.recommendations[0].depends_on = ["rec_9999"]
    ids = {c.id for c in check_report(report, None).checks}
    assert {"contract.gate", "refs.resolve"} <= ids


def test_quality_detects_a_dependency_cycle() -> None:
    report, _ = _render("gated", "en")
    a, b = report.recommendations[0], report.recommendations[1]
    a.depends_on, b.depends_on = [b.id], [a.id]
    assert "refs.cycle" in {c.id for c in check_report(report, None).checks}


def test_missing_translation_is_a_warning_not_a_failure() -> None:
    rec = make_sample_record("gated")
    f = rec.findings[1].model_copy(
        update={
            "id": "x-no-translation",
            "message_key": "finding.x-no-translation",
            "message": "English only",
        }
    )
    rec.findings.append(f)
    registry.register_messages({"finding.x-no-translation": {"en": "English only"}})
    try:
        report = build_report(rec, "tr")
        q = check_report(report, render_report_html(report, "tr"), lang="tr")
        assert q.status == "WARN" and "text.translation" in {c.id for c in q.checks}
        assert (
            next(x for x in report.findings if x.check_id == "x-no-translation").message
            == "English only"
        )
    finally:
        registry.MESSAGES.pop("finding.x-no-translation", None)


def test_severity_map_five_distinct_tones_shapes_and_labels() -> None:
    for mode in ("light", "dark"):
        assert len({SEVERITY_STYLES[s][mode][0] for s in Severity}) == 5
        assert len({SEVERITY_STYLES[s][mode][1] for s in Severity}) == 5
    assert len({SEVERITY_STYLES[s]["shape"] for s in Severity}) == 5
    assert len(set(BAND_STYLES.values())) == 3
    css = severity_css()
    for sev in Severity:
        assert f"--sev-{sev.value.lower()}-fg" in css
    assert "prefers-color-scheme: dark" in css


def _luminance(hex_: str) -> float:
    rgb = [int(hex_[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _ratio(a: str, b: str) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


@pytest.mark.parametrize("sev", list(Severity))
@pytest.mark.parametrize("mode", ["light", "dark"])
def test_severity_text_contrast_meets_wcag_aa(sev: Severity, mode: str) -> None:
    fg, bg = SEVERITY_STYLES[sev][mode]
    assert _ratio(fg, bg) >= 4.5


def test_all_five_severities_appear_with_text_labels_and_distinct_icons() -> None:
    _, html = _render("gated", "en")
    for label in ("Critical", "High", "Medium", "Low", "Info"):
        assert f"<span>{label}</span>" in html
    assert html.count('<polygon points="5,1 11,1') >= 1  # octagon (Critical)
    assert '<polygon points="8,1.5 15,14 1,14"' in html  # triangle (High)


def test_gate_banner_and_status_sections_render() -> None:
    _, html = _render("gated", "tr")
    assert "Skor sınırlandırıldı" in html and "Ham skor 71" in html and "en çok 40" in html
    _, partial = _render("partial", "tr")
    assert "Rapor kısmi" in partial
    _, insuff = _render("insufficient", "en")
    assert "Insufficient data" in insuff and "no number is shown" in insuff
    _, failed = _render("failed", "en")
    assert (
        "could not be completed" in failed
        and "could not be reached" in failed
        and "internal-host" not in failed
    )


def test_not_measured_card_is_not_painted_as_a_score() -> None:
    _, html = _render("partial", "en")
    assert "Not measured" in html and "did not count toward the score" in html
    root = lxml.html.fromstring(html)
    nm = root.xpath("//div[contains(@class,'nm')]")
    assert nm and not nm[0].xpath(".//svg") and "—" in nm[0].text_content()


def test_zero_findings_never_claims_the_site_is_fine() -> None:
    _, html = _render("clean", "en")
    assert "No issues were found in the checks that were run" in html
    assert "does not mean" in html and "your site has no problems" in html


def test_advisory_section_is_labelled_estimated_and_excluded_from_score() -> None:
    _, html = _render("gated", "en")
    assert "ESTIMATED" in html and "does not count toward the overall score" in html
    assert "does not publish numeric weights for E-E-A-T" in html


def test_findings_filter_is_server_side_and_marks_current() -> None:
    report = build_report(make_sample_record("gated"), "en")
    html = render_report_html(report, "en", severity="High")
    root = lxml.html.fromstring(html)
    arts = root.xpath("//article[contains(@class,'finding')]")
    assert arts and all("High" in a.xpath(".//header")[0].text_content() for a in arts)
    assert root.xpath("//nav[contains(@class,'filters')]//a[@aria-current='true']")


def test_templates_never_use_safe_or_disable_autoescape() -> None:
    for tpl in TEMPLATES_DIR.glob("*.html"):
        text = tpl.read_text()
        assert "|safe" not in text and "| safe" not in text, tpl.name
        assert "autoescape false" not in text and "{% autoescape" not in text, tpl.name
        assert "innerHTML" not in text


def test_static_js_never_uses_innerhtml_or_eval() -> None:
    js = (TEMPLATES_DIR.parent / "static" / "app.js").read_text()
    assert "innerHTML" not in js and "eval(" not in js and "document.write" not in js


def test_interactive_false_removes_scripts_and_forms() -> None:
    report = build_report(make_sample_record("gated"), "en")
    html = render_report_html(report, "en", interactive=False)
    root = lxml.html.fromstring(html)
    assert not root.xpath("//script") and not root.xpath("//form")


def test_report_title_and_language_switch() -> None:
    _, html = _render("gated", "tr")
    assert "Site denetim raporu" in html and "?lang=en" in html


def test_golden_report_json_is_stable() -> None:
    """Golden file for the sample record (real catalog texts). Regenerate with SEOA_UPDATE_GOLDEN=1 after a deliberate change."""
    from seoa.application.rules_loader import load_all_rules

    load_all_rules()
    report = build_report(make_sample_record("gated"), "en")
    got = json.loads(report.model_dump_json())
    path = GOLDEN / "gated.en.json"
    if os.environ.get("SEOA_UPDATE_GOLDEN") == "1" or not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(got, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
    want = json.loads(path.read_text())
    assert json.loads(json.dumps(got, sort_keys=True)) == want


def test_report_html_contains_no_leftover_template_syntax() -> None:
    _, html = _render("gated", "tr")
    assert not re.search(r"\{\{|\{%", html)


def test_p25_is_hidden_below_five_pages_and_few_pages_are_explained() -> None:
    rec = make_sample_record("gated")
    rec.scores.p25 = 55.0  # type: ignore[union-attr]
    rec.coverage = {
        "pages_planned": 1,
        "pages_fetched": 1,
        "sitemap_urls": 1,
        "skipped": {"out_of_scope": 2},
    }
    rec.pages = rec.pages[:1]
    report = build_report(rec, "en")
    assert report.scores.p25 is None
    assert any(
        lim.code == "few-pages" and "1 page" in lim.message and "2 link" in lim.message
        for lim in report.limitations
    )
