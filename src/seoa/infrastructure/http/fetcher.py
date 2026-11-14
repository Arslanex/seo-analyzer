"""The single outbound HTTP client for user-supplied URLs.

Every request and every redirect hop passes ``policy.check_url`` first; hostnames
are additionally judged by ``SafeResolver`` at connect time (belge 05 s.5.2, P1).
Redirects are followed manually (``allow_redirects=False``).
"""

from __future__ import annotations

import asyncio
import ssl
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin

import aiohttp

from seoa.application.crawl.politeness import HostLimiter
from seoa.application.ports import MAX_PAGE_BYTES, RawResponse
from seoa.config import Settings, get_settings
from seoa.domain import FetchResult, Hop
from seoa.domain.text import decode_body
from seoa.domain.url_safety import Target, URLSafetyError, check_url
from seoa.infrastructure.http.resolver import BlockedAddressError, DNSResolutionError, SafeResolver

MAX_REDIRECTS = 5
_REDIRECT = {301, 302, 303, 307, 308}
_TEXT_TYPES = ("text/html", "application/xhtml", "text/plain", "application/xml", "text/xml")


def _collect_headers(raw: Any) -> dict[str, str]:
    """Lower-cased headers; repeated headers are joined (X-Robots-Tag: a, b), cookies by newline."""
    out: dict[str, list[str]] = {}
    for k, v in raw.items():
        out.setdefault(k.lower(), []).append(v)
    return {k: ("\n" if k == "set-cookie" else ", ").join(v) for k, v in out.items()}


class Fetcher:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        limiter: HostLimiter | None = None,
        resolver: SafeResolver | None = None,
        url_check: Callable[[str], Target] = check_url,  # injection seam for tests only
    ) -> None:
        self.settings = settings or get_settings()
        self.limiter = limiter or HostLimiter(
            self.settings.per_host_concurrency, self.settings.request_delay_s
        )
        self._url_check = url_check
        self._resolver = resolver or SafeResolver()
        self._session: aiohttp.ClientSession | None = None
        self.user_agent = (
            f"Mozilla/5.0 (compatible; {self.settings.bot_name}; +{self.settings.bot_info_url})"
        )

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(resolver=self._resolver, use_dns_cache=False, limit=50)
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=aiohttp.ClientTimeout(total=self.settings.fetch_timeout_s),
                headers={
                    "User-Agent": self.user_agent,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Encoding": "gzip, deflate",  # Accept-Language deliberately absent
                },
                auto_decompress=True,
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    # ------------------------------------------------------------------ core

    async def fetch_bytes(self, url: str, *, max_bytes: int = MAX_PAGE_BYTES) -> RawResponse:
        t0 = time.monotonic()
        chain: list[Hop] = []
        current = url
        ttfb: int | None = None
        session = self._get_session()
        for _ in range(MAX_REDIRECTS + 1):
            try:
                target = self._url_check(current)
            except URLSafetyError as exc:
                return RawResponse(
                    url, current, None, {}, b"", False, f"target-rejected: {exc}", chain
                )
            host = target.hostname
            if self.limiter.is_open(host):
                return RawResponse(url, current, None, {}, b"", False, "circuit-open", chain)
            try:
                async with self.limiter.slot(host):
                    async with session.get(current, allow_redirects=False) as resp:
                        ttfb = int((time.monotonic() - t0) * 1000)
                        headers = _collect_headers(resp.headers)
                        status = resp.status
                        if status in _REDIRECT and headers.get("location"):
                            chain.append(Hop(url=current, status=status))
                            current = urljoin(current, headers["location"])
                            self.limiter.record(host, True)
                            continue
                        body = bytearray()
                        truncated = False
                        async for chunk in resp.content.iter_chunked(65536):
                            body.extend(chunk)
                            if len(body) > max_bytes:
                                truncated = True
                                del body[max_bytes:]
                                break
                        self.limiter.record(host, status < 500 and status != 429)
                        return RawResponse(
                            url,
                            current,
                            status,
                            headers,
                            bytes(body),
                            truncated,
                            None,
                            chain,
                            ttfb,
                            int((time.monotonic() - t0) * 1000),
                        )
            except BlockedAddressError as exc:
                return RawResponse(
                    url, current, None, {}, b"", False, f"target-rejected: {exc}", chain
                )
            except aiohttp.ClientConnectorCertificateError as exc:
                self.limiter.record(host, False)
                return RawResponse(
                    url, current, None, {}, b"", False, f"tls-handshake-failed: {exc}", chain
                )
            except (ssl.SSLError, aiohttp.ClientSSLError) as exc:
                self.limiter.record(host, False)
                return RawResponse(
                    url, current, None, {}, b"", False, f"tls-handshake-failed: {exc}", chain
                )
            except aiohttp.ClientConnectorError as exc:
                self.limiter.record(host, False)
                inner = exc.os_error
                code = (
                    "target-rejected" if isinstance(inner, BlockedAddressError) else "unreachable"
                )
                if isinstance(inner, DNSResolutionError):
                    code = "unreachable"
                return RawResponse(url, current, None, {}, b"", False, f"{code}: {inner}", chain)
            except (TimeoutError, asyncio.TimeoutError):
                self.limiter.record(host, False)
                return RawResponse(url, current, None, {}, b"", False, "timeout", chain)
            except aiohttp.ClientError as exc:
                self.limiter.record(host, False)
                return RawResponse(url, current, None, {}, b"", False, f"fetch-error: {exc}", chain)
        return RawResponse(url, current, None, {}, b"", False, "redirect-loop", chain)

    async def fetch(self, url: str, *, max_bytes: int = MAX_PAGE_BYTES) -> FetchResult:
        raw = await self.fetch_bytes(url, max_bytes=max_bytes)
        ctype = raw.headers.get("content-type")
        html: str | None = None
        if (
            raw.error is None
            and raw.body
            and (ctype is None or ctype.lower().startswith(_TEXT_TYPES))
        ):
            html = decode_body(raw.body, ctype)
        code, _, detail = (raw.error or "").partition(": ")
        return FetchResult(
            url=url,
            final_url=raw.final_url,
            status=raw.status,
            headers=raw.headers,
            redirect_chain=raw.redirect_chain or [],
            content_type=ctype,
            html=html,
            html_bytes=len(raw.body),
            truncated=raw.truncated,
            ttfb_ms=raw.ttfb_ms,
            total_ms=raw.total_ms,
            error=code or None,
            error_detail=detail or None,
            fetched_at=datetime.now(UTC),
        )
