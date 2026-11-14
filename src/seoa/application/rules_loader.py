"""Fills the rule and message registry.

Rules and messages register themselves when their module is imported. Scoring and report
building need the *full* catalogue whichever process builds them (API server, CLI, tests), so
they call ``load_all_rules()`` instead of relying on import order.
"""

from __future__ import annotations

import importlib

# Every module that declares rules or message texts (idempotent to import).
RULE_MODULES = (
    "seoa.domain.rules.rules_page",
    "seoa.domain.rules.messages_page",
    "seoa.domain.rules.rules_site",
    "seoa.domain.rules.messages_site",
    "seoa.domain.rules.schema_checks",
    "seoa.application.analysis.links.rules",
    "seoa.application.analysis.links.messages",
    "seoa.application.analysis.performance.rules",
    "seoa.application.analysis.performance.messages",
    "seoa.application.analysis.performance.web_vitals",
    "seoa.application.analysis.search_console.rules",
    "seoa.application.analysis.search_console.messages",
    "seoa.application.audit.rules",
)


def load_all_rules() -> None:
    """Import every module that registers rules or messages, then the analysis modules."""
    for name in RULE_MODULES:
        importlib.import_module(name)
    from seoa.application.analysis.plugin import load_module_files

    load_module_files()
