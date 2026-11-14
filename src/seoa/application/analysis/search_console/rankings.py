"""Keyword rankings from the site's own Search Console data (belge 12 B1).

Only the owner's verified property can answer "where do I rank": no paid SERP provider is used and
nobody else's ranking is available. Everything here is informational and never part of the score.

Request budget: one ``query x page`` request per keyword (at most ``MAX_KEYWORDS``) plus one
``query`` request for the opportunity lists, so at most ``MAX_KEYWORDS + 1`` = 11 requests.
A 429 stops the remaining keyword requests (they are recorded as ``rate-limited``).

Heuristics (they are Search Console averages, not guarantees):

* **opportunity**: average position 4 to 20 with at least ``MIN_IMPRESSIONS`` impressions, the
  queries closest to page one or to the top three, most impressions first;
* **low CTR**: position <= 10, at least ``MIN_IMPRESSIONS`` impressions and a CTR under
  ``LOW_CTR_TOP3`` (positions 1-3) or ``LOW_CTR_TOP10`` (positions 4-10).

Search Console anonymises rare queries, so a keyword without data is "no data in the last 28
days", not "not ranking".
"""

from __future__ import annotations

import asyncio
from typing import Any

from seoa.application.ports import GscError, SearchConsolePort
from seoa.domain import KeywordRankings, KeywordRankRow, RankingQuery

MAX_KEYWORDS = 10
QUERY_ROWS = 250  # rows fetched for the opportunity lists
PAGE_ROWS = 25  # rows per keyword (query x page)
LIST_LIMIT = 15
MIN_IMPRESSIONS = 50
LOW_CTR_TOP3 = 0.05
LOW_CTR_TOP10 = 0.015


def _fold(text: str) -> str:
    return text.strip().casefold()


def clean_keywords(keywords: list[str] | None) -> list[str]:
    """Trimmed, de-duplicated (case-insensitive) keywords, at most ``MAX_KEYWORDS``."""
    out: list[str] = []
    seen: set[str] = set()
    for k in keywords or []:
        k = " ".join(str(k).split())[:80]
        if k and _fold(k) not in seen:
            seen.add(_fold(k))
            out.append(k)
    return out[:MAX_KEYWORDS]


def _num(v: Any) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _aggregate(keyword: str, rows: list[dict[str, Any]]) -> KeywordRankRow:
    """Collapse query x page rows into one row for ``keyword``.

    The exact query (case-insensitive) wins. Without one, the containing query with the most
    impressions is used and named in ``matched_query``. Position is impression-weighted.
    """
    by_query: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        keys = r.get("keys")
        if not isinstance(keys, list) or len(keys) < 2:
            continue
        by_query.setdefault(str(keys[0]), []).append(r)
    if not by_query:
        return KeywordRankRow(keyword=keyword, status="no-data")

    want = _fold(keyword)
    exact = [q for q in by_query if _fold(q) == want]
    if exact:
        chosen, matched = exact, None
    else:
        best = max(
            by_query, key=lambda q: (sum(_num(r.get("impressions")) for r in by_query[q]), q)
        )
        chosen, matched = [best], best
    pages = [r for q in chosen for r in by_query[q]]
    impressions = sum(int(_num(r.get("impressions"))) for r in pages)
    clicks = sum(int(_num(r.get("clicks"))) for r in pages)
    if impressions > 0:
        position = sum(_num(r.get("position")) * _num(r.get("impressions")) for r in pages)
        position /= impressions
    else:
        position = _num(pages[0].get("position")) if pages else 0.0
    top = max(
        pages,
        key=lambda r: (_num(r.get("impressions")), _num(r.get("clicks")), str(r["keys"][1])),
    )
    return KeywordRankRow(
        keyword=keyword,
        matched_query=matched,
        impressions=impressions,
        clicks=clicks,
        ctr=(clicks / impressions) if impressions else 0.0,
        position=round(position, 2),
        top_page=str(top["keys"][1]),
        status="ok",
    )


def _query(r: dict[str, Any]) -> RankingQuery | None:
    keys = r.get("keys")
    if not isinstance(keys, list) or not keys:
        return None
    return RankingQuery(
        query=str(keys[0]),
        impressions=int(_num(r.get("impressions"))),
        clicks=int(_num(r.get("clicks"))),
        ctr=_num(r.get("ctr")),
        position=_num(r.get("position")),
    )


def opportunity_lists(
    rows: list[dict[str, Any]],
) -> tuple[list[RankingQuery], list[RankingQuery]]:
    """(opportunities, low-CTR queries) from the property's query rows."""
    queries = [q for q in (_query(r) for r in rows) if q is not None]
    opps = [q for q in queries if 4 <= q.position <= 20 and q.impressions >= MIN_IMPRESSIONS]
    low = [
        q
        for q in queries
        if 0 < q.position <= 10
        and q.impressions >= MIN_IMPRESSIONS
        and q.ctr < (LOW_CTR_TOP3 if q.position <= 3 else LOW_CTR_TOP10)
    ]
    opps.sort(key=lambda q: (-q.impressions, q.query))
    low.sort(key=lambda q: (-q.impressions, q.query))
    return opps[:LIST_LIMIT], low[:LIST_LIMIT]


async def collect_rankings(
    client: SearchConsolePort, prop: str, keywords: list[str] | None, days: int
) -> KeywordRankings:
    """Never raises. A failing keyword becomes ``status="error"``, a failing list ``error``."""
    kws = clean_keywords(keywords)
    out = KeywordRankings(period_days=days, keywords_requested=len(kws))
    limited = False
    sem = asyncio.Semaphore(3)

    async def one(kw: str) -> KeywordRankRow:
        nonlocal limited
        async with sem:
            if limited:
                return KeywordRankRow(keyword=kw, status="error", error="rate-limited")
            try:
                rows = await client.search_analytics(
                    prop,
                    days=days,
                    dimensions=["query", "page"],
                    row_limit=PAGE_ROWS,
                    query=kw,
                    query_operator="contains",
                )
            except GscError as exc:
                if exc.code == "rate-limited":
                    limited = True
                return KeywordRankRow(keyword=kw, status="error", error=exc.code)
            except Exception as exc:  # noqa: BLE001  one keyword must not lose the others
                return KeywordRankRow(
                    keyword=kw, status="error", error=f"internal-error: {type(exc).__name__}"
                )
            return _aggregate(kw, rows)

    async def lists() -> None:
        try:
            rows = await client.search_analytics(
                prop, days=days, dimensions=["query"], row_limit=QUERY_ROWS
            )
        except GscError as exc:
            out.error = exc.code
            return
        except Exception as exc:  # noqa: BLE001
            out.error = f"internal-error: {type(exc).__name__}"
            return
        out.opportunities, out.low_ctr = opportunity_lists(rows)

    rank_rows, _ = await asyncio.gather(asyncio.gather(*(one(k) for k in kws)), lists())
    out.rows = list(rank_rows)
    return out
