"""Rule catalogue, spend and integration key tests."""

from __future__ import annotations

import os
from typing import Annotated, Any

from fastapi import APIRouter, Path

from seoa.domain.i18n import norm_lang
from seoa.domain.i18n import t as tr
from seoa.domain.rules import registry
from seoa.presentation.api.deps import Service

router = APIRouter()


@router.get("/rules")
async def rules() -> dict[str, Any]:
    data = [
        {
            "id": d.id,
            "severity": d.severity.value,
            "category": d.category.value,
            "layer": d.layer.value,
            "scope": d.scope,
            "heuristic": d.heuristic,
            "message_key": d.message_key,
            "effort_default": d.effort_default,
            "impact_default": d.impact_default,
        }
        for d in sorted(registry.RULES.values(), key=lambda x: x.id)
    ]
    return {"data": data, "count": len(data)}


@router.get("/spend")
async def spend(service: Service) -> dict[str, float]:
    return await service.spend()


def _opr_key(service: Service) -> str | None:
    cfg = getattr(service, "settings", None)
    return getattr(cfg, "openpagerank_key", None) or os.environ.get("SEOA_OPENPAGERANK_KEY") or None


def _test_code(name: str, error: str | None) -> str:
    """Map a provider's error code onto the few outcomes the settings page can explain."""
    if error is None or error == "no-data":  # no data for the sample site still means the key works
        return "ok"
    if error in ("unauthorized", "http-400", "http-401", "http-403"):
        return f"rejected.{name}"
    if error in ("rate-limited", "unreachable", "timeout"):
        return "unreachable" if error == "timeout" else error
    if error == "no-api-key":
        return "missing"
    return "other"


@router.post("/integrations/{name}/test")
async def test_integration(
    name: Annotated[str, Path(pattern="^(gkey|opr|ai)$")],
    service: Service,
    lang: str | None = None,
) -> dict[str, Any]:
    """Try a saved key against its provider with one harmless request. Never echoes the key."""
    from seoa.infrastructure.integrations.crux import fetch_crux
    from seoa.infrastructure.integrations.openpagerank import fetch_authority

    lg = norm_lang(lang)
    error: str | None
    if name == "ai":
        outcome = await service.test_llm()
        code = "rejected.ai" if outcome == "rejected" else outcome
        error = None if outcome == "ok" else outcome
    else:
        if name == "gkey":
            error = (await fetch_crux("https://web.dev/", "https://web.dev")).error
        else:
            error = (await fetch_authority("example.com", key=_opr_key(service))).error
        code = _test_code(name, error)
    ok = code == "ok"
    text = tr(lg, f"set.test.{code}") if code != "other" else tr(lg, "set.test.other", code=error)
    return {"ok": ok, "code": code, "message": text}
