"""SERP truncation, image header parsing and social card findings (offline)."""

from __future__ import annotations

import base64
import struct
import zlib
from pathlib import Path

from seoa.application.analysis.modules import previews as mp
from seoa.application.analysis.plugin import AnalysisInputs
from seoa.config import Settings
from seoa.domain import AuditMode, FetchResult
from seoa.domain.parsing.html import parse_html
from tests.support.fixture_fetcher import FixtureFetcher

WEBP_1X1 = base64.b64decode("UklGRiIAAABXRUJQVlA4IBYAAAAwAQCdASoBAAEADsD+JaQAA3AAAAAA")


def png(w: int, h: int) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
        + chunk(b"IEND", b"")
    )


def jpeg(w: int, h: int) -> bytes:
    app0 = (
        b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00" + b"\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    )
    com = b"\xff\xfe" + struct.pack(">H", 8) + b"abcdef"
    sof = b"\xff\xc0" + struct.pack(">HBHHB", 11, 8, h, w, 1) + b"\x01\x11\x00"
    return b"\xff\xd8" + app0 + com + sof + b"\xff\xd9"


def webp_vp8l(w: int, h: int) -> bytes:
    bits = (w - 1) | ((h - 1) << 14)
    payload = b"\x2f" + bits.to_bytes(4, "little") + b"\x00" * 4
    body = b"WEBP" + b"VP8L" + struct.pack("<I", len(payload)) + payload
    return b"RIFF" + struct.pack("<I", len(body)) + body


def webp_vp8x(w: int, h: int) -> bytes:
    payload = b"\x00\x00\x00\x00" + (w - 1).to_bytes(3, "little") + (h - 1).to_bytes(3, "little")
    body = b"WEBP" + b"VP8X" + struct.pack("<I", len(payload)) + payload
    return b"RIFF" + struct.pack("<I", len(body)) + body


def test_image_headers() -> None:
    assert mp.image_info(png(1200, 630)) == {"format": "png", "width": 1200, "height": 630}
    assert mp.image_info(jpeg(800, 418)) == {"format": "jpeg", "width": 800, "height": 418}
    assert mp.image_info(WEBP_1X1) == {"format": "webp", "width": 1, "height": 1}
    assert mp.image_info(webp_vp8l(1200, 630)) == {"format": "webp", "width": 1200, "height": 630}
    assert mp.image_info(webp_vp8x(1920, 1005)) == {"format": "webp", "width": 1920, "height": 1005}
    assert mp.image_info(b"GIF89a" + struct.pack("<HH", 30, 20)) == {
        "format": "gif",
        "width": 30,
        "height": 20,
    }
    assert mp.image_info(b"<html>") is None
    assert mp.image_info(b"") is None
    assert mp.image_info(b"\x89PNG\r\n\x1a\n") is None  # truncated header
    assert mp.image_info(b"\xff\xd8\xff\xe0\x00") is None  # truncated jpeg


def test_title_truncation_is_pixel_based_not_character_based() -> None:
    short = "Coffee beans | Shop"
    assert mp.truncate_px(short, 580) == (short, False)
    long_t = "Best Specialty Coffee Beans and Brewing Equipment Online Store for Home Baristas"
    shown, cut = mp.truncate_px(long_t, 580)
    assert cut and shown.endswith("…") and 45 <= len(shown) <= 62
    assert long_t.startswith(shown[:-1].rstrip())
    # 30 wide capitals are wider than 30 narrow letters
    assert mp.text_px("W" * 30) > mp.text_px("i" * 30) * 2
    assert mp.truncate_px("W" * 40, 580)[1] and not mp.truncate_px("i" * 80, 580)[1]


def test_description_truncation_and_missing() -> None:
    d = "word " * 60
    shown, cut = mp.truncate_chars(d, 160)
    assert cut and len(shown) <= 160 and shown.endswith("…")
    assert mp.truncate_chars("short", 160) == ("short", False)
    serp = mp.build_serp("https://www.x.test/a/b", "T", "")
    assert [s.device for s in serp] == ["desktop", "mobile"] and serp[0].description_missing
    serp2 = mp.build_serp("https://x.test/", "T", "x" * 140)
    assert not serp2[0].description_truncated and serp2[1].description_truncated  # 160 vs 120


def test_display_url_breadcrumb() -> None:
    assert mp.display_url("https://www.example.com/blog/my-post") == "example.com › blog › my-post"
    assert mp.display_url("https://example.com/") == "example.com"
    assert mp.display_url("https://example.com/a/b/c/d").endswith("› …")


