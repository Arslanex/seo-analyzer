"""Connections page: which integrations are ready, with a test for each key."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import (
    HTMLResponse,
)

from seoa.domain.i18n import t as tr
from seoa.presentation.api.deps import Service, pick_lang
from seoa.presentation.api.web_context import GOOGLE_MESSAGES, app_ctx, google_card, key_flags
from seoa.presentation.web.html import render_template

router = APIRouter()


@router.get("/settings", response_model=None)
async def settings_page(
    request: Request,
    service: Service,
    lang: str | None = None,
    audit: Annotated[str | None, Query(max_length=64)] = None,
) -> HTMLResponse:
    lg = pick_lang(request, lang)
    rec = await service.get_audit(audit) if audit else None
    card = await google_card(request)
    flags = key_flags(service)
    msg = request.query_params.get("google")
    if card is None or not card["configured"]:
        g_text, g_action = tr(lg, "set.google.unconfigured"), None
    elif card["connected"]:
        g_text, g_action = tr(lg, "set.google.on", email=card["email"] or "—"), "disconnect"
    else:
        g_text, g_action = tr(lg, "set.google.off"), "connect"
    conns = [
        {
            "name": tr(lg, "set.google"),
            "ready": bool(card and card["connected"]),
            "text": g_text,
            "affects": tr(lg, "set.google.affects"),
            "action": g_action,
        },
        {
            "name": tr(lg, "set.gkey"),
            "ready": flags["gkey"],
            "text": tr(lg, "set.gkey.on" if flags["gkey"] else "set.gkey.off"),
            "affects": tr(lg, "set.gkey.affects"),
            "action": None,
            "test": "gkey" if flags["gkey"] else None,
        },
        {
            "name": tr(lg, "set.opr"),
            "ready": flags["opr"],
            "text": tr(lg, "set.opr.on" if flags["opr"] else "set.opr.off"),
            "affects": tr(lg, "set.opr.affects"),
            "action": None,
            "test": "opr" if flags["opr"] else None,
            "link": "https://keywordseverywhere.com/account/openpagerank",
        },
        {
            "name": tr(lg, "set.ai"),
            "ready": flags["ai"],
            "text": tr(lg, "set.ai.on" if flags["ai"] else "set.ai.off"),
            "affects": tr(lg, "set.ai.affects") + " " + tr(lg, "set.ai.testcost"),
            "action": None,
            "test": "ai" if flags["ai"] else None,
        },
    ]
    html = render_template(
        "app_settings.html",
        lg,
        title=f"{tr(lg, 'set.title')} · {tr(lg, 'nav.settings')}",
        page="settings",
        conns=conns,
        n_ready=sum(1 for c in conns if c["ready"]),
        n_missing=sum(1 for c in conns if not c["ready"]),
        spend=await service.spend(),
        google_msg=msg if msg in GOOGLE_MESSAGES else None,
        **await app_ctx(request, lg, active="settings", audit=rec),
    )
    return HTMLResponse(html)
