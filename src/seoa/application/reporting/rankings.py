"""Keyword rankings section (belge 12 B1): Search Console only, informational, never scored.

Measured (with data) or not measured (with a reason), like every deep section. Query and page text
comes from Search Console but is attacker-influenceable (anyone can search for anything), so it
goes through ``clean_text`` and is autoescaped by the template.
"""

from __future__ import annotations

import re

from seoa.application.analysis.search_console import rankings as gr
from seoa.application.reporting import schema as s
from seoa.application.reporting.deep import _GSC_REASONS, not_measured
from seoa.domain import AuditRecord, KeywordRankRow, RankingQuery
from seoa.domain.i18n import CATALOG, t
from seoa.domain.text import clean_text

ROWS = 20
_CODE = re.compile(r"^[a-z0-9][a-z0-9 _:-]{0,40}$")


def _c(text: object, limit: int = 300) -> str:
    return clean_text(str(text))[:limit]


def _err(lang: str, code: str | None) -> str:
    code = code or ""
    key = f"rank.error.{code}"
    if key in CATALOG["en"]:
        return t(lang, key)
    return code if _CODE.match(code) else ""


def _row(lang: str, days: int, r: KeywordRankRow) -> s.RankingRow:
    if r.status == "ok":
        text = t(lang, "rank.status.ok")
    elif r.status == "no-data":
        text = t(lang, "rank.status.no-data", days=days)
    else:
        text = f"{t(lang, 'rank.status.error')}: {_err(lang, r.error)}".rstrip(": ")
    return s.RankingRow(
        keyword=_c(r.keyword, 80),
        matched_query=_c(r.matched_query, 200) if r.matched_query else None,
        impressions=r.impressions,
        clicks=r.clicks,
        ctr_pct=round(r.ctr * 100, 1),
        position=round(r.position, 1) if r.position is not None else None,
        top_page=_c(r.top_page, 2048) if r.top_page else None,
        status=r.status,
        status_text=text,
    )


def _q(r: RankingQuery) -> s.RankingQueryRow:
    return s.RankingQueryRow(
        query=_c(r.query, 200),
        impressions=r.impressions,
        clicks=r.clicks,
        ctr_pct=round(r.ctr * 100, 1),
        position=round(r.position, 1),
    )


def rankings_section(rec: AuditRecord, lang: str) -> s.RankingsSection:
    g = rec.gsc
    if g is None or g.status != "ok":
        reason = (
            "rankings-gsc-required"
            if g is None or g.status in ("not-connected", "not-configured")
            else _GSC_REASONS[g.status]
        )
        return s.RankingsSection(**not_measured(lang, reason))
    rk = g.rankings
    if rk is None:
        return s.RankingsSection(**not_measured(lang, "rankings-not-run"))
    if not rk.rows and not rk.opportunities and not rk.low_ctr:
        return s.RankingsSection(**not_measured(lang, "rankings-no-keywords"))
    return s.RankingsSection(
        status="measured",
        period_days=rk.period_days,
        keywords_requested=rk.keywords_requested,
        rows=[_row(lang, rk.period_days, r) for r in rk.rows[: gr.MAX_KEYWORDS]],
        opportunities=[_q(r) for r in rk.opportunities[: gr.LIST_LIMIT]],
        low_ctr=[_q(r) for r in rk.low_ctr[: gr.LIST_LIMIT]],
        keywords_note=t(lang, "rank.keywords.missing") if not rk.rows else "",
        list_error=t(lang, "rank.list.error", code=_err(lang, rk.error) or "error")
        if rk.error
        else "",
        note=t(lang, "rank.note", days=rk.period_days),
        rules_note=" ".join(
            [
                t(lang, "rank.opp.rule", min=gr.MIN_IMPRESSIONS),
                t(
                    lang,
                    "rank.low.rule",
                    top3=round(gr.LOW_CTR_TOP3 * 100, 1),
                    top10=round(gr.LOW_CTR_TOP10 * 100, 1),
                    min=gr.MIN_IMPRESSIONS,
                ),
            ]
        ),
    )
