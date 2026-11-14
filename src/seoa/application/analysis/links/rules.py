"""Rules of the link analysis, the duplicate-content detector (belge 11 s.3.1, s.3.5).

Thresholds are heuristics (marked ``heuristic=True``): none of them is a published search
engine rule. ``deep-page`` follows the upstream project ``skills/seo-technical/SKILL.md`` ("important
pages within 3 clicks of homepage"); the others are our own conservative choices.

Importing this module registers every rule in ``seoa.checks.registry``.
"""

from __future__ import annotations

from seoa.application.analysis.links import messages as messages_links  # noqa: F401  (registers messages)
from seoa.domain import Category, Severity
from seoa.domain.rules.registry import CheckDef, register

L, C = Category.LINKS, Category.CONTENT
M, LOW = Severity.MEDIUM, Severity.LOW

# (id, category, severity, heuristic, effort, impact, modes)
_SPECS: tuple[tuple[str, Category, Severity, bool, str, str, tuple[str, ...]], ...] = (
    ("broken-internal-link", L, M, False, "S", "medium", ("page", "site")),
    ("broken-external-link", L, LOW, False, "S", "low", ("page", "site")),
    ("internal-redirect-link", L, LOW, False, "S", "low", ("page", "site")),
    ("orphan-page", L, M, True, "M", "medium", ("site",)),
    ("deep-page", L, LOW, True, "M", "low", ("site",)),
    ("too-many-links", L, LOW, True, "M", "low", ("page", "site")),
    ("no-internal-links", L, LOW, False, "S", "medium", ("site",)),
    ("nofollow-internal-links", L, LOW, True, "S", "low", ("page", "site")),
    ("placeholder-links", L, LOW, True, "S", "medium", ("page", "site")),
    ("duplicate-content", C, M, True, "M", "medium", ("site",)),
)

for _id, _cat, _sev, _heur, _effort, _impact, _modes in _SPECS:
    register(
        CheckDef(
            id=_id,
            category=_cat,
            severity=_sev,
            scope="page",
            heuristic=_heur,
            effort_default=_effort,  # type: ignore[arg-type]
            impact_default=_impact,  # type: ignore[arg-type]
            message_key=f"finding.{_id}",
            recommendation_key=f"rec.{_id}",
            failure_check_key=f"fail.{_id}",
            leading_indicator_key=f"lead.{_id}",
            modes=_modes,
        )
    )

LINK_RULE_IDS = tuple(s[0] for s in _SPECS)
