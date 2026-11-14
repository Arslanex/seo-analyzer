"""Shared HTTP helpers for the keyless public-data lookups (RDAP, Wayback, Common Crawl).

The targets are fixed hosts, but the session still goes through ``SafeResolver`` and every
URL (and every redirect hop) through ``check_url``: the same rule as for user URLs, no exceptions.
Errors never raise: callers get a short stable code (``timeout``, ``unreachable``,
``target-rejected``, ``http-<status>``, ``too-large``).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from urllib.parse import urljoin, urlparse

import aiohttp

from seoa.config import get_settings
from seoa.domain.url_safety import URLSafetyError, check_url
from seoa.infrastructure.http.resolver import BlockedAddressError, SafeResolver

MAX_BODY = 2 * 1024 * 1024
MAX_REDIRECTS = 3
Session = Any  # aiohttp.ClientSession or a test double with the same ``get`` shape


def make_session(
    timeout_s: float = 30.0, resolver: SafeResolver | None = None
) -> aiohttp.ClientSession:
    s = get_settings()
    return aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(
            resolver=resolver or SafeResolver(), use_dns_cache=False, limit=10
        ),
        timeout=aiohttp.ClientTimeout(total=timeout_s),
        headers={
            "User-Agent": f"{s.bot_name} (+{s.bot_info_url})",
            "Accept": "application/json, */*;q=0.5",
        },
    )


async def get_text(
    session: Session, url: str, *, timeout_s: float = 30.0
) -> tuple[int | None, str | None, str | None]:
    """GET ``url`` (https only). Returns (status, body text, error code)."""
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        try:
            target = check_url(current)
        except URLSafetyError:
            return None, None, "target-rejected"
        if target.scheme != "https":
            return None, None, "target-rejected"
        try:
            async with asyncio.timeout(timeout_s):
                async with session.get(current, allow_redirects=False) as resp:
                    if resp.status in (301, 302, 303, 307, 308) and resp.headers.get("Location"):
                        current = urljoin(current, resp.headers["Location"])
                        continue
                    buf = bytearray()
                    async for chunk in resp.content.iter_chunked(65536):
                        buf.extend(chunk)
                        if len(buf) > MAX_BODY:
                            return resp.status, None, "too-large"
                    raw = bytes(buf)
                    return resp.status, raw.decode("utf-8", "replace"), None
        except BlockedAddressError:
            return None, None, "target-rejected"
        except TimeoutError:
            return None, None, "timeout"
        except aiohttp.ClientConnectorError as exc:
            return (
                None,
                None,
                "target-rejected"
                if isinstance(exc.os_error, BlockedAddressError)
                else "unreachable",
            )
        except aiohttp.ClientError:
            return None, None, "unreachable"
    return None, None, "redirect-loop"


async def get_json(
    session: Session, url: str, *, timeout_s: float = 30.0
) -> tuple[Any, str | None]:
    """Returns (parsed JSON | None, error code | None). 404 is reported as ``http-404``."""
    status, text, err = await get_text(session, url, timeout_s=timeout_s)
    if err:
        return None, err
    if status != 200 or text is None:
        return None, f"http-{status}"
    try:
        return json.loads(text), None
    except ValueError:
        return None, "bad-json"


def host_of(value: str) -> str:
    """Bare lower-case host from a domain or URL (no scheme, port, path, or leading dot)."""
    v = value.strip().lower()
    if "://" not in v:
        v = "//" + v
    return (urlparse(v).hostname or "").strip(".")
