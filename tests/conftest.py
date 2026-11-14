"""Shared test setup."""

from __future__ import annotations

import pytest

from seoa.application.rules_loader import load_all_rules


@pytest.fixture(scope="session", autouse=True)
def _rule_catalogue() -> None:
    """The scoring code expects the rule registry to be filled by whoever starts the process."""
    load_all_rules()