def _inputs(html: str, fetcher: FixtureFetcher, tmp_path: Path) -> AnalysisInputs:
    url = "https://x.test/page"
    return AnalysisInputs(
        audit_id="a", mode=AuditMode.PAGE, entry_url=url, origin="https://x.test",
        entry_fetch=FetchResult(url=url, final_url=url), entry_html=html,
        entry_parsed=parse_html(html, url), pages=[], fetcher=fetcher, renderer=None,
        settings=Settings(data_dir=tmp_path), lang="en", output_lang="en", options={},
        robots=None, save_file=None,  # type: ignore[arg-type]
    )  # fmt: skip


def _page(og_image: str | None, twitter: bool = False) -> str:
    og = f"<meta property='og:image' content='{og_image}'>" if og_image else ""
    tw = "<meta name='twitter:card' content='summary_large_image'>" if twitter else ""
    return (
        "<html><head><title>Hello</title><meta property='og:title' content='Hello'>"
        f"{og}{tw}</head><body></body></html>"
    )


async def _run(html: str, files: dict[str, tuple[int, dict[str, str], bytes]], tmp_path: Path):  # noqa: ANN202
    res = await mp.PreviewsModule().run(_inputs(html, FixtureFetcher(files), tmp_path))
    return res, {f.id for f in res.findings}


async def test_good_card_has_no_image_findings(tmp_path: Path) -> None:
    files = {"https://x.test/og.png": (200, {"content-type": "image/png"}, png(1200, 630))}
    res, ids = await _run(_page("https://x.test/og.png", twitter=True), files, tmp_path)
    assert ids == set()
    img = res.data.social.image  # type: ignore[union-attr]
    assert img.reachable and (img.width, img.height, img.ratio) == (1200, 630, 1.9)
    assert res.data.serp  # type: ignore[union-attr]


async def test_small_wrong_ratio_and_missing_twitter(tmp_path: Path) -> None:
    files = {"https://x.test/og.jpg": (200, {"content-type": "image/jpeg"}, jpeg(600, 600))}
    _res, ids = await _run(_page("https://x.test/og.jpg"), files, tmp_path)
    assert ids == {"og-image-too-small", "og-image-wrong-ratio", "twitter-card-missing"}


async def test_unreachable_and_not_an_image(tmp_path: Path) -> None:
    _r, ids = await _run(_page("https://x.test/gone.png", True), {}, tmp_path)
    assert ids == {"og-image-unreachable"}
    html_files = {"https://x.test/fake.png": (200, {"content-type": "image/png"}, b"<html>")}
    res, ids2 = await _run(_page("https://x.test/fake.png", True), html_files, tmp_path)
    assert ids2 == {"og-image-unreachable"} and res.data.social.image.error == "not-an-image"  # type: ignore[union-attr]


async def test_relative_url_is_flagged_and_still_inspected(tmp_path: Path) -> None:
    files = {"https://x.test/og.png": (200, {"content-type": "image/png"}, png(1200, 630))}
    res, ids = await _run(_page("/og.png", True), files, tmp_path)
    assert ids == {"og-image-relative-url"}
    assert res.data.social.image.reachable  # type: ignore[union-attr]


async def test_no_og_image_adds_no_image_findings(tmp_path: Path) -> None:
    fetcher = FixtureFetcher({})
    res = await mp.PreviewsModule().run(_inputs(_page(None, True), fetcher, tmp_path))
    assert not res.findings and fetcher.requested == []  # existing rules cover the missing tag
    assert "og:image" in res.data.social.missing_og  # type: ignore[union-attr]


async def test_image_fetch_is_at_most_one_request_and_size_flagged(tmp_path: Path) -> None:
    big = png(1200, 630) + b"\x00" * 3_000_000
    fetcher = FixtureFetcher({"https://x.test/og.png": (200, {"content-type": "image/png"}, big)})
    res = await mp.PreviewsModule().run(
        _inputs(_page("https://x.test/og.png", True), fetcher, tmp_path)
    )
    assert fetcher.requested == ["https://x.test/og.png"]
    img = res.data.social.image  # type: ignore[union-attr]
    assert img.too_heavy and img.bytes_is_lower_bound


def test_rules_registered_with_both_languages() -> None:
    from seoa.domain.rules import registry

    for rid in mp._SPECS:
        d = registry.get(rid)
        assert d.category.value == "onpage"
        for key in (
            d.message_key,
            d.recommendation_key,
            d.failure_check_key,
            d.leading_indicator_key,
        ):
            assert registry.MESSAGES[key]["en"] and registry.MESSAGES[key]["tr"]
