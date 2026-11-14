"""Is the domain in the newest Common Crawl index? (CDX server, keyless.) Informational only.

Common Crawl is a public web crawl, a *proxy* for "known to a large crawler". It says nothing about
Google's index. A 404 / "no captures" answer is ``present=False``.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

from seoa.infrastructure.integrations._public_http import Session, get_json, get_text, host_of

COLLINFO = "https://index.commoncrawl.org/collinfo.json"
SAMPLE_LIMIT = 50


async def lookup_commoncrawl(
    domain: str, session: Session, *, timeout_s: float = 30.0
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "collection": None,
        "present": None,
        "pages_seen_sample": 0,
        "error": None,
    }
    host = host_of(domain)
    if not host:
        out["error"] = "invalid-domain"
        return out
    info, err = await get_json(session, COLLINFO, timeout_s=timeout_s)
    if err:
        out["error"] = f"collinfo-{err}"
        return out
    if (
        not isinstance(info, list)
        or not info
        or not isinstance(info[0], dict)
        or not info[0].get("cdx-api")
    ):
        out["error"] = "bad-json"
        return out
    out["collection"] = info[0].get("id")
    api = str(info[0]["cdx-api"])
    status, text, err = await get_text(
        session,
        f"{api}?url={quote(host)}/*&output=json&limit={SAMPLE_LIMIT}&fl=url",
        timeout_s=timeout_s,
    )
    if err:
        out["error"] = err
        return out
    if status == 404:
        out["present"] = False  # "No Captures found" arrives as a 404 with a JSON message
        return out
    if status != 200:  # a 5xx is a server problem, never "the site is absent"
        out["error"] = f"http-{status}"
        return out
    if not (text or "").strip():
        out["present"] = False
        return out
    urls = 0
    for line in (text or "").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get("url"):
            urls += 1
    out["present"] = urls > 0
    out["pages_seen_sample"] = min(urls, SAMPLE_LIMIT)
    return out
