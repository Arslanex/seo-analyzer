from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import lxml.html
import pytest

from seoa.domain import AuditStatus
from seoa.presentation.api import create_app
from seoa.presentation.api.app import CSP
from tests.support.fake_service import FakeService, make_sample_record

AUD = "aud_sample0001"


@pytest.fixture
def service() -> FakeService:
    return FakeService()


@pytest.fixture
async def client(service: FakeService) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=create_app(service), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as c:
        yield c


# ------------------------------------------------------------------ security


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/healthz",
        "/v1/audits",
        f"/v1/audits/{AUD}",
        f"/audits/{AUD}/report",
        "/static/app.js",
        "/v1/audits/zzz",
        "/nope",
    ],
)
async def test_security_headers_on_every_response(client: httpx.AsyncClient, path: str) -> None:
    r = await client.get(path)
    assert r.headers["content-security-policy"] == CSP
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"] == "no-referrer"
    assert r.headers["x-frame-options"] == "DENY"


def test_csp_forbids_inline_scripts_and_foreign_origins() -> None:
    assert (
        "script-src 'self'" in CSP
        and "'unsafe-inline'" not in CSP.split("script-src")[1].split(";")[0]
    )
    assert (
        "default-src 'self'" in CSP
        and "frame-ancestors 'none'" in CSP
        and "object-src 'none'" in CSP
    )


