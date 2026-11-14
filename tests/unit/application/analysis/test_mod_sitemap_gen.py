"""mod_sitemap_gen: the suggested sitemap (belge 12 C5)."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from seoa.application.analysis import plugin
from seoa.application.analysis.modules.sitemap_gen import (
    SitemapGenerated,
    SitemapGenModule,
    exclusion_reason,
)
from seoa.domain import AuditMode
from tests.support.modules import HOST, inputs, page

OK = "<html><head><title>t</title></head><body><p>x</p></body></html>"
NOINDEX = '<html><head><meta name="robots" content="noindex"></head><body>x</body></html>'
ELSEWHERE = '<html><head><link rel="canonical" href="https://example.com/other"></head><body>x</body></html>'
NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}


async def _run(pages, sitemap: set[str] | None = None, mode: AuditMode = AuditMode.SITE):  # type: ignore[no-untyped-def]
    inp = inputs(pages)
    inp.mode = mode
    inp.sitemap_urls = sitemap or set()
    return await SitemapGenModule().run(inp)


def test_registered() -> None:
    assert "sitemap_gen" in plugin.MODULE_FILES
    assert "sitemap_generated" in {m.kind for m in plugin.modules()}


async def test_page_mode_is_not_checked() -> None:
    res = await _run([page("/", OK)], mode=AuditMode.PAGE)
    assert res.data is None and res.findings == []
    assert [(n.check_id, n.reason_code) for n in res.not_checked] == [
        ("sitemap_generated", "site-mode-only")
    ]


async def test_only_fit_pages_are_listed_and_xml_is_valid() -> None:
    pages = [
        page("/", OK, headers={"Last-Modified": "Wed, 21 Oct 2015 07:28:00 GMT"}),
        page("/a&b?x=1", OK),
        page("/gone", OK, status=404),
        page("/hidden", NOINDEX),
        page("/dup", ELSEWHERE),
        page("/hdr", OK, headers={"X-Robots-Tag": "noindex"}),
    ]
    res = await _run(pages)
    data = SitemapGenerated.model_validate(res.data.model_dump())  # type: ignore[union-attr]
    assert res.findings == []
    root = ET.fromstring(data.xml)  # well-formed, ampersand escaped
    locs = [e.text for e in root.findall("s:url/s:loc", NS)]
    assert locs == [f"{HOST}/", f"{HOST}/a&b?x=1"]
    lastmods = [e.text for e in root.findall("s:url/s:lastmod", NS)]
    assert lastmods == ["2015-10-21"]  # only where the server sent Last-Modified
    assert data.with_lastmod == 1 and data.urls_total == 2
    assert {e.reason for e in data.excluded} == {
        "status-4xx",
        "noindex",
        "canonical-elsewhere",
        "noindex-header",
    }


async def test_comparison_with_existing_sitemap() -> None:
    pages = [page("/", OK), page("/new", OK), page("/gone", OK, status=404)]
    res = await _run(pages, sitemap={f"{HOST}/", f"{HOST}/gone"})
    data = res.data  # type: ignore[assignment]
    assert data.existing_sitemap  # type: ignore[union-attr]
    assert data.missing_from_sitemap == [f"{HOST}/new"]  # type: ignore[union-attr]
    assert [(x.url, x.reason) for x in data.in_sitemap_not_indexable] == [  # type: ignore[union-attr]
        (f"{HOST}/gone", "status-4xx")
    ]


async def test_no_existing_sitemap_reports_no_missing_list() -> None:
    res = await _run([page("/", OK), page("/x", OK)])
    assert res.data.missing_from_sitemap == [] and not res.data.existing_sitemap  # type: ignore[union-attr]


async def test_nothing_eligible_is_not_checked() -> None:
    res = await _run([page("/", NOINDEX)])
    assert res.data is None
    assert res.not_checked[0].reason_code == "no-eligible-pages"


def test_redirected_and_error_pages_are_excluded() -> None:
    p = page("/old", OK)
    p.final_url = f"{HOST}/new"
    assert exclusion_reason(p) == "redirected"
    q = page("/x", OK)
    q.error = "timeout"
    assert exclusion_reason(q) == "fetch-error"
