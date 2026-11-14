"""First/last Internet Archive capture of a domain (Wayback CDX API, keyless). Informational only.

Two requests (the directive said one per source, but first and last capture need two orderings):
the oldest unique URLs (also the sample count, capped at 100, meaning "at least") and the newest
capture. No captures is a valid answer (``urls_archived_sample == 0``), not an error.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

from seoa.infrastructure.integrations._public_http import Session, get_text, host_of

CDX = "https://web.archive.org/cdx/search/cdx"
SAMPLE_LIMIT = 100


def _date(ts: str) -> str | None:
    return f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]}" if len(ts) >= 8 and ts[:8].isdigit() else None


async def _cdx(session: Session, url: str, timeout_s: float) -> tuple[Any, str | None]:
    """CDX answers an empty BODY (not ``[]``) when nothing matches: that is "no captures", not bad JSON."""
    status, text, err = await get_text(session, url, timeout_s=timeout_s)
    if err:
        return None, err
    if status != 200:
        return None, f"http-{status}"
    if not (text or "").strip():
        return [], None
    try:
        return json.loads(text or ""), None
    except ValueError:
        return None, "bad-json"


def _rows(data: Any) -> list[list[str]]:
    """CDX JSON: first row is the header; an empty result is [] or None."""
    if not isinstance(data, list) or len(data) < 2:
        return []
    return [r for r in data[1:] if isinstance(r, list) and r]


async def lookup_wayback(
    domain: str, session: Session, *, timeout_s: float = 30.0
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "first_capture": None,
        "last_capture": None,
        "captures": 0,
        "urls_archived_sample": 0,
        "error": None,
    }
    host = host_of(domain)
    if not host:
        out["error"] = "invalid-domain"
        return out
    q = f"{CDX}?url={quote(host)}&matchType=domain&output=json"
    first, err = await _cdx(
        session,
        f"{q}&fl=timestamp,original&collapse=urlkey&limit={SAMPLE_LIMIT}",
        timeout_s=timeout_s,
    )
    if err:
        out["error"] = err
        return out
    rows = _rows(first)
    if not rows:
        return out
    stamps = sorted(r[0] for r in rows if r and isinstance(r[0], str))
    out["first_capture"] = _date(stamps[0]) if stamps else None
    out["urls_archived_sample"] = out["captures"] = min(len(rows), SAMPLE_LIMIT)
    last, err = await _cdx(session, f"{q}&fl=timestamp&sort=reverse&limit=1", timeout_s=timeout_s)
    if err:
        out["error"] = f"last-capture-{err}"  # the first part is still valid
        return out
    lr = _rows(last)
    out["last_capture"] = _date(lr[0][0]) if lr and isinstance(lr[0][0], str) else None
    return out
