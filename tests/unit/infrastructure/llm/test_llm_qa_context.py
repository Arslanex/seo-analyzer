from __future__ import annotations

from seoa.infrastructure.llm.qa import build_context

REPORT = {
    "audit": {"url": "https://e.com/"},
    "scores": {"overall": 80, "categories": [{"category": "onpage", "score": 70}]},
    "findings": [
        {
            "id": f"fnd_{i:04d}",
            "severity": "Medium",
            "category": "onpage",
            "message": f"m{i}",
            "url": "https://e.com/",
        }
        for i in range(12)
    ],
}


def test_a_turkish_question_without_keywords_still_gets_the_top_findings() -> None:
    ctx, allowed = build_context(REPORT, "Önce neyi düzeltmeliyim?")
    assert len(allowed["finding_id"]) >= 8 and "fnd_0000" in allowed["finding_id"]
    assert "FINDINGS:" in ctx


def test_more_severe_findings_come_first() -> None:
    rep = {
        **REPORT,
        "findings": [
            {"id": "low", "severity": "Low", "category": "x", "message": "l"},
            {"id": "crit", "severity": "Critical", "category": "x", "message": "c"},
        ],
    }
    ctx, allowed = build_context(rep, "hangisi?")
    assert ctx.index('"crit"') < ctx.index('"low"') and allowed["finding_id"] == {"crit", "low"}
