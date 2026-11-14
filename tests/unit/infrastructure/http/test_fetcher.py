"""Fetcher against a local aiohttp server. The URL policy is relaxed ONLY here (test seam)."""

from __future__ import annotations

import socket
from collections.abc import AsyncIterator

import pytest
from aiohttp import web
from aiohttp.abc import AbstractResolver

from seoa.application.crawl.politeness import HostLimiter
from seoa.config import Settings
from seoa.domain.text import decode_body
from seoa.domain.url_safety import Target, URLSafetyError, check_url
from seoa.infrastructure.http.fetcher import Fetcher


class _Local(AbstractResolver):
    async def resolve(self, host, port=0, family=socket.AF_INET):
        return [
            {
                "hostname": host,
                "host": "127.0.0.1",
                "port": port,
                "family": socket.AF_INET,
                "proto": 0,
                "flags": 0,
            }
        ]

    async def close(self) -> None:
        return None


def _allow_local(url: str) -> Target:
    from urllib.parse import urlparse

    p = urlparse(url)
    return Target(url, p.scheme, p.hostname or "", p.port or 80, False)


@pytest.fixture
async def base() -> AsyncIterator[str]:
    app = web.Application()

    async def ok(r: web.Request) -> web.Response:
        return web.Response(text="<html><title>hi</title></html>", content_type="text/html")

    async def red(r: web.Request) -> web.Response:
        raise web.HTTPFound("/ok")

    async def loop(r: web.Request) -> web.Response:
        raise web.HTTPFound("/loop")

    async def big(r: web.Request) -> web.Response:
        return web.Response(body=b"x" * 200_000, content_type="text/html")

    async def latin(r: web.Request) -> web.Response:
        return web.Response(
            body="<p>caf\xe9</p>".encode("latin-1"),
            headers={"Content-Type": "text/html; charset=iso-8859-9"},
        )

    async def pdf(r: web.Request) -> web.Response:
        return web.Response(body=b"%PDF-1.4", content_type="application/pdf")

    for p, h in (
        ("/ok", ok),
        ("/red", red),
        ("/loop", loop),
        ("/big", big),
        ("/latin", latin),
        ("/pdf", pdf),
    ):
        app.router.add_get(p, h)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
    yield f"http://pinned.test:{port}"
    await runner.cleanup()


def _fetcher() -> Fetcher:
    return Fetcher(
        Settings(), limiter=HostLimiter(4, 0.0), resolver=_Local(), url_check=_allow_local
    )  # type: ignore[arg-type]


async def test_fetch_ok(base: str) -> None:
    f = _fetcher()
    r = await f.fetch(f"{base}/ok")
    await f.close()
    assert (
        r.status == 200
        and "<title>hi</title>" in (r.html or "")
        and r.error is None
        and r.ttfb_ms is not None
    )


async def test_redirect_followed_and_recorded(base: str) -> None:
    f = _fetcher()
    r = await f.fetch(f"{base}/red")
    await f.close()
    assert r.status == 200 and r.final_url.endswith("/ok") and r.redirect_chain[0].status == 302


async def test_redirect_loop(base: str) -> None:
    f = _fetcher()
    r = await f.fetch(f"{base}/loop")
    await f.close()
    assert r.error == "redirect-loop"


async def test_truncation(base: str) -> None:
    f = _fetcher()
    r = await f.fetch(f"{base}/big", max_bytes=1000)
    await f.close()
    assert r.truncated and r.html_bytes == 1000


async def test_non_html_has_no_text(base: str) -> None:
    f = _fetcher()
    r = await f.fetch(f"{base}/pdf")
    await f.close()
    assert r.html is None and r.content_type == "application/pdf"


async def test_charset_from_header(base: str) -> None:
    f = _fetcher()
    r = await f.fetch(f"{base}/latin")
    await f.close()
    assert "café" in (r.html or "")


async def test_production_policy_rejects_loopback_and_never_connects() -> None:
    f = Fetcher(Settings())  # real policy + real SafeResolver
    r = await f.fetch("http://127.0.0.1:9/")
    r2 = await f.fetch("http://localhost/")
    r3 = await f.fetch("http://169.254.169.254/latest/meta-data/")
    await f.close()
    assert [x.error for x in (r, r2, r3)] == ["target-rejected"] * 3


async def test_redirect_to_ip_literal_is_refused_by_the_hop_check() -> None:
    """The P1 lesson: aiohttp skips the resolver for IP literals, so each hop is checked."""
    from aiohttp import web as w

    app = w.Application()

    async def evil(r: w.Request) -> w.Response:
        raise w.HTTPFound("http://127.0.0.1:1/secret")

    app.router.add_get("/evil", evil)
    runner = w.AppRunner(app)
    await runner.setup()
    site = w.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]

    def check(url: str) -> Target:  # allow only the first hop's host, real policy for the rest
        return _allow_local(url) if "pinned.test" in url else check_url(url)

    f = Fetcher(Settings(), limiter=HostLimiter(2, 0.0), resolver=_Local(), url_check=check)  # type: ignore[arg-type]
    r = await f.fetch(f"http://pinned.test:{port}/evil")
    await f.close()
    await runner.cleanup()
    assert r.error == "target-rejected" and "127.0.0.1" in r.final_url


def test_decode_body_bom_and_meta() -> None:
    assert decode_body(b"\xef\xbb\xbfhello", None) == "hello"
    assert "ş" in decode_body('<meta charset="iso-8859-9"><p>\xfe</p>'.encode("latin-1"), None)


def test_url_policy_unused_import_guard() -> None:
    with pytest.raises(URLSafetyError):
        check_url("http://10.0.0.1/")


def test_repeated_headers_are_joined_not_dropped() -> None:
    from multidict import CIMultiDict

    from seoa.infrastructure.http.fetcher import _collect_headers

    h = CIMultiDict(
        [
            ("X-Robots-Tag", "noindex"),
            ("X-Robots-Tag", "googlebot: nofollow"),
            ("Set-Cookie", "a=1"),
            ("Set-Cookie", "b=2"),
        ]
    )
    out = _collect_headers(h)
    assert out["x-robots-tag"] == "noindex, googlebot: nofollow" and out["set-cookie"] == "a=1\nb=2"
