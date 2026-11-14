"""What every server-rendered page needs: menu state, audited site, language switch."""

from __future__ import annotations

import inspect
import os
from typing import Any
from urllib.parse import urlencode, urlparse

from fastapi import Request

from seoa.application.reporting.schema import AuditReport
from seoa.domain import AuditRecord
from seoa.domain.i18n import t as tr
from seoa.domain.text import clean_text
from seoa.presentation.api.deps import Service

GOOGLE_MESSAGES = ("connected", "disconnected")


async def google_card(request: Request) -> dict[str, Any] | None:
    """The home-page Google card; None (card hidden) when no status provider is wired."""
    provider = getattr(request.app.state, "google_status", None)
    if provider is None:
        return None
    raw = provider()
    if inspect.isawaitable(raw):
        raw = await raw
    return {
        "configured": bool(raw.get("configured")),
        "connected": bool(raw.get("connected")),
        "email": clean_text(str(raw["email"]))[:254] if raw.get("email") else None,
    }


# the order the design shows the eight categories in (tabs, cards)
CATEGORY_ORDER = [
    "technical",
    "onpage",
    "content",
    "links",
    "images",
    "schema",
    "ai_readiness",
    "performance",
]


def ordered_categories(report: AuditReport) -> list[Any]:
    rank = {c: i for i, c in enumerate(CATEGORY_ORDER)}
    return sorted(report.scores.categories, key=lambda c: rank.get(c.id.value, 99))


def overview_stats(report: AuditReport, lg: str) -> list[dict[str, str]]:
    """The four numbers next to the score: LCP, indexable pages, broken links, critical/high."""
    wanted = [
        tr(lg, k) for k in ("glance.lcp", "glance.indexable", "glance.broken", "glance.issues")
    ]
    by_label = {i.label: i.value for i in report.glance.items}
    return [{"label": w, "value": by_label[w]} for w in wanted if w in by_label]


def nav_audit(rec: AuditRecord) -> dict[str, Any]:
    sc = rec.scores
    score = sc.overall if sc is not None and not sc.insufficient_data else None
    return {
        "id": rec.id,
        "host": urlparse(rec.target_url).hostname or rec.target_url,
        "mode": rec.mode.value,
        "score": score,
    }


async def app_ctx(
    request: Request,
    lang: str,
    *,
    active: str,
    audit: AuditRecord | None = None,
    show_side: bool = True,
) -> dict[str, Any]:
    """Context every app-shell page needs: menu state, the audited site, the language switch."""
    other = "en" if lang == "tr" else "tr"
    query = {**dict(request.query_params), "lang": other}
    card = await google_card(request)
    return {
        "show_side": show_side,
        "nav_active": active,
        "nav_audit": nav_audit(audit) if audit is not None else None,
        "google_connected": None if card is None else bool(card["connected"]),
        "lang_url": f"{request.url.path}?{urlencode(query)}",
    }


def latest_per_site(audits: list[Any], limit: int = 6) -> list[Any]:
    """The newest audit of each site (host without www.), newest first."""
    seen: set[str] = set()
    out: list[Any] = []
    for a in audits:
        host = (urlparse(a.target_url).hostname or a.target_url).removeprefix("www.")
        if host not in seen:
            seen.add(host)
            out.append(a)
    return out[:limit]


def key_flags(service: Service) -> dict[str, bool]:
    from seoa.infrastructure.integrations.psi import api_key

    cfg = getattr(service, "settings", None)
    return {
        "ai": bool(getattr(cfg, "anthropic_api_key", None) or os.environ.get("ANTHROPIC_API_KEY")),
        "gkey": bool(api_key()),
        "opr": bool(
            getattr(cfg, "openpagerank_key", None) or os.environ.get("SEOA_OPENPAGERANK_KEY")
        ),
    }
