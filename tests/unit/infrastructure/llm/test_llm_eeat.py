from __future__ import annotations

from datetime import date

import pytest

from seoa.infrastructure.llm import eeat
from seoa.infrastructure.llm.input import build_content_input
from tests.support.llm import FakeTransport, make_client

TODAY = date(2026, 11, 13)
HTML = """<html lang="en"><head><title>T</title><script type="application/ld+json">
{"@type":"Article","author":{"name":"Jane Doe"},"dateModified":"2026-06-01"}</script></head><body>
<nav><a href="/contact">Contact us</a></nav><main><h1>How we cut churn</h1>
<p>I tested this retention approach with 14 customers over two years and tracked every result by hand.
As a certified analyst with ten years of practice I document the exact steps I followed.</p></main>
<footer><a href="/privacy">Privacy Policy</a><a href="/about">About us</a></footer></body></html>"""


def ci():
    return build_content_input(HTML, "https://example.com/blog/churn", {})


def sig(sid, status="present", field="main_text", quote="", note=""):
    return {"signal_id": sid, "status": status, "field": field, "quote": quote, "note": note}


def test_catalog_applicability() -> None:
    assert "T9" not in eeat.applicable_ids("article") and "T9" in eeat.applicable_ids("product")
    assert "X5" not in eeat.llm_ids("article") and "T3" not in eeat.llm_ids("article")


def test_fabricated_quote_is_rejected_to_unclear() -> None:
    raw = eeat.SignalExtraction(
        signals=[sig("E1", quote="I have personally run this program for a decade")],
        observations=[],
    )
    out, stats = eeat.validate_signals(ci(), raw, TODAY)
    e1 = next(s for s in out if s["signal_id"] == "E1")
    assert e1["status"] == "unclear" and stats["rejected_quotes"] == 1


def test_valid_quote_accepted_and_reuse_blocked() -> None:
    q = "I tested this retention approach with 14 customers"
    raw = eeat.SignalExtraction(signals=[sig("E1", quote=q), sig("E3", quote=q)], observations=[])
    out, stats = eeat.validate_signals(ci(), raw, TODAY)
    by = {s["signal_id"]: s for s in out}
    assert (
        by["E1"]["status"] == "present"
        and by["E3"]["status"] == "unclear"
        and stats["reused_quotes"] == 1
    )


def test_wrong_field_for_signal_is_rejected() -> None:
    raw = eeat.SignalExtraction(
        signals=[sig("T2", field="main_text", quote="I tested this retention approach with 14")],
        observations=[],
    )
    out, _ = eeat.validate_signals(ci(), raw, TODAY)
    assert (
        next(s for s in out if s["signal_id"] == "T2")["status"] == "unclear"
    )  # T2 only allows chrome_link


def test_missing_signals_become_unclear_and_unknown_ids_dropped() -> None:
    raw = eeat.SignalExtraction(signals=[sig("E4", "absent", "none")], observations=[])
    out, stats = eeat.validate_signals(ci(), raw, TODAY)
    assert {s["signal_id"] for s in out} == set(eeat.applicable_ids("article"))
    assert (
        stats["missing"] >= 10
        and next(s for s in out if s["signal_id"] == "E4")["status"] == "absent"
    )


def test_deterministic_signals_win() -> None:
    raw = eeat.SignalExtraction(signals=[sig("X6", "absent", "none")], observations=[])
    out, _ = eeat.validate_signals(ci(), raw, TODAY)
    by = {s["signal_id"]: s for s in out}
    assert by["X6"]["status"] == "present" and by["X6"]["source"] == "code"
    assert (
        by["T3"]["status"] == "present" and by["X5"]["status"] == "present"
    )  # modified 2026-06 is recent
    assert (
        eeat.det_signals(ci(), date(2030, 1, 1))["X5"]["status"] == "absent"
    )  # old date -> absent


def _sigs(**counts):
    """signals for one factor: n present, m absent, k unclear."""
    ids = {"experience": ["E1", "E2", "E3", "E4", "E5", "E6"], "expertise": ["X1", "X3", "X5", "X6"],
           "authoritativeness": ["A4", "A6", "A7"], "trustworthiness": ["T1", "T2", "T3", "T4", "T5", "T6"]}  # fmt: skip
    out = []
    for factor, (p, a, u) in counts.items():
        for sid in ids[factor][: p + a + u]:
            i = ids[factor].index(sid)
            out.append(
                {
                    "signal_id": sid,
                    "status": "present" if i < p else "absent" if i < p + a else "unclear",
                }
            )
    return out


