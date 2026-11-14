"""Phase-A API surface: screenshot files, section endpoints, the extra form fields."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from seoa.presentation.api import create_app
from seoa.presentation.api.schemas import parse_competitors, parse_keywords
from tests.support.fake_service import FakeService

AUD = "aud_sample0001"
JPEG = b"\xff\xd8\xff\xe0fake-jpeg"


@pytest.fixture
def service() -> FakeService:
    return FakeService()


@pytest.fixture
async def client(service: FakeService) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(service)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as c:
        yield c


async def test_screenshot_is_served_with_image_headers(
    client: httpx.AsyncClient, service: FakeService, tmp_path: Path
) -> None:
    f = tmp_path / "desktop.jpg"
    f.write_bytes(JPEG)
    service.files[(AUD, "desktop.jpg")] = f
    r = await client.get(f"/v1/audits/{AUD}/files/desktop.jpg")
    assert r.status_code == 200 and r.content == JPEG
    assert r.headers["content-type"] == "image/jpeg"
    assert (
        "max-age" in r.headers["cache-control"] and r.headers["x-content-type-options"] == "nosniff"
    )


@pytest.mark.parametrize(
    "name", ["secret.txt", "..%2F..%2Fetc%2Fpasswd", "desktop.png", "desktop.jpg%00", "%2e%2e"]
)
async def test_other_file_names_are_not_served(
    client: httpx.AsyncClient, service: FakeService, tmp_path: Path, name: str
) -> None:
    (tmp_path / "secret.txt").write_text("x")
    service.files[(AUD, "secret.txt")] = tmp_path / "secret.txt"
    r = await client.get(f"/v1/audits/{AUD}/files/{name}")
    assert r.status_code == 404


async def test_missing_file_and_unknown_audit_are_404(client: httpx.AsyncClient) -> None:
    assert (await client.get(f"/v1/audits/{AUD}/files/mobile.jpg")).status_code == 404
    assert (await client.get("/v1/audits/nope/files/mobile.jpg")).status_code == 404


@pytest.mark.parametrize(
    "name",
    [
        "techstack",
        "site-setup",
        "previews",
        "screenshots",
        "readability",
        "hreflang",
        "schema-suggestions",
        "agentic",
    ],
)
async def test_section_endpoints_answer_even_without_data(
    client: httpx.AsyncClient, name: str
) -> None:
    r = await client.get(f"/v1/audits/{AUD}/{name}?lang=en")
    assert r.status_code == 200
    assert r.json()["status"] in ("measured", "not_measured")


async def test_report_json_carries_the_new_sections(client: httpx.AsyncClient) -> None:
    b = (await client.get(f"/v1/audits/{AUD}/report?format=json&lang=en")).json()
    for key in (
        "glance",
        "techstack",
        "site_setup",
        "previews",
        "screenshots",
        "readability",
        "hreflang",
        "schema_suggestions",
        "agentic",
    ):
        assert key in b, key
    assert b["schema_version"] == "1.6.0"


def test_parse_keywords() -> None:
    assert parse_keywords("seo, SEO\nsite hızı ,, ") == ["seo", "site hızı"]
    assert parse_keywords("") == []
    with pytest.raises(ValueError, match="too_many_keywords"):
        parse_keywords(",".join(f"k{i}" for i in range(11)))
    with pytest.raises(ValueError, match="invalid_keywords"):
        parse_keywords("x" * 81)


def test_parse_competitors() -> None:
    assert parse_competitors("a.com\nhttps://b.com/x\na.com") == [
        "https://a.com",
        "https://b.com/x",
    ]
    with pytest.raises(ValueError, match="invalid_competitor"):
        parse_competitors("ftp://x.com")
    with pytest.raises(ValueError, match="too_many_competitors"):
        parse_competitors("a.com b.com c.com d.com")


async def test_form_passes_keywords_competitors_and_lang(
    client: httpx.AsyncClient, service: FakeService
) -> None:
    r = await client.post(
        "/ui/audits",
        content="url=example.com&mode=page&lang=en&keywords=seo%2C+speed&competitors=rival.com%0Aother.com",
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 303 and "lang=en" in r.headers["location"]
    assert service.last_lang == "en"
    assert service.last_keywords == ["seo", "speed"]
    assert service.last_competitors == ["https://rival.com", "https://other.com"]


@pytest.mark.parametrize(
    ("body", "error"),
    [
        ("url=example.com&keywords=" + ",".join(f"k{i}" for i in range(11)), "too_many_keywords"),
        ("url=example.com&competitors=ftp%3A%2F%2Fx.com", "invalid_competitor"),
    ],
)
async def test_form_rejects_bad_optional_fields_in_both_languages(
    client: httpx.AsyncClient, service: FakeService, body: str, error: str
) -> None:
    for lang in ("tr", "en"):
        r = await client.post(
            "/ui/audits",
            content=f"{body}&lang={lang}",
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        assert r.status_code == 422 and 'role="alert"' in r.text
        assert service.last_keywords is None  # nothing was created


async def test_json_api_accepts_keywords_and_competitors(
    client: httpx.AsyncClient, service: FakeService
) -> None:
    r = await client.post(
        "/v1/audits",
        json={"url": "example.com", "keywords": ["seo", "SEO"], "competitors": ["rival.com"]},
    )
    assert r.status_code == 202
    assert service.last_keywords == ["seo"] and service.last_competitors == ["https://rival.com"]
    bad = await client.post("/v1/audits", json={"url": "example.org", "competitors": ["ftp://x"]})
    assert bad.status_code == 422


async def test_form_remembers_keywords_and_competitors_per_site(
    client: httpx.AsyncClient, service: FakeService
) -> None:
    await client.post(
        "/ui/audits",
        content="url=https%3A%2F%2Fwww.example.com%2F&keywords=seo%2C+speed&competitors=rival.com",
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    for typed in ("example.com", "https://example.com/page", "www.example.com"):
        r = await client.get("/ui/profile", params={"url": typed})
        assert r.json() == {"keywords": "seo, speed", "competitors": "https://rival.com"}
    other = await client.get("/ui/profile", params={"url": "other.org"})
    assert other.json() == {"keywords": "", "competitors": ""}
    assert other.headers["cache-control"] == "no-store"


async def test_submitting_the_form_with_empty_fields_clears_the_saved_profile(
    client: httpx.AsyncClient, service: FakeService
) -> None:
    form = {"content-type": "application/x-www-form-urlencoded"}
    await client.post("/ui/audits", content="url=example.com&keywords=seo", headers=form)
    await client.post("/ui/audits", content="url=example.com&keywords=", headers=form)
    r = await client.get("/ui/profile", params={"url": "example.com"})
    assert r.json() == {"keywords": "", "competitors": ""}


async def test_json_api_saves_only_when_it_sends_inputs(
    client: httpx.AsyncClient, service: FakeService
) -> None:
    await client.post("/v1/audits", json={"url": "example.com", "keywords": ["seo"]})
    await client.post("/v1/audits", json={"url": "example.com/other", "mode": "page"})
    r = await client.get("/ui/profile", params={"url": "example.com"})
    assert r.json()["keywords"] == "seo"  # a call without inputs keeps what was saved


async def test_home_page_loads_the_script_and_has_the_profile_note(
    client: httpx.AsyncClient,
) -> None:
    html = (await client.get("/")).text
    assert "/static/app.js" in html and 'id="profile-note"' in html
