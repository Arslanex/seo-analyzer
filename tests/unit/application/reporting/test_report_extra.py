"""Report sections and routes for local SEO, suggested sitemap and authority (belge 12)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import lxml.html
import pytest

from seoa.application.analysis.modules.local import (
    AddressEntry,
    LocalSeo,
    NapInconsistency,
    PhoneEntry,
)
from seoa.application.analysis.modules.sitemap_gen import (
    ExcludedPage,
    SitemapGenerated,
    build_sitemap,
)
from seoa.application.reporting import build_report
from seoa.application.reporting.quality import check_report
from seoa.application.rules_loader import load_all_rules
from seoa.domain import AuditMode, NotChecked
from seoa.domain.i18n import missing_keys
from seoa.infrastructure.integrations.openpagerank import AuthoritySignal
from seoa.presentation.api import create_app
from seoa.presentation.web.html import render_report_html
from tests.support.fake_service import FakeService, make_sample_record
from tests.support.modules import page

XSS = "<script>alert(1)</script>"
IDS = ("local", "sitemapgen", "authority")
OK = "<html><head><title>t</title></head><body>x</body></html>"


def _extras() -> dict[str, object]:
    gen = build_sitemap([page("/", OK), page(f"/{XSS}", OK), page("/n", OK, status=404)], set())
    gen.in_sitemap_not_indexable = [ExcludedPage(url=XSS, reason="noindex")]
    gen.in_sitemap_not_indexable_total = 1
    gen.missing_from_sitemap = [XSS]
    gen.missing_total = 1
    return {
        "local": LocalSeo(
            applicable=True,
            signals=["schema-local-business", "tel-link"],
            business_types=["Dentist"],
            names=[XSS],
            phones=[
                PhoneEntry(
                    number="+903125551234",
                    formats=[XSS],
                    pages=["https://e.com/"],
                    sources=["text"],
                )
            ],
            addresses=[AddressEntry(text=XSS, source="text", pages=["https://e.com/"])],
            inconsistencies=[
                NapInconsistency(
                    kind="phone",
                    code="schema-phones-differ",
                    values=[XSS, "+903125550000"],
                    pages=[XSS],
                )
            ],
            has_tel_link=True,
            pages_scanned=2,
            notes=["address-from-text-is-heuristic"],
        ).model_dump(),
        "sitemap_generated": gen.model_dump(),
        "authority": AuthoritySignal(
            domain=XSS, page_rank_decimal=4.5, page_rank_integer=4, rank=1234567
        ).model_dump(),
    }


def _record(extras: dict[str, object] | None, mode: AuditMode | None = None):  # type: ignore[no-untyped-def]
    rec = make_sample_record("gated", mode=mode)
    rec.extras = dict(extras or {})
    return rec


def test_catalog_parity() -> None:
    assert missing_keys() == set()


def test_sections_measured_clean_and_escaped() -> None:
    load_all_rules()
    for lang in ("tr", "en"):
        report = build_report(_record(_extras()), lang)
        for name in ("local", "sitemap_gen", "authority"):
            assert getattr(report, name).status == "measured", name
        html = render_report_html(report, lang)
        quality = check_report(report, html, lang=lang)
        assert not [c for c in quality.checks if c.status == "FAIL"], quality
        root = lxml.html.fromstring(html)
        for sid in IDS + ("sitemapgen",):
            assert root.xpath(f"//section[@id='sec-{sid}']"), sid
        assert XSS not in html
        assert "sitemap.xml" in html
        assert report.sitemap_gen.counts_toward_overall is False


def test_sections_without_data_say_why() -> None:
    load_all_rules()
    rec = _record(None)
    rec.not_checked += [
        NotChecked(check_id="local", reason_code="not-applicable"),
        NotChecked(check_id="sitemap_generated", reason_code="site-mode-only"),
        NotChecked(check_id="authority", reason_code="no-api-key"),
    ]
    report = build_report(rec, "en")
    assert report.local.not_measured_reason == "not-applicable"
    assert report.sitemap_gen.not_measured_reason == "site-mode-only"
    assert report.authority.not_measured_reason == "no-api-key"
    assert "SEOA_OPENPAGERANK_KEY" in (report.authority.not_measured_text or "")
    html = render_report_html(report, "en")
    quality = check_report(report, html, lang="en")
    assert not [c for c in quality.checks if c.status == "FAIL"], quality


def test_preview_is_capped_and_bad_data_is_not_measured() -> None:
    load_all_rules()
    big = SitemapGenerated(
        xml=build_sitemap([page(f"/p{i}", OK) for i in range(250)], set()).xml, urls_total=250
    )
    rec = _record({"sitemap_generated": big.model_dump(), "local": {"phones": "nope"}})
    report = build_report(rec, "en")
    assert report.sitemap_gen.urls_shown == 200
    assert report.sitemap_gen.xml_preview.count("<url>") == 200
    assert report.local.not_measured_reason == "suite-bad-data"


@pytest.fixture
def service() -> FakeService:
    svc = FakeService()
    svc.audits["aud_sample0001"].extras = _extras()
    return svc


@pytest.fixture
async def client(service: FakeService) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=create_app(service), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as c:
        yield c


async def test_sitemap_download_route(client: httpx.AsyncClient) -> None:
    r = await client.get("/v1/audits/aud_sample0001/sitemap.xml")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/xml")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "attachment" in r.headers["content-disposition"]
    assert r.text.startswith("<?xml") and "<urlset" in r.text
    assert XSS not in r.text  # escaped inside the XML


async def test_sitemap_route_404_without_data_or_audit(
    client: httpx.AsyncClient, service: FakeService
) -> None:
    service.audits["aud_sample0001"].extras = {}
    assert (await client.get("/v1/audits/aud_sample0001/sitemap.xml")).status_code == 404
    assert (await client.get("/v1/audits/nope/sitemap.xml")).status_code == 404


@pytest.mark.parametrize("name", ["local", "sitemap-suggestion", "authority"])
async def test_section_endpoints(client: httpx.AsyncClient, name: str) -> None:
    r = await client.get(f"/v1/audits/aud_sample0001/{name}?lang=en")
    assert r.status_code == 200 and r.json()["status"] == "measured"


async def test_report_json_has_new_sections(client: httpx.AsyncClient) -> None:
    b = (await client.get("/v1/audits/aud_sample0001/report?format=json&lang=en")).json()
    for key in ("local", "sitemap_gen", "authority"):
        assert key in b
    assert b["schema_version"] == "1.6.0"
