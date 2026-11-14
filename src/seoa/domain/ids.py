"""Identifier generation."""

from __future__ import annotations

import uuid


def new_id() -> str:
    """A short random id for audits and pages."""
    return uuid.uuid4().hex[:16]
