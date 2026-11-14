from __future__ import annotations

import base64
import hashlib
import json
import logging
import stat
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest

from seoa.infrastructure.integrations.google_oauth import (
    REVOKE_URL,
    SCOPE_GSC_READ,
    STATE_TTL_S,
    TOKEN_URL,
    USERINFO_URL,
    FileTokenStore,
    GoogleOAuth,
    HttpResult,
    OAuthError,
)
from tests.support.google_support import (
    ACCESS,
    REFRESH,
    SECRET,
    FakeHttp,
    make_oauth,
    make_settings,
)

REDIRECT = "http://127.0.0.1:8000/oauth/google/callback"


@pytest.fixture(autouse=True)
def _no_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_SECRET", raising=False)


def _grant(method: str, url: str, kw: dict[str, Any]) -> HttpResult:
    if url == TOKEN_URL:
        return HttpResult(
            200,
            {
                "access_token": ACCESS,
                "refresh_token": REFRESH,
                "expires_in": 3600,
                "scope": f"openid email {SCOPE_GSC_READ}",
            },
        )
    if url == USERINFO_URL:
        return HttpResult(200, {"email": "me@example.com"})
    return HttpResult(200, {})


def test_not_configured(tmp_path: Path) -> None:
    o = make_oauth(tmp_path, with_client=False)
    assert not o.is_configured()
    assert o.status() == {"configured": False, "connected": False, "email": None}
    with pytest.raises(OAuthError) as e:
        o.authorization_url(REDIRECT)
    assert e.value.code == "not-configured"


def test_env_credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "envid")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "envsecret")
    assert make_oauth(tmp_path, with_client=False).is_configured()


def test_authorization_url_pkce_and_scopes(tmp_path: Path) -> None:
    o = make_oauth(tmp_path)
    url, state = o.authorization_url(REDIRECT)
    q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
    assert q["state"] == state and q["redirect_uri"] == REDIRECT
    assert q["code_challenge_method"] == "S256"
    assert q["access_type"] == "offline" and q["prompt"] == "consent"
    assert set(q["scope"].split()) == {SCOPE_GSC_READ, "openid", "email"}
    verifier = o._pending[state].verifier
    expect = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    assert q["code_challenge"] == expect.decode()
    assert SECRET not in url
    assert o.authorization_url(REDIRECT)[1] != state


async def test_exchange_ok_stores_token_and_email(tmp_path: Path) -> None:
    http = FakeHttp(_grant)
    o = make_oauth(tmp_path, http)
    _url, state = o.authorization_url(REDIRECT)
    verifier = o._pending[state].verifier
    res = await o.exchange_code(state, "the-code", REDIRECT)
    assert res["email"] == "me@example.com"
    token_call = next(c for c in http.calls if c[1] == TOKEN_URL)
    assert token_call[2]["form"]["code_verifier"] == verifier
    userinfo = next(c for c in http.calls if c[1] == USERINFO_URL)
    assert userinfo[2]["headers"]["Authorization"] == f"Bearer {ACCESS}"
    assert o.status() == {"configured": True, "connected": True, "email": "me@example.com"}
    assert await o.access_token() == ACCESS


async def test_wrong_state_rejected(tmp_path: Path) -> None:
    http = FakeHttp(_grant)
    o = make_oauth(tmp_path, http)
    o.authorization_url(REDIRECT)
    with pytest.raises(OAuthError) as e:
        await o.exchange_code("forged", "c", REDIRECT)
    assert e.value.code == "invalid-state"
    assert http.calls == []


async def test_state_is_single_use(tmp_path: Path) -> None:
    o = make_oauth(tmp_path, FakeHttp(_grant))
    _u, state = o.authorization_url(REDIRECT)
    await o.exchange_code(state, "c", REDIRECT)
    with pytest.raises(OAuthError):
        await o.exchange_code(state, "c", REDIRECT)


async def test_expired_state_rejected(tmp_path: Path) -> None:
    t = [1000.0]
    o = make_oauth(tmp_path, FakeHttp(_grant), now=lambda: t[0])
    _u, state = o.authorization_url(REDIRECT)
    t[0] += STATE_TTL_S + 1
    with pytest.raises(OAuthError) as e:
        await o.exchange_code(state, "c", REDIRECT)
    assert e.value.code == "invalid-state"


async def test_redirect_uri_must_match(tmp_path: Path) -> None:
    o = make_oauth(tmp_path, FakeHttp(_grant))
    _u, state = o.authorization_url(REDIRECT)
    with pytest.raises(OAuthError):
        await o.exchange_code(state, "c", "http://evil.example/cb")


