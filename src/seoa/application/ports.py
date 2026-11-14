"""Ports: the contracts the application layer needs from the outside world.

Infrastructure implements them (``infrastructure.http.Fetcher`` implements ``FetcherLike``);
tests inject fakes (``tests/support``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from seoa.domain import FetchResult, Hop

MAX_PAGE_BYTES = 10 * 1024 * 1024


@dataclass
class RawResponse:
    """One HTTP response as bytes, before any decoding."""

    url: str
    final_url: str
    status: int | None
    headers: dict[str, str]
    body: bytes
    truncated: bool
    error: str | None = None
    redirect_chain: list[Hop] | None = None
    ttfb_ms: int | None = None
    total_ms: int | None = None


class FetcherLike(Protocol):
    """Outbound HTTP for user-supplied URLs (SSRF-safe in the real implementation)."""

    async def fetch(self, url: str, *, max_bytes: int = MAX_PAGE_BYTES) -> FetchResult: ...
    async def fetch_bytes(self, url: str, *, max_bytes: int = MAX_PAGE_BYTES) -> RawResponse: ...
    async def close(self) -> None: ...


class RenderUnavailable(RuntimeError):
    """The browser could not be started (not installed, sandbox problem)."""


class GscError(Exception):
    """A Search Console call failed. ``code`` is stable: no-permission, property-not-found,
    rate-limited, not-connected, http-<status>, timeout, unreachable, ..."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class SearchConsolePort(Protocol):
    """The Search Console calls the analysis needs (``infrastructure.integrations.gsc.GscClient``)."""

    oauth: (
        Any  # exposes ``status(user_id)`` -> {"configured": bool, "connected": bool, "email": ...}
    )
    user_id: str

    async def list_properties(self) -> list[dict[str, str]]: ...
    async def search_analytics(
        self,
        property: str,
        *,
        days: int = 28,
        dimensions: list[str] | None = None,
        row_limit: int = 25,
        query: str | None = None,
        query_operator: str = "contains",
    ) -> list[dict[str, Any]]: ...
    async def inspect_url(self, property: str, url: str) -> dict[str, Any]: ...
    async def list_sitemaps(self, property: str) -> list[dict[str, Any]]: ...
