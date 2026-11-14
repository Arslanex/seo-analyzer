"""The 47 page rules, registered (ported from the upstream project page_checks.py ``CHECKS``).

Severity is the source's, id for id: Critical 2 / High 6 / Medium 24 / Low 15. The parity test
compares ``severity_for`` of the source module with this table. Category, effort and impact
are our decisions (the source has no categories).
"""

from __future__ import annotations

from seoa.domain import Category as C
from seoa.domain import Severity as S
from seoa.domain.rules import messages_page  # noqa: F401  (registers the texts)
from seoa.domain.rules.registry import CheckDef, register

# (id, category, severity, heuristic, effort, impact, requires)
_T = tuple[str, C, S, bool, str, str, tuple[str, ...]]

_TABLE: list[_T] = [
    ("missing-title", C.ONPAGE, S.HIGH, False, "S", "high", ()),
    ("title-too-long", C.ONPAGE, S.MEDIUM, True, "S", "low", ()),
    ("title-too-short", C.ONPAGE, S.MEDIUM, True, "S", "medium", ()),
    ("missing-meta-description", C.ONPAGE, S.MEDIUM, False, "S", "medium", ()),
    ("meta-description-too-long", C.ONPAGE, S.MEDIUM, True, "S", "low", ()),
    ("duplicate-meta-tags", C.ONPAGE, S.MEDIUM, False, "S", "medium", ()),
    ("missing-h1", C.ONPAGE, S.MEDIUM, False, "S", "medium", ()),
    ("multiple-h1", C.ONPAGE, S.LOW, False, "S", "low", ()),
    ("heading-level-skip", C.ONPAGE, S.LOW, False, "S", "low", ()),
    ("missing-canonical", C.TECHNICAL, S.MEDIUM, False, "S", "medium", ()),
    ("canonical-points-elsewhere", C.TECHNICAL, S.HIGH, False, "S", "high", ()),
    ("og-url-differs-from-canonical", C.ONPAGE, S.LOW, False, "S", "low", ()),
    ("noindex", C.TECHNICAL, S.CRITICAL, False, "S", "high", ()),
    ("noindex-header", C.TECHNICAL, S.CRITICAL, False, "M", "high", ("headers",)),
    ("nofollow", C.TECHNICAL, S.MEDIUM, False, "S", "medium", ()),
    ("meta-refresh-redirect", C.TECHNICAL, S.MEDIUM, False, "M", "medium", ()),
    ("hreflang-missing-self", C.TECHNICAL, S.MEDIUM, False, "S", "medium", ()),
    ("missing-doctype", C.TECHNICAL, S.LOW, False, "S", "low", ()),
    ("missing-charset", C.TECHNICAL, S.MEDIUM, False, "S", "low", ()),
    ("charset-mismatch", C.TECHNICAL, S.MEDIUM, False, "S", "medium", ("headers",)),
    ("missing-lang", C.ONPAGE, S.MEDIUM, False, "S", "low", ()),
    ("missing-viewport", C.ONPAGE, S.MEDIUM, False, "S", "medium", ()),
    ("uses-frames", C.TECHNICAL, S.HIGH, False, "L", "high", ()),
    ("deprecated-html-tags", C.TECHNICAL, S.LOW, False, "M", "low", ()),
    ("placeholder-text", C.CONTENT, S.HIGH, False, "S", "high", ()),
    ("images-missing-alt", C.IMAGES, S.MEDIUM, False, "M", "medium", ()),
    ("images-missing-dimensions", C.IMAGES, S.MEDIUM, False, "M", "medium", ()),
    ("first-image-lazy-loaded", C.IMAGES, S.MEDIUM, False, "S", "medium", ()),
    ("links-without-text", C.ONPAGE, S.MEDIUM, False, "M", "medium", ()),
    ("generic-anchor-text", C.ONPAGE, S.LOW, False, "M", "low", ()),
    ("links-to-http", C.TECHNICAL, S.LOW, False, "M", "low", ()),
    ("mixed-content", C.TECHNICAL, S.HIGH, False, "M", "high", ()),
    ("url-too-long", C.ONPAGE, S.LOW, True, "M", "low", ()),
    ("url-has-parameters", C.ONPAGE, S.MEDIUM, False, "M", "medium", ()),
    ("url-uppercase", C.ONPAGE, S.LOW, False, "M", "low", ()),
    ("url-underscores", C.ONPAGE, S.LOW, False, "M", "low", ()),
    ("url-non-ascii", C.ONPAGE, S.LOW, False, "S", "low", ()),
    ("url-double-slash", C.ONPAGE, S.LOW, False, "M", "low", ()),
    ("html-over-2mb", C.TECHNICAL, S.HIGH, False, "L", "high", ()),
    ("deep-dom", C.TECHNICAL, S.LOW, True, "L", "low", ()),
    ("wide-dom-node", C.TECHNICAL, S.LOW, True, "M", "low", ()),
    ("missing-open-graph", C.ONPAGE, S.MEDIUM, False, "S", "medium", ()),
    ("missing-og-image", C.ONPAGE, S.LOW, False, "S", "low", ()),
    ("invalid-jsonld", C.SCHEMA, S.MEDIUM, False, "S", "high", ()),
    ("title-not-reflected-in-content", C.CONTENT, S.MEDIUM, True, "M", "medium", ()),
    ("description-not-reflected-in-content", C.CONTENT, S.MEDIUM, True, "S", "low", ()),
    ("thin-content", C.CONTENT, S.MEDIUM, True, "L", "medium", ()),
]

_DEPENDS: dict[str, tuple[str, ...]] = {
    "og-url-differs-from-canonical": ("missing-canonical",),
    "missing-og-image": ("missing-open-graph",),
}


def _register_all() -> None:
    for rid, cat, sev, heur, effort, impact, req in _TABLE:
        register(
            CheckDef(
                id=rid,
                category=cat,
                severity=sev,
                heuristic=heur,
                effort_default=effort,  # type: ignore[arg-type]
                impact_default=impact,  # type: ignore[arg-type]
                failure_check_key="failure_check.rescan",
                leading_indicator_key=f"leading_indicator.{cat.value}",
                depends_on=_DEPENDS.get(rid, ()),
                requires=req,
            )
        )


_register_all()
PAGE_RULE_IDS: tuple[str, ...] = tuple(t[0] for t in _TABLE)
