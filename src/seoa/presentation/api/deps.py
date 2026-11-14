"""Shared helpers for routes."""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, Request

from seoa.application.audit.protocol import AuditService
from seoa.domain.i18n import norm_lang


def get_service(request: Request) -> AuditService:
    return cast(AuditService, request.app.state.service)


Service = Annotated[AuditService, Depends(get_service)]


def pick_lang(request: Request, lang: str | None) -> str:
    """?lang wins, then Accept-Language, then the default (tr)."""
    if lang:
        return norm_lang(lang)
    header = request.headers.get("accept-language", "").lower()
    for part in header.split(","):
        code = part.split(";")[0].strip()[:2]
        if code in ("tr", "en"):
            return code
    return norm_lang(None)
