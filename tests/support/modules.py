"""Shared builders for the module tests: AnalysisInputs, scripted fetcher, fake robots."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from seoa.application.analysis.plugin import AnalysisInputs
from seoa.application.analysis.types import AnalysisPage
from seoa.application.ports import MAX_PAGE_BYTES, RawResponse
from seoa.config import Settings
from seoa.domain import AuditMode, FetchResult, Hop
from seoa.domain.parsing.html import parse_html

HOST = "https://example.com"


class Scripted:
    """url -> (status, headers, body). Unknown URLs answer 404. Records every request."""

    def __init__(self, table: dict[str, tuple[int, dict[str, str], str]] | None = None):
        self.table = table or {}
        self.requested: list[str] = []

    async def fetch_bytes(self, url: str, *, max_bytes: int = MAX_PAGE_BYTES) -> RawResponse:
        self.requested.append(url)
        status, headers, body = self.table.get(url, (404, {}, ""))
        return RawResponse(
            url,
            url,
            status,
            {k.lower(): v for k, v in headers.items()},
            body.encode(),
            False,
            None,
            [],
            1,
            1,
        )

    async def fetch(self, url: str, *, max_bytes: int = MAX_PAGE_BYTES) -> FetchResult:
        self.requested.append(url)
        status, headers, body = self.table.get(url, (404, {}, ""))
        hdrs = {k.lower(): v for k, v in headers.items()}
        # a "redirect:<target>" body models a redirect that was followed
        final = url
        if body.startswith("redirect:"):
            final = body.split(":", 1)[1]
            status, body = 200, ""
        return FetchResult(
            url=url,
            final_url=final,
            status=status,
            headers=hdrs,
            html=body or None,
            html_bytes=len(body),
            redirect_chain=[Hop(url=url, status=301)] if final != url else [],
        )

    async def close(self) -> None:
        return None


def page(
    path: str,
    html: str,
    *,
    status: int = 200,
    headers: dict[str, str] | None = None,
    kind: str = "core",
) -> AnalysisPage:
    url = path if path.startswith("http") else f"{HOST}{path}"
    return AnalysisPage(
        url=url,
        final_url=url,
        status=status,
        headers={k.lower(): v for k, v in (headers or {}).items()},
        parsed=parse_html(html, url),
        sample_kind=kind,  # type: ignore[arg-type]
    )


def inputs(
    pages: list[AnalysisPage],
    fetcher: Any = None,
    *,
    robots_raw: Any = None,
    entry: str = f"{HOST}/",
    entry_html: str = "",
) -> AnalysisInputs:
    parsed = parse_html(entry_html, entry) if entry_html else None
    if parsed is None and pages and pages[0].parsed is not None:
        parsed = pages[0].parsed
    return AnalysisInputs(
        audit_id="a1",
        mode=AuditMode.SITE,
        entry_url=entry,
        origin=HOST,
        entry_fetch=FetchResult(url=entry, final_url=entry, status=200),
        entry_html=entry_html,
        entry_parsed=parsed,
        pages=pages,
        fetcher=fetcher or Scripted(),
        renderer=None,
        settings=Settings(anthropic_api_key=None),
        lang="en",
        output_lang="en",
        options={},
        robots=SimpleNamespace(available=True, raw=robots_raw, sitemaps=[], findings=[]),
        save_file=_nosave,
    )


async def _nosave(name: str, data: bytes) -> str:
    return name
