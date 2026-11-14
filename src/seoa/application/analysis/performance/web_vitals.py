"""Core Web Vitals rules, rating and PageSpeed Insights response parsing (pure, no network).

Thresholds are Google's published CWV values (the upstream project: references/cwv-thresholds.md, scripts/pagespeed_check.py):
LCP good <=2500 ms / poor >4000; INP good <=200 ms / poor >500; CLS good <=0.1 / poor >0.25.
Field data (CrUX, p75) wins over lab data when both exist. INP is the only interactivity metric (no FID).
"""

from __future__ import annotations

from typing import Any

from seoa.domain import Category, CheckOutput, NotChecked, Severity
from seoa.domain.rules.registry import CheckDef, make_finding, register, register_messages

THRESHOLDS = {"lcp": (2500.0, 4000.0), "inp": (200.0, 500.0), "cls": (0.1, 0.25)}
P = Category.PERFORMANCE

for _m, _label in (
    ("lcp", "Largest Contentful Paint"),
    ("inp", "Interaction to Next Paint"),
    ("cls", "Cumulative Layout Shift"),
):
    register(
        CheckDef(
            f"cwv-{_m}-poor",
            P,
            Severity.HIGH,
            scope="site",
            effort_default="L",
            impact_default="high",
        )
    )
    register(
        CheckDef(
            f"cwv-{_m}-needs-improvement",
            P,
            Severity.MEDIUM,
            scope="site",
            effort_default="M",
            impact_default="medium",
        )
    )
    register_messages(
        {
            f"finding.cwv-{_m}-poor": {
                "en": f"{_label} is in the 'poor' range (Core Web Vitals).",
                "tr": f"{_label} 'kötü' aralığında (Core Web Vitals).",
            },
            f"finding.cwv-{_m}-needs-improvement": {
                "en": f"{_label} needs improvement (Core Web Vitals).",
                "tr": f"{_label} iyileştirme gerektiriyor (Core Web Vitals).",
            },
            f"rec.cwv-{_m}-poor": {
                "en": "Profile the page and fix the largest contributor; re-measure with field data.",
                "tr": "Sayfayı profilleyip en büyük etkeni düzeltin; saha verisiyle yeniden ölçün.",
            },
            f"rec.cwv-{_m}-needs-improvement": {
                "en": "Look for quick wins in the metric's main contributors.",
                "tr": "Metriğin ana etkenlerinde hızlı kazanımlar arayın.",
            },
            f"fail.cwv-{_m}-poor": {
                "en": "The metric moves into the 'good' range in field data.",
                "tr": "Metrik saha verisinde 'iyi' aralığına geçer.",
            },
            f"fail.cwv-{_m}-needs-improvement": {
                "en": "The metric moves into the 'good' range in field data.",
                "tr": "Metrik saha verisinde 'iyi' aralığına geçer.",
            },
            f"lead.cwv-{_m}-poor": {
                "en": "Lab value in Lighthouse after each change.",
                "tr": "Her değişiklikten sonra Lighthouse laboratuvar değeri.",
            },
            f"lead.cwv-{_m}-needs-improvement": {
                "en": "Lab value in Lighthouse after each change.",
                "tr": "Her değişiklikten sonra Lighthouse laboratuvar değeri.",
            },
        }
    )


def rate(metric: str, value: float) -> str:
    good, poor = THRESHOLDS[metric]
    return "good" if value <= good else ("needs-improvement" if value <= poor else "poor")


def parse_psi(data: dict[str, Any], url: str) -> CheckOutput:
    """Turn a PSI JSON response into findings. Field p75 values win over lab values."""
    out = CheckOutput()
    audits = data.get("lighthouseResult", {}).get("audits", {})
    field = (data.get("loadingExperience") or {}).get("metrics", {})
    values: dict[str, tuple[float, str]] = {}
    lab = {
        "lcp": audits.get("largest-contentful-paint", {}).get("numericValue"),
        "cls": audits.get("cumulative-layout-shift", {}).get("numericValue"),
    }
    for m, v in lab.items():
        if isinstance(v, (int, float)):
            values[m] = (float(v), "lab")
    for m, key in (
        ("lcp", "LARGEST_CONTENTFUL_PAINT_MS"),
        ("inp", "INTERACTION_TO_NEXT_PAINT"),
        ("cls", "CUMULATIVE_LAYOUT_SHIFT_SCORE"),
    ):
        p75 = field.get(key, {}).get("percentile")
        if isinstance(p75, (int, float)):
            values[m] = (float(p75) / 100.0 if m == "cls" else float(p75), "field")
    for m, (v, src) in values.items():
        r = rate(m, v)
        if r != "good":
            unit = "" if m == "cls" else " ms"
            shown = f"{v:.3g}" if m == "cls" else f"{v:.0f}"
            where = "PageSpeed mobile lab" if src == "lab" else "field"
            out.findings.append(
                make_finding(
                    f"cwv-{m}-{r}", url=url, evidence=f"{m.upper()} {shown}{unit} ({where})"
                )
            )
    out.facts.update(
        {
            f"cwv_{m}": {"value": v, "source": s, "rating": rate(m, v)}
            for m, (v, s) in values.items()
        }
    )
    if "inp" not in values:
        out.not_checked.append(
            NotChecked(check_id="cwv-inp-poor", reason_code="field-data-unavailable")
        )
    return out
