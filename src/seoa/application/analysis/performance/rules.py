"""Rules produced by the lab performance / image / mobile measurement (belge 11 s.3.2-3.3).

The Core Web Vitals rules (``cwv-lcp-*``, ``cwv-cls-*``, ``cwv-inp-*``) are registered in
``integrations.psi`` and reused here for lab data. Everything below needs the ``lab`` measurement.
"""

from __future__ import annotations

from seoa.domain import Category, Severity
from seoa.domain.rules.registry import CheckDef, register

P, T, I = Category.PERFORMANCE, Category.TECHNICAL, Category.IMAGES  # noqa: E741

# Thresholds (module constants, used by perf_checks). Heuristic ones are marked in the rule.
PAGE_WEIGHT_BYTES = 3 * 1024 * 1024
MAX_REQUESTS = 100
RENDER_BLOCKING_MIN = 4
THIRD_PARTY_REQUESTS = 25
THIRD_PARTY_BYTES_SHARE = 0.40
MOBILE_SMALL_FONT_SHARE = 0.20
MOBILE_TAP_TARGETS_MIN = 3
NO_CACHE_MIN_FILES = 3

_LAB = ("lab",)


def _d(
    id_: str,
    cat: Category,
    sev: Severity,
    *,
    effort: str = "M",
    impact: str = "medium",
    heuristic: bool = False,
) -> CheckDef:
    return register(
        CheckDef(
            id_,
            cat,
            sev,
            heuristic=heuristic,
            effort_default=effort,  # type: ignore[arg-type]
            impact_default=impact,  # type: ignore[arg-type]
            requires=_LAB,
            modes=("page", "site"),
        )
    )


PERF_RULES = [
    _d("page-weight-heavy", P, Severity.MEDIUM, effort="M", impact="medium", heuristic=True),
    _d("too-many-requests", P, Severity.LOW, effort="M", impact="low", heuristic=True),
    _d("uncompressed-text-resources", P, Severity.MEDIUM, effort="S", impact="medium"),
    _d("static-assets-no-cache", P, Severity.LOW, effort="S", impact="low"),
    _d("render-blocking-resources", P, Severity.LOW, effort="M", impact="low", heuristic=True),
    _d("third-party-heavy", P, Severity.LOW, effort="M", impact="low", heuristic=True),
    _d("mobile-horizontal-scroll", T, Severity.MEDIUM, effort="M", impact="medium"),
    _d("mobile-tap-targets-small", T, Severity.LOW, effort="M", impact="low", heuristic=True),
    _d("mobile-font-too-small", T, Severity.LOW, effort="S", impact="low", heuristic=True),
    _d("image-too-large", I, Severity.MEDIUM, effort="S", impact="medium"),
    _d("image-critically-large", I, Severity.HIGH, effort="S", impact="high"),
    _d("image-oversized-for-display", I, Severity.LOW, effort="M", impact="low", heuristic=True),
    _d("image-legacy-format", I, Severity.LOW, effort="M", impact="low", heuristic=True),
]

# Every id the lab measurement can produce a verdict for (used for NotChecked on a failed render).
LAB_RULE_IDS = [d.id for d in PERF_RULES] + [
    f"cwv-{m}-{r}" for m in ("lcp", "cls") for r in ("poor", "needs-improvement")
]
MOBILE_RULE_IDS = ["mobile-horizontal-scroll", "mobile-tap-targets-small", "mobile-font-too-small"]
