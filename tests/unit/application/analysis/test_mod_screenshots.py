"""Screenshots module against local pages. The URL policy is relaxed ONLY for ``*.localhost``
(test seam, as in test_render_browser); every other target goes through the real policy."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from aiohttp import web

from seoa.application.analysis.modules import screenshots as ms
from seoa.application.analysis.plugin import AnalysisInputs
from seoa.config import Settings
from seoa.domain import AuditMode, FetchResult
from seoa.domain.url_safety import Target, check_url
from seoa.infrastructure.rendering import Renderer

PAGES = {
    "/good": "<html><head><meta name='viewport' content='width=device-width'></head><body>"
    "<h1>Welcome home</h1><p>Some intro text for visitors.</p>"
    "<a class='btn' href='/x'>Buy now</a></body></html>",
    "/deep-h1": "<html><head><meta name='viewport' content='width=device-width'></head><body>"
    "<div style='height:2000px'>spacer</div><h1>Far below</h1></body></html>",
    "/banner": "<html><head><meta name='viewport' content='width=device-width'></head><body>"
    "<h1>Page</h1><div id='cookie' style='position:fixed;left:0;right:0;bottom:0;top:30%;"
    "background:#222;color:#fff'>We use cookies <button>OK</button></div></body></html>",
    "/overflow": "<html><head><meta name='viewport' content='width=device-width'></head><body>"
    "<h1>Wide</h1><div style='width:2400px;height:10px;background:red'></div></body></html>",
}


def _relaxed(url: str) -> Target:
    p = urlsplit(url)
    host = (p.hostname or "").lower()
    if host.endswith(".localhost"):
        return Target(url, p.scheme, host, p.port or 80, False)
    return check_url(url)


async def _resolve(host: str) -> list[str]:
    return ["93.184.216.34"]


@pytest.fixture
async def port() -> AsyncIterator[int]:
    app = web.Application()

    def serve(html: str):  # type: ignore[no-untyped-def]
        async def handler(r: web.Request) -> web.Response:
            return web.Response(text=html, content_type="text/html")

        return handler

    for path, html in PAGES.items():
        app.router.add_get(path, serve(html))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    yield site._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
    await runner.cleanup()


@pytest.fixture
async def renderer() -> AsyncIterator[Renderer]:
    r = Renderer(url_check=_relaxed, resolve=_resolve)
    await r.start()
    if r._browser is None:
        pytest.skip(f"chromium unavailable: {r.launch_error}")
    yield r
    await r.close()


def _inputs(
    url: str, renderer: Renderer | None, saved: dict[str, bytes], tmp: Path
) -> AnalysisInputs:
    async def save(name: str, data: bytes) -> str:
        saved[name] = data
        return name

    return AnalysisInputs(
        audit_id="a", mode=AuditMode.PAGE, entry_url=url, origin=url,
        entry_fetch=FetchResult(url=url, final_url=url), entry_html="", entry_parsed=None,
        pages=[], fetcher=None, renderer=renderer, settings=Settings(data_dir=tmp),  # type: ignore[arg-type]
        lang="en", output_lang="en", options={}, robots=None, save_file=save,
    )  # fmt: skip


async def test_two_devices_saved_and_clean_page_has_no_findings(
    renderer: Renderer, port: int, tmp_path: Path
) -> None:
    saved: dict[str, bytes] = {}
    res = await ms.ScreenshotsModule().run(
        _inputs(f"http://app.localhost:{port}/good", renderer, saved, tmp_path)
    )
    assert set(saved) == {"desktop.jpg", "mobile.jpg"}
    assert all(b[:3] == b"\xff\xd8\xff" and len(b) <= ms.MAX_BYTES for b in saved.values())
    d = res.data
    assert {(f.device, f.width, f.height) for f in d.files} == {  # type: ignore[union-attr]
        ("desktop", 1366, 768),
        ("mobile", 780, 1688),
    }
    for dev in ("desktop", "mobile"):
        fold = d.above_fold[dev]  # type: ignore[union-attr]
        assert fold.h1_visible and fold.cta_visible and fold.text_chars > 20
        assert fold.overlay_share == 0 and not fold.horizontal_overflow
    assert res.findings == [] and res.not_checked == []


async def test_h1_below_the_fold_and_overlay_are_flagged(
    renderer: Renderer, port: int, tmp_path: Path
) -> None:
    res = await ms.ScreenshotsModule().run(
        _inputs(f"http://app.localhost:{port}/deep-h1", renderer, {}, tmp_path)
    )
    assert [f.id for f in res.findings] == ["above-fold-no-h1"]
    res2 = await ms.ScreenshotsModule().run(
        _inputs(f"http://app.localhost:{port}/banner", renderer, {}, tmp_path)
    )
    ids = [f.id for f in res2.findings]
    assert ids == ["intrusive-interstitial"]
    assert res2.data.above_fold["mobile"].overlay_share > 0.3  # type: ignore[union-attr]


async def test_horizontal_overflow_reported_on_mobile(
    renderer: Renderer, port: int, tmp_path: Path
) -> None:
    res = await ms.ScreenshotsModule().run(
        _inputs(f"http://app.localhost:{port}/overflow", renderer, {}, tmp_path)
    )
    assert res.data.above_fold["mobile"].horizontal_overflow  # type: ignore[union-attr]


async def test_no_renderer_is_not_checked(tmp_path: Path) -> None:
    res = await ms.ScreenshotsModule().run(_inputs("https://x.test/", None, {}, tmp_path))
    assert res.data is None and not res.findings
    assert [(n.check_id, n.reason_code) for n in res.not_checked] == [
        ("screenshots", "render-unavailable")
    ]


async def test_production_policy_rejects_loopback(renderer_prod: Renderer, tmp_path: Path) -> None:
    saved: dict[str, bytes] = {}
    res = await ms.ScreenshotsModule().run(
        _inputs("http://127.0.0.1:9/", renderer_prod, saved, tmp_path)
    )
    assert saved == {} and res.not_checked[0].reason_code == "target-rejected"


@pytest.fixture
async def renderer_prod() -> AsyncIterator[Renderer]:
    r = Renderer()
    yield r
    await r.close()


def test_rules_registered_with_both_languages() -> None:
    from seoa.domain.rules import registry

    for rid in ms._SPECS:
        d = registry.get(rid)
        assert d.category.value == "technical" and d.heuristic
        for key in (
            d.message_key,
            d.recommendation_key,
            d.failure_check_key,
            d.leading_indicator_key,
        ):
            assert registry.MESSAGES[key]["en"] and registry.MESSAGES[key]["tr"]
