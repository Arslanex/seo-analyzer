from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi import FastAPI

from seoa.infrastructure.integrations.google_oauth import (
    REVOKE_URL,
    SCOPE_GSC_READ,
    TOKEN_URL,
    USERINFO_URL,
    HttpResult,
)
from seoa.presentation.api.errors import install_handlers
from seoa.presentation.api.google_routes import create_google_router
from tests.support.google_support import ACCESS, REFRESH, SECRET, FakeHttp, make_oauth

BASE = "http://127.0.0.1:8000"


@pytest.fixture(autouse=True)
def _no_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_SECRET", raising=False)


def _app(oauth: Any) -> FastAPI:
    app = FastAPI()
    install_handlers(app)
    app.include_router(create_google_router(oauth))
    return app


def _c(oauth: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=_app(oauth)), base_url=BASE)


async def test_connect_not_configured_shows_setup(tmp_path: Path) -> None:
    async with _c(make_oauth(tmp_path, with_client=False)) as c:
        r = await c.get("/connect/google")
    assert r.status_code == 409 and "google-setup.md" in r.text and "google_client.json" in r.text


async def test_connect_redirects_to_google(tmp_path: Path) -> None:
    async with _c(make_oauth(tmp_path)) as c:
        r = await c.get("/connect/google")
    assert r.status_code == 302
    loc = urlparse(r.headers["location"])
    q = parse_qs(loc.query)
    assert loc.netloc == "accounts.google.com"
    assert q["redirect_uri"] == [f"{BASE}/oauth/google/callback"]
    assert q["scope"] == [f"{SCOPE_GSC_READ} openid email"]
    assert SECRET not in r.headers["location"]


async def test_callback_error_param_friendly(tmp_path: Path) -> None:
    async with _c(make_oauth(tmp_path)) as c:
        r = await c.get("/oauth/google/callback", params={"error": "access_denied"})
    assert r.status_code == 400 and "test kullanıcısı" in r.text


async def test_callback_bad_state(tmp_path: Path) -> None:
    async with _c(make_oauth(tmp_path)) as c:
        r = await c.get("/oauth/google/callback", params={"state": "x", "code": "y"})
        r2 = await c.get("/oauth/google/callback")
    assert r.status_code == 400 and "süresi dolmuş" in r.text
    assert r2.status_code == 400


async def test_callback_success_roundtrip(tmp_path: Path) -> None:
    def h(m: str, u: str, kw: dict[str, Any]) -> HttpResult:
        if u == TOKEN_URL:
            assert kw["form"]["redirect_uri"] == f"{BASE}/oauth/google/callback"
            return HttpResult(
                200,
                {
                    "access_token": ACCESS,
                    "refresh_token": REFRESH,
                    "scope": SCOPE_GSC_READ,
                    "expires_in": 3600,
                },
            )
        assert u == USERINFO_URL
        return HttpResult(200, {"email": "me@example.com"})

    o = make_oauth(tmp_path, FakeHttp(h))
    async with _c(o) as c:
        loc = (await c.get("/connect/google")).headers["location"]
        state = parse_qs(urlparse(loc).query)["state"][0]
        r = await c.get("/oauth/google/callback", params={"state": state, "code": "abc"})
        assert r.status_code == 303 and r.headers["location"] == "/?google=connected"
        st = (await c.get("/v1/google/status")).json()
    assert st == {"configured": True, "connected": True, "email": "me@example.com"}


async def test_disconnect_csrf(tmp_path: Path) -> None:
    http = FakeHttp(lambda *_: HttpResult(200, {}))
    o = make_oauth(tmp_path, http, connected=True)
    async with _c(o) as c:
        for headers in (
            {},
            {"Origin": "http://evil.example"},
            {"Referer": "http://evil.example/x"},
        ):
            r = await c.post("/disconnect/google", headers=headers)
            assert r.status_code == 403
        assert o.status()["connected"] is True and http.calls == []
        r = await c.post("/disconnect/google", headers={"Origin": BASE})
    assert r.status_code == 303 and r.headers["location"] == "/?google=disconnected"
    assert o.status()["connected"] is False and http.calls[0][1] == REVOKE_URL


async def test_status_and_properties(tmp_path: Path) -> None:
    async with _c(make_oauth(tmp_path)) as c:
        assert (await c.get("/v1/google/status")).json()["connected"] is False
        r = await c.get("/v1/google/properties")
    assert r.status_code == 409 and r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["code"] == "google-not-connected"

    http = FakeHttp(
        lambda *_: HttpResult(
            200, {"siteEntry": [{"siteUrl": "sc-domain:a.com", "permissionLevel": "siteOwner"}]}
        )
    )
    async with _c(make_oauth(tmp_path, http, connected=True)) as c:
        r = await c.get("/v1/google/properties")
    assert r.json() == {"properties": [{"site_url": "sc-domain:a.com", "permission": "siteOwner"}]}


async def test_properties_upstream_error_is_502(tmp_path: Path) -> None:
    http = FakeHttp(lambda *_: HttpResult(500, {"error": "x"}))
    async with _c(make_oauth(tmp_path, http, connected=True)) as c:
        r = await c.get("/v1/google/properties")
    assert r.status_code == 502


async def test_no_secret_leaks_in_responses_or_logs(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    http = FakeHttp(
        lambda *_: HttpResult(400, {"error": "invalid_grant", "error_description": REFRESH})
    )
    o = make_oauth(tmp_path, http, connected=True)
    texts = []
    async with _c(o) as c:
        for path in ("/v1/google/status", "/v1/google/properties", "/connect/google"):
            r = await c.get(path)
            texts.append(r.text + str(r.headers))
        r = await c.get("/oauth/google/callback", params={"state": "s", "code": "c"})
        texts.append(r.text)
    blob = "\n".join(texts) + caplog.text
    for s in (SECRET, REFRESH, ACCESS):
        assert s not in blob
