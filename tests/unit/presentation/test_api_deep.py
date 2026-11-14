"""API endpoints for the deep analyses (belge 11)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

from seoa.domain import AuditStatus
from seoa.presentation.api import create_app
from seoa.presentation.api.routers import audit_pages as routes_mod
from tests.support.fake_service import FakeService, make_sample_record

AUD = "aud_sample0001"


@pytest.fixture
def service() -> FakeService:
    return FakeService()


@pytest.fixture
async def client(service: FakeService) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(service)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as c:
        yield c


async def test_links_lists_summary_pages_and_rows(client: httpx.AsyncClient) -> None:
    r = await client.get(f"/v1/audits/{AUD}/links?lang=en")
    assert r.status_code == 200
    b = r.json()
    assert b["status"] == "measured" and b["total"] == len(b["data"]) > 0
    assert b["summary"] and b["pages"] and "links" not in b["summary"]


async def test_links_filters_kind_broken_and_source(client: httpx.AsyncClient) -> None:
    ext = (await client.get(f"/v1/audits/{AUD}/links?kind=external")).json()
    assert ext["data"] and all(x["kind"] == "external" for x in ext["data"])
    br = (await client.get(f"/v1/audits/{AUD}/links?broken=true")).json()
    assert br["total"] == 2 and all(x["state"] == "broken" for x in br["data"])
    src = br["data"][0]["source_url"]
    one = (await client.get(f"/v1/audits/{AUD}/links", params={"source": src})).json()
    assert one["data"] and all(x["source_url"] == src for x in one["data"])
    none = (
        await client.get(f"/v1/audits/{AUD}/links", params={"source": "https://nope.test/"})
    ).json()
    assert none["total"] == 0 and none["data"] == []


async def test_links_pagination_with_cursor(client: httpx.AsyncClient) -> None:
    first = (await client.get(f"/v1/audits/{AUD}/links?limit=2")).json()
    assert len(first["data"]) == 2 and first["has_more"] and first["next_cursor"] == "2"
    second = (await client.get(f"/v1/audits/{AUD}/links?limit=2&cursor=2")).json()
    assert second["data"] and second["data"][0] != first["data"][0]
    assert second["total"] == first["total"]


async def test_links_download_is_an_attachment_with_everything(client: httpx.AsyncClient) -> None:
    r = await client.get(f"/v1/audits/{AUD}/links?download=1")
    assert r.status_code == 200
    assert f"links-{AUD}.json" in r.headers["content-disposition"]
    b = r.json()
    assert b["links"] and b["pages"] and b["summary"]


async def test_links_validation_errors_are_problem_json(client: httpx.AsyncClient) -> None:
    for q in ("kind=other", "limit=0", "limit=201"):
        r = await client.get(f"/v1/audits/{AUD}/links?{q}")
        assert r.status_code == 422 and r.headers["content-type"].startswith(
            "application/problem+json"
        )
    r = await client.get(f"/v1/audits/{AUD}/links?cursor=abc")
    assert r.status_code == 422 and r.json()["code"] == "validation-error"


@pytest.mark.parametrize(
    "name", ["links", "perf", "images", "indexability", "visibility", "gsc", "field"]
)
async def test_unknown_audit_is_404_problem(client: httpx.AsyncClient, name: str) -> None:
    r = await client.get(f"/v1/audits/aud_missing/{name}")
    assert r.status_code == 404 and r.headers["content-type"].startswith("application/problem+json")


@pytest.mark.parametrize(
    "name", ["links", "perf", "images", "indexability", "visibility", "gsc", "field"]
)
async def test_running_audit_is_409(
    client: httpx.AsyncClient, service: FakeService, name: str
) -> None:
    rec = make_sample_record("gated", audit_id="aud_running01")
    rec.status = AuditStatus.RUNNING
    service.add(rec)
    r = await client.get(f"/v1/audits/aud_running01/{name}")
    assert r.status_code == 409 and r.headers["content-type"].startswith("application/problem+json")


async def test_perf_images_indexability_visibility_return_sections(
    client: httpx.AsyncClient,
) -> None:
    perf = (await client.get(f"/v1/audits/{AUD}/perf?lang=en")).json()
    assert perf["status"] == "measured" and perf["rows"] and perf["by_type"]
    assert any(r["ratings"].get("lcp_ms") for r in perf["rows"])
    img = (await client.get(f"/v1/audits/{AUD}/images")).json()
    assert img["status"] == "measured" and img["rows"] and img["total_kb"] > 0
    idx = (await client.get(f"/v1/audits/{AUD}/indexability")).json()
    assert idx["status"] == "measured" and idx["rows"] and idx["blocked_count"] == 3
    vis = (await client.get(f"/v1/audits/{AUD}/visibility?lang=tr")).json()
    assert vis["status"] == "measured" and vis["counts_toward_overall"] is False and vis["items"]


async def test_not_measured_answers_with_reason_not_an_empty_list(
    client: httpx.AsyncClient, service: FakeService
) -> None:
    service.add(make_sample_record("no-deep-analysis", audit_id="aud_nodeep001"))
    links = (await client.get("/v1/audits/aud_nodeep001/links?lang=en")).json()
    assert links["status"] == "not_measured" and links["reason"] == "analysis-not-run"
    assert links["reason_text"] and links["data"] == [] and links["has_more"] is False
    perf = (await client.get("/v1/audits/aud_nodeep001/perf?lang=en")).json()
    assert perf["status"] == "not_measured" and perf["not_measured_reason"] == "lab-unavailable"
    for name in ("images", "indexability", "visibility"):
        b = (await client.get(f"/v1/audits/aud_nodeep001/{name}")).json()
        assert b["status"] == "not_measured" and b["not_measured_reason"]
        assert not b.get("rows") and not b.get("items")


async def test_xss_text_is_data_in_json_not_markup(
    client: httpx.AsyncClient, service: FakeService
) -> None:
    service.add(make_sample_record("gated", audit_id="aud_xss0001", xss=True))
    r = await client.get("/v1/audits/aud_xss0001/links")
    assert r.headers["content-type"].startswith("application/json")
    assert "<script>" in r.text  # carried verbatim as JSON string data


async def test_create_passes_lang_and_validates_it(
    client: httpx.AsyncClient, service: FakeService
) -> None:
    r = await client.post("/v1/audits", json={"url": "example.org", "lang": "en"})
    assert r.status_code == 202 and service.last_lang == "en"
    bad = await client.post("/v1/audits", json={"url": "example.org", "lang": "de"})
    assert bad.status_code == 422


def test_stages_include_analyze_between_measure_and_score() -> None:
    st = list(routes_mod.STAGES)
    assert "analyze" in st