@pytest.mark.parametrize(
    "p,a,band,value",
    [
        (4, 2, "moderate", 65),
        (3, 3, "moderate", 65),
        (2, 4, "weak", 35),
        (1, 5, "weak", 35),
        (0, 6, "none", 10),
        (5, 1, "strong", 90),
        (6, 0, "strong", 90),
    ],
)
def test_band_thresholds(p: int, a: int, band: str, value: int) -> None:
    f = next(
        x for x in eeat.factor_bands(_sigs(experience=(p, a, 0))) if x["factor"] == "experience"
    )
    assert (f["band"], f["value"]) == (band, value) and f["assessed"]


def test_unclear_leaves_denominator_and_factor_needs_two_assessable() -> None:
    f = {
        x["factor"]: x
        for x in eeat.factor_bands(_sigs(experience=(1, 0, 5), trustworthiness=(1, 1, 0)))
    }
    assert not f["experience"]["assessed"] and f["experience"]["band"] is None
    assert f["trustworthiness"]["assessed"] and f["trustworthiness"]["r"] == 0.5


def test_score_renormalises_over_assessed_factors_and_coverage_gate() -> None:
    sigs = _sigs(
        experience=(6, 0, 0),
        expertise=(0, 4, 0),
        authoritativeness=(0, 0, 3),
        trustworthiness=(0, 0, 6),
    )
    score, label, cov = eeat.advisory_score(eeat.factor_bands(sigs))
    assert cov == 45.0 and score is None and label is None  # (20+25)/100 < 50 -> no number
    sigs = _sigs(
        experience=(6, 0, 0),
        expertise=(0, 4, 0),
        authoritativeness=(0, 0, 3),
        trustworthiness=(6, 0, 0),
    )
    score, label, cov = eeat.advisory_score(eeat.factor_bands(sigs))
    assert (
        cov == 75.0
        and score == round((20 * 90 + 25 * 10 + 30 * 90) / 75, 1)
        and label == "moderate"
    )


@pytest.mark.parametrize(
    "v,label",
    [
        (100, "exceptional"),
        (90, "exceptional"),
        (89.9, "strong"),
        (70, "strong"),
        (69.9, "moderate"),
        (50, "moderate"),
        (49.9, "weak"),
        (30, "weak"),
        (29.9, "very_low"),
    ],
)
def test_label_bands(v: float, label: str) -> None:
    f = [{"assessed": True, "weight": 100, "value": v}]
    assert eeat.advisory_score(f)[1] == label


async def test_run_eeat_end_to_end_with_fake_model(tmp_path) -> None:
    q1, q2 = (
        "I tested this retention approach with 14 customers",
        "As a certified analyst with ten years of practice",
    )
    body = {
        "signals": [sig("E1", quote=q1), sig("X1", field="main_text", quote=q2), sig("T2", field="chrome_link", quote="Privacy Policy"),
                    sig("T4", field="chrome_link", quote="About us"), sig("T1", field="chrome_link", quote="Contact us"),
                    sig("E3", "absent", "none"), sig("E2", "absent", "none")],
        "observations": [{"kind": "strength", "signal_ids": ["E1"], "text": "First-hand testing is described.", "quote": q1},
                         {"kind": "gap", "signal_ids": ["E3"], "text": "Improve FID on this page.", "quote": ""},   # V5 -> dropped
                         {"kind": "strength", "signal_ids": ["E1"], "text": "Invented", "quote": "this sentence is not on the page at all"}],  # V3 -> dropped
    }  # fmt: skip
    t = FakeTransport(body)
    rec = await eeat.run_eeat(make_client(tmp_path, t), ci(), today=TODAY)
    assert rec.kind == "eeat" and rec.error is None and rec.score is not None and rec.label
    assert len(rec.observations) == 1 and rec.observations[0]["quote"] == q1
    assert rec.rubric_version == "eeat-1.0" and rec.prompt_version.startswith("eeat-")
    meta = rec.factors[-1]
    assert meta["factor"] == "_meta" and meta["stats"]["missing"] > 0


async def test_run_eeat_degrades_to_error_record_when_llm_unavailable(tmp_path) -> None:
    t = FakeTransport(RuntimeError("boom"))
    rec = await eeat.run_eeat(make_client(tmp_path, t), ci(), today=TODAY)
    assert rec.error and rec.error.startswith("unavailable") and rec.confidence == "low"
    assert any(s["signal_id"] == "T3" for s in rec.signals)  # code-decided signals still reported