async def test_cors_is_off(client: httpx.AsyncClient) -> None:
    r = await client.get("/v1/audits", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in r.headers
    pre = await client.options(
        "/v1/audits",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in pre.headers


async def test_api_responses_are_not_cacheable(client: httpx.AsyncClient) -> None:
    assert (await client.get("/v1/audits")).headers["cache-control"] == "no-store"


async def test_unexpected_errors_do_not_leak_details(service: FakeService) -> None:
    async def boom(limit: int = 20) -> list[object]:
        raise RuntimeError("secret-internal-path /etc/passwd")

    service.list_audits = boom  # type: ignore[method-assign,assignment]
    transport = httpx.ASGITransport(app=create_app(service), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as c:
        r = await c.get("/v1/audits")
        assert r.status_code == 500 and r.json()["code"] == "internal-error"
        assert "secret" not in r.text and "passwd" not in r.text
        page = await c.get("/")
        assert page.status_code == 500 and "secret" not in page.text


async def test_problem_core_members_cannot_be_overridden(client: httpx.AsyncClient) -> None:
    new = (await client.post("/v1/audits", json={"url": "queued2.example"})).json()["id"]
    body = (await client.get(f"/v1/audits/{new}/report")).json()
    assert body["status"] == 409 and body["audit_status"] == "queued"


async def test_http_methods_are_restricted(client: httpx.AsyncClient) -> None:
    r = await client.delete(f"/v1/audits/{AUD}")
    assert r.status_code == 405 and r.json()["code"] == "method-not-allowed"


async def test_xss_in_evidence_is_escaped_through_the_http_routes(service: FakeService) -> None:
    service.add(make_sample_record("gated", audit_id="aud_xss", xss=True))
    transport = httpx.ASGITransport(app=create_app(service), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as c:
        r = await c.get("/audits/aud_xss/report?lang=en")
        assert r.status_code == 200 and "<script>alert" not in r.text
        root = lxml.html.fromstring(r.text)
        assert not [s for s in root.iter("script") if not s.get("src")] and not root.xpath("//img")
        j = await c.get("/v1/audits/aud_xss/report", params={"lang": "en"})
        assert j.status_code == 200 and j.headers["content-type"].startswith("application/json")


# ------------------------------------------------------------------ pages


async def test_home_page(client: httpx.AsyncClient) -> None:
    r = await client.get("/", params={"lang": "en"})
    root = lxml.html.fromstring(r.text)
    assert r.status_code == 200 and root.get("lang") == "en"
    form = root.xpath("//form[@action='/ui/audits']")[0]
    assert form.get("method") == "post" and {
        i.get("name") for i in form.xpath(".//input|.//select")
    } >= {"url", "mode", "enable_llm", "lang"}
    assert root.xpath("//label[@for='url']") and "aud_sample0001" in r.text and "$0.0123" in r.text
    assert (await client.get("/", params={"lang": "tr"})).text.count(
        "Sitenizin SEO durumunu kanıtlarıyla görün."
    ) == 1


async def test_ui_create_redirects_to_the_progress_page(
    client: httpx.AsyncClient, service: FakeService
) -> None:
    r = await client.post(
        "/ui/audits",
        content=b"url=Example.com&mode=page&enable_llm=1&lang=en",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert (
        r.status_code == 303
        and r.headers["location"].startswith("/audits/aud_new")
        and r.headers["location"].endswith("lang=en")
    )
    assert service.calls[-1] == ("create_audit", ("https://Example.com", "page", None, True))
    assert service.last_lang == "en"  # the UI language is the language of the AI text too


async def test_ui_create_without_ai_checkbox(
    client: httpx.AsyncClient, service: FakeService
) -> None:
    await client.post(
        "/ui/audits",
        content=b"url=example.com&mode=site",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert service.calls[-1][1][3] is False


@pytest.mark.parametrize(
    "body", [b"url=", b"url=ftp%3A%2F%2Fx", b"mode=site", b"url=https%3A%2F%2Fu%3Ap%40example.com"]
)
async def test_ui_create_invalid_url_rerenders_with_an_error(
    client: httpx.AsyncClient, body: bytes
) -> None:
    r = await client.post(
        "/ui/audits",
        content=body + b"&lang=en",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 422
    root = lxml.html.fromstring(r.text)
    assert root.xpath("//*[@role='alert']") and "valid web address" in r.text


async def test_progress_page_then_redirect_to_report(client: httpx.AsyncClient) -> None:
    new = (await client.post("/v1/audits", json={"url": "progress.example"})).json()["id"]
    page = await client.get(f"/audits/{new}", params={"lang": "en"})
    root = lxml.html.fromstring(page.text)
    box = root.xpath("//*[@data-progress]")[0]
    assert page.status_code == 200 and box.get("data-audit-id") == new
    assert root.xpath("//script[@src='/static/app.js']") and root.xpath("//*[@role='progressbar']")
    assert [li.get("data-stage") for li in root.xpath("//ul[@id='stage-names']/li")][:3] == [
        "validate",
        "fetch_entry",
        "robots",
    ]
    await client.get(f"/v1/audits/{new}/events")  # drives the fake to completion
    done = await client.get(f"/audits/{new}", params={"lang": "en"})
    assert done.status_code == 200 and 'aria-current="page"' in done.text  # the overview page
    assert f"/audits/{new}/report?lang=en" in done.text  # the full report stays one click away


async def test_report_page_for_a_running_audit_redirects_to_progress(
    client: httpx.AsyncClient,
) -> None:
    new = (await client.post("/v1/audits", json={"url": "running.example"})).json()["id"]
    r = await client.get(f"/audits/{new}/report")
    assert r.status_code == 303 and r.headers["location"].startswith(f"/audits/{new}")


async def test_report_page_has_actions_qa_and_filters(client: httpx.AsyncClient) -> None:
    r = await client.get(f"/audits/{AUD}/report", params={"lang": "en", "severity": "Critical"})
    root = lxml.html.fromstring(r.text)
    assert r.status_code == 200
    assert root.xpath("//form[@data-qa-form]") and root.xpath("//button[@data-action-post]")
    assert len(root.xpath("//article[contains(@class,'finding')]")) == 1  # only the Critical group
    assert root.xpath(f"//a[contains(@href,'/v1/audits/{AUD}/report?format=json')]")
    assert (
        await client.get(f"/audits/{AUD}/report", params={"severity": "Nope"})
    ).status_code == 422
    assert (
        await client.get(f"/audits/{AUD}/report", params={"category": "nope"})
    ).status_code == 422


async def test_failed_audit_page_shows_a_friendly_error(client: httpx.AsyncClient) -> None:
    new = (await client.post("/v1/audits", json={"url": "fail.example"})).json()["id"]
    r = await client.get(f"/audits/{new}/report", params={"lang": "tr"})
    assert r.status_code == 200 and "ulaşılamadı" in r.text and "internal-host" not in r.text
    root = lxml.html.fromstring(r.text)
    assert not root.xpath("//form[@data-qa-form]")  # no Q&A without a report


async def test_unknown_audit_pages_are_404_problem_json(client: httpx.AsyncClient) -> None:
    for path in ("/audits/nope", "/audits/nope/report"):
        r = await client.get(path)
        assert r.status_code == 404 and r.json()["code"] == "not-found"


async def test_static_assets_are_served(client: httpx.AsyncClient) -> None:
    r = await client.get("/static/app.js")
    assert r.status_code == 200 and "EventSource" in r.text and "textContent" in r.text
    assert (await client.get("/static/../report.html")).status_code in (404, 400)


async def test_canceled_audit_report_renders_a_banner(
    client: httpx.AsyncClient, service: FakeService
) -> None:
    rec = make_sample_record("canceled", audit_id="aud_cx")
    assert rec.status == AuditStatus.CANCELED
    service.add(rec)
    r = await client.get("/audits/aud_cx/report", params={"lang": "en"})
    assert r.status_code == 200 and "was canceled" in r.text
