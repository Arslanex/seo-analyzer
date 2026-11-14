"""Visibility signals: public, keyless, informational (belge 11 s.3.6).

None of these is proof of indexing or a ranking estimate, and none is part of the score:
* RDAP says how old the registration is (a young domain needs time),
* Wayback says how long the site has been archivable,
* Common Crawl says whether a large public crawl knows the site (a proxy, not Google).
Whether Google indexed a page is only answerable through Search Console (not connected).
``notes`` holds stable CODES; the report translates them.
"""

from __future__ import annotations

import asyncio
from typing import Any

from seoa.domain import VisibilitySignals
from seoa.infrastructure.integrations._public_http import Session, host_of, make_session
from seoa.infrastructure.integrations.commoncrawl import lookup_commoncrawl
from seoa.infrastructure.integrations.rdap import lookup_rdap, registrable_domain
from seoa.infrastructure.integrations.wayback import lookup_wayback


async def _safe(coro: Any) -> dict[str, Any]:
    try:
        res = await coro
    except Exception as exc:  # one source failing must never break the others
        return {"error": f"internal-error: {type(exc).__name__}"}
    return dict(res)


def notes_for(v: VisibilitySignals) -> list[str]:
    notes: list[str] = []
    age = v.rdap.get("age_days")
    if isinstance(age, int):
        if age < 180:
            notes.append("domain-under-180-days")
        elif age < 365:
            notes.append("domain-under-1-year")
    if not v.wayback.get("error") and v.wayback.get("urls_archived_sample") == 0:
        notes.append("no-wayback-captures")
    if v.common_crawl.get("present") is False:
        notes.append("not-in-common-crawl")
    notes.append("gsc-not-connected")
    return notes


async def collect_visibility(
    domain: str, *, session: Session | None = None, timeout_s: float = 30.0
) -> VisibilitySignals:
    host = host_of(domain)
    own = session is None
    sess = session or make_session(timeout_s)
    try:
        rdap, wb, cc = await asyncio.gather(
            _safe(lookup_rdap(registrable_domain(host), sess, timeout_s=timeout_s)),
            _safe(lookup_wayback(host, sess, timeout_s=timeout_s)),
            _safe(lookup_commoncrawl(host, sess, timeout_s=timeout_s)),
        )
    finally:
        if own:
            await sess.close()
    v = VisibilitySignals(
        domain=host, rdap=rdap, wayback=wb, common_crawl=cc, search_console={"connected": False}
    )
    v.notes = notes_for(v)
    return v
