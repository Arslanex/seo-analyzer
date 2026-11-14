"""FixtureFetcher: serves canned responses; the e2e seam (belge 08 FS2). Never used in production."""

from __future__ import annotations

from datetime import UTC, datetime

from seoa.application.ports import MAX_PAGE_BYTES, RawResponse
from seoa.domain import FetchResult
from seoa.domain.text import decode_body


class FixtureFetcher:
    """pages: url -> (status, headers, body bytes). Unknown URLs -> 404."""

    def __init__(
        self,
        pages: dict[str, tuple[int, dict[str, str], bytes]],
        errors: dict[str, str] | None = None,
    ) -> None:
        self.pages = pages
        self.errors = errors or {}  # url -> error code, e.g. "unreachable", "tls-handshake-failed"
        self.requested: list[str] = []

    async def fetch_bytes(self, url: str, *, max_bytes: int = MAX_PAGE_BYTES) -> RawResponse:
        self.requested.append(url)
        if url in self.errors:
            return RawResponse(
                url, url, None, {}, b"", False, f"{self.errors[url]}: fixture", [], None, 5
            )
        status, headers, body = self.pages.get(
            url, (404, {"content-type": "text/plain"}, b"not found")
        )
        return RawResponse(
            url,
            url,
            status,
            {k.lower(): v for k, v in headers.items()},
            body[:max_bytes],
            len(body) > max_bytes,
            None,
            [],
            5,
            10,
        )

    async def fetch(self, url: str, *, max_bytes: int = MAX_PAGE_BYTES) -> FetchResult:
        raw = await self.fetch_bytes(url, max_bytes=max_bytes)
        if raw.error:
            code, _, detail = raw.error.partition(": ")
            return FetchResult(
                url=url,
                final_url=raw.final_url,
                error=code,
                error_detail=detail,
                fetched_at=datetime.now(UTC),
            )
        ctype = raw.headers.get("content-type")
        html = (
            decode_body(raw.body, ctype)
            if raw.body
            and (ctype or "").startswith(("text/", "application/xhtml", "application/xml"))
            else None
        )
        return FetchResult(
            url=url,
            final_url=raw.final_url,
            status=raw.status,
            headers=raw.headers,
            content_type=ctype,
            html=html,
            html_bytes=len(raw.body),
            ttfb_ms=5,
            total_ms=10,
            fetched_at=datetime.now(UTC),
        )

    async def close(self) -> None:
        return None
