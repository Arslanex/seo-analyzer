"""Rules fed by Search Console data (belge 11 s.3.6).

All of them ``requires=("gsc",)``: they apply only when the site owner connected Search Console
and the property was resolved. ``gsc-no-impressions`` is a heuristic (a new site has none).

Importing this module registers every rule in ``seoa.checks.registry``.
"""

from __future__ import annotations

from typing import Literal

from seoa.application.analysis.search_console import messages as messages_gsc  # noqa: F401  (registers messages)
from seoa.domain import Category, Severity
from seoa.domain.rules.registry import CheckDef, register

T = Category.TECHNICAL
H, M, LOW = Severity.HIGH, Severity.MEDIUM, Severity.LOW

# (id, severity, heuristic, scope, effort, impact)
_SPECS: tuple[tuple[str, Severity, bool, Literal["page", "site"], str, str], ...] = (
    ("gsc-page-not-indexed", H, False, "page", "M", "high"),
    ("gsc-canonical-mismatch", M, False, "page", "S", "medium"),
    ("gsc-robots-blocked", H, False, "page", "S", "high"),
    ("gsc-fetch-failed", M, False, "page", "M", "medium"),
    ("gsc-sitemap-errors", M, False, "site", "S", "medium"),
    ("gsc-sitemap-not-submitted", LOW, False, "site", "S", "low"),
    ("gsc-no-impressions", LOW, True, "site", "L", "medium"),
)

for _id, _sev, _heur, _scope, _effort, _impact in _SPECS:
    register(
        CheckDef(
            id=_id,
            category=T,
            severity=_sev,
            scope=_scope,
            heuristic=_heur,
            effort_default=_effort,  # type: ignore[arg-type]
            impact_default=_impact,  # type: ignore[arg-type]
            message_key=f"finding.{_id}",
            recommendation_key=f"rec.{_id}",
            failure_check_key=f"fail.{_id}",
            leading_indicator_key=f"lead.{_id}",
            requires=("gsc",),
        )
    )

GSC_RULE_IDS = tuple(s[0] for s in _SPECS)
