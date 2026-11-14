"""Domain authority estimate from OpenPageRank (belge 12 B2). Optional: needs ``SEOA_OPENPAGERANK_KEY``.

``GET https://openpagerank.keywordseverywhere.com/api/v1.0/getPageRank?domains[]=<domain>`` with the key in the
``API-OPR`` header. The number is a THIRD-PARTY estimate (built from Common Crawl), not a Google
metric. The key travels only in that header: it is never put in a URL, a log line, an error code
or a result. Same safety rules as the other public lookups (``check_url`` on the URL, the
``SafeResolver`` at connect time, no redirects, a small body cap). Never raises: callers get a
short stable code in ``AuthoritySignal.error`` (``no-api-key``, ``timeout``, ``unreachable``,
``target-rejected``, ``unauthorized``, ``rate-limited``, ``http-<status>``, ``too-large``,
``bad-json``, ``no-data``).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from urllib.parse import quote

import aiohttp

from seoa.application.analysis.modules.authority import AuthoritySignal
from seoa.config import get_settings
from seoa.domain.url_safety import URLSafetyError, check_url
from seoa.infrastructure.http.resolver import BlockedAddressError, SafeResolver
from seoa.infrastructure.integrations._public_http import Session
from seoa.infrastructure.integrations.rdap import registrable_domain

# The service moved from openpagerank.com (now a 301) to Keywords Everywhere; keys of the old
# service no longer work. The legacy path still takes the key in the API-OPR header.
ENDPOINT = "https://openpagerank.keywordseverywhere.com/api/v1.0/getPageRank"
MAX_BODY = 64 * 1024


def api_key() -> str | None:
    return get_settings().openpagerank_key


def parse_response(data: Any, domain: str) -> AuthoritySignal:
    """First record of the ``response`` list; ``status_code`` 200 means the domain was found."""
    rows = data.get("response") if isinstance(data, dict) else None
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        return AuthoritySignal(domain=domain, error="bad-json")
    row = rows[0]
    if row.get("status_code") != 200:
        return AuthoritySignal(domain=domain, error="no-data")

    def num(v: Any) -> float | None:
        return float(v) if isinstance(v, int | float) and not isinstance(v, bool) else None

    dec = num(row.get("page_rank_decimal"))
    integer = num(row.get("page_rank_integer"))
    rank_raw = row.get("rank")
    rank = int(rank_raw) if isinstance(rank_raw, str) and rank_raw.isdigit() else None
    if isinstance(rank_raw, int) and not isinstance(rank_raw, bool):
        rank = rank_raw
    return AuthoritySignal(
        domain=domain,
        page_rank_decimal=dec,
        page_rank_integer=int(integer) if integer is not None else None,
        rank=rank,
    )


async def _get(
    session: Session, url: str, key: str, timeout_s: float
) -> tuple[int | None, bytes, str | None]:
    try:
        check_url(url)
    except URLSafetyError:
        return None, b"", "target-rejected"
    try:
        async with asyncio.timeout(timeout_s):
            async with session.get(
                url, headers={"API-OPR": key, "Accept": "application/json"}, allow_redirects=False
            ) as resp:
                buf = bytearray()
                async for chunk in resp.content.iter_chunked(8192):
                    buf.extend(chunk)
                    if len(buf) > MAX_BODY:
                        return resp.status, b"", "too-large"
                return resp.status, bytes(buf), None
    except BlockedAddressError:
        return None, b"", "target-rejected"
    except TimeoutError:
        return None, b"", "timeout"
    except aiohttp.ClientConnectorError as exc:
        blocked = isinstance(exc.os_error, BlockedAddressError)
        return None, b"", "target-rejected" if blocked else "unreachable"
    except aiohttp.ClientError:
        return None, b"", "unreachable"


async def fetch_authority(
    host: str, *, session: Session | None = None, key: str | None = None, timeout_s: float = 20.0
) -> AuthoritySignal:
    domain = registrable_domain(host)
    key = key or api_key()
    if not key:
        return AuthoritySignal(domain=domain, error="no-api-key")
    if not domain:
        return AuthoritySignal(domain=domain, error="no-data")
    own = session is None
    sess = session or aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(resolver=SafeResolver(), use_dns_cache=False, limit=2),
        timeout=aiohttp.ClientTimeout(total=timeout_s),
    )
    try:
        url = f"{ENDPOINT}?domains%5B%5D={quote(domain, safe='')}"
        status, body, err = await _get(sess, url, key, timeout_s)
    finally:
        if own:
            await sess.close()
    if err:
        return AuthoritySignal(domain=domain, error=err)
    if status in (401, 403):
        return AuthoritySignal(domain=domain, error="unauthorized")
    if status == 429:
        return AuthoritySignal(domain=domain, error="rate-limited")
    if status != 200:
        return AuthoritySignal(domain=domain, error=f"http-{status}")
    try:
        data = json.loads(body.decode("utf-8", "replace"))
    except ValueError:
        return AuthoritySignal(domain=domain, error="bad-json")
    return parse_response(data, domain)


__all__ = ["AuthoritySignal", "api_key", "fetch_authority", "parse_response"]