async def test_exchange_failures(tmp_path: Path) -> None:
    def bad(m: str, u: str, kw: dict[str, Any]) -> HttpResult:
        return HttpResult(400, {"error": "invalid_grant", "error_description": SECRET})

    o = make_oauth(tmp_path, FakeHttp(bad))
    _u, s = o.authorization_url(REDIRECT)
    with pytest.raises(OAuthError) as e:
        await o.exchange_code(s, "c", REDIRECT)
    assert e.value.code == "token-exchange-failed" and SECRET not in str(e.value)

    def no_refresh(m: str, u: str, kw: dict[str, Any]) -> HttpResult:
        return HttpResult(200, {"access_token": "a", "scope": SCOPE_GSC_READ})

    o = make_oauth(tmp_path, FakeHttp(no_refresh))
    _u, s = o.authorization_url(REDIRECT)
    with pytest.raises(OAuthError) as e:
        await o.exchange_code(s, "c", REDIRECT)
    assert e.value.code == "missing-refresh-token"

    def wrong_scope(m: str, u: str, kw: dict[str, Any]) -> HttpResult:
        return HttpResult(200, {"access_token": "a", "refresh_token": "r", "scope": "openid"})

    o = make_oauth(tmp_path, FakeHttp(wrong_scope))
    _u, s = o.authorization_url(REDIRECT)
    with pytest.raises(OAuthError) as e:
        await o.exchange_code(s, "c", REDIRECT)
    assert e.value.code == "scope-not-granted"
    assert not o.status()["connected"]


async def test_refresh_when_expired(tmp_path: Path) -> None:
    t = [1000.0]

    def h(m: str, u: str, kw: dict[str, Any]) -> HttpResult:
        assert u == TOKEN_URL and kw["form"]["grant_type"] == "refresh_token"
        return HttpResult(200, {"access_token": "new-access", "expires_in": 3600})

    http = FakeHttp(h)
    o = make_oauth(tmp_path, http, connected=True, now=lambda: t[0])
    assert await o.access_token() == ACCESS  # fresh: no HTTP
    assert http.calls == []
    t[0] = 9e12 + 1
    assert await o.access_token() == "new-access"
    assert len(http.calls) == 1
    assert await o.access_token() == "new-access"  # cached again
    assert len(http.calls) == 1
    assert o.store.get("local")["refresh_token"] == REFRESH  # type: ignore[index]


async def test_invalid_grant_deletes_token(tmp_path: Path) -> None:
    http = FakeHttp(lambda *_: HttpResult(400, {"error": "invalid_grant"}))
    o = make_oauth(tmp_path, http, connected=True)
    assert await o.access_token(force_refresh=True) is None
    assert o.store.get("local") is None
    assert o.status()["connected"] is False


async def test_transient_refresh_failure_keeps_token(tmp_path: Path) -> None:
    http = FakeHttp(lambda *_: HttpResult(None, error="timeout"))
    o = make_oauth(tmp_path, http, connected=True)
    with pytest.raises(OAuthError) as e:
        await o.access_token(force_refresh=True)
    assert e.value.code == "refresh-failed"
    assert o.store.get("local") is not None


async def test_not_connected_returns_none(tmp_path: Path) -> None:
    assert await make_oauth(tmp_path).access_token() is None


async def test_per_user_isolation(tmp_path: Path) -> None:
    o = make_oauth(tmp_path, connected=True)
    assert await o.access_token("someone-else") is None
    assert o.status("someone-else")["connected"] is False


async def test_disconnect_revokes_and_deletes(tmp_path: Path) -> None:
    http = FakeHttp(lambda *_: HttpResult(200, {}))
    o = make_oauth(tmp_path, http, connected=True)
    await o.disconnect()
    assert http.calls[0][1] == REVOKE_URL and http.calls[0][2]["form"] == {"token": REFRESH}
    assert o.store.get("local") is None


async def test_disconnect_deletes_even_if_revoke_fails(tmp_path: Path) -> None:
    def boom(*_: Any) -> HttpResult:
        raise RuntimeError("network")

    o = make_oauth(tmp_path, FakeHttp(boom), connected=True)
    await o.disconnect()
    assert o.store.get("local") is None


def test_file_token_store(tmp_path: Path) -> None:
    p = tmp_path / "sub" / "tokens.json"
    s = FileTokenStore(p)
    assert s.get("local") is None
    s.set("local", {"refresh_token": "r"})
    s.set("u2", {"refresh_token": "r2"})
    assert stat.S_IMODE(p.stat().st_mode) == 0o600
    assert FileTokenStore(p).get("u2") == {"refresh_token": "r2"}
    s.delete("local")
    assert s.get("local") is None and s.get("u2") is not None
    assert not [f for f in p.parent.iterdir() if f.name != "tokens.json"]  # no temp leftovers
    p.write_text("not json")
    assert s.get("u2") is None


async def test_no_secrets_in_logs(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)

    def h(m: str, u: str, kw: dict[str, Any]) -> HttpResult:
        if u == TOKEN_URL and kw["form"]["grant_type"] == "refresh_token":
            return HttpResult(400, {"error": "invalid_grant", "error_description": REFRESH})
        return _grant(m, u, kw)

    o = make_oauth(tmp_path, FakeHttp(h))
    _u, s = o.authorization_url(REDIRECT)
    await o.exchange_code(s, "auth-code-999", REDIRECT)
    await o.access_token(force_refresh=True)
    text = caplog.text + json.dumps(o.status())
    for secret in (SECRET, REFRESH, ACCESS, "auth-code-999"):
        assert secret not in text


def test_credentials_repr_hides_secret(tmp_path: Path) -> None:
    o = GoogleOAuth(make_settings(tmp_path))
    creds = o._credentials()
    assert creds is not None and SECRET not in repr(creds)
