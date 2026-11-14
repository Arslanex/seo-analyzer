"""Google OAuth 2.0 for Search Console (installed-app / loopback flow with PKCE).

Design (belge 11 s.3.6, "Search Console baglantisi"):

* one OAuth client for the whole installation (a Google Cloud "Desktop app" client), but the
  tokens are stored **per user id** (``user_id``; the MVP always uses ``"local"``), so the same
  code serves a multi-user product later: each customer authorises their own Google account;
  we never see a password and only ask for the read-only Search Console scope;
* PKCE (S256) and a one-time ``state`` guard the authorisation response;
* nothing secret is ever logged or placed in an error message: errors carry a short stable
  ``code`` only, and every Google response body is reduced to its ``error`` code.

``FileTokenStore`` keeps refresh tokens in a 0600 file. That is acceptable for a single-user
machine; **a product needs encrypted storage** (a KMS-wrapped column, per-tenant keys) and a
revocation path from the user's account page.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import re
import secrets
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlencode

import aiohttp

from seoa.config import Settings, get_settings
from seoa.domain.url_safety import URLSafetyError, check_url
from seoa.infrastructure.http.resolver import BlockedAddressError, SafeResolver

log = logging.getLogger("seoa.google")

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
SCOPE_GSC_READ = "https://www.googleapis.com/auth/webmasters.readonly"
SCOPES = (SCOPE_GSC_READ, "openid", "email")
STATE_TTL_S = 600.0
_EXPIRY_SKEW_S = 60.0
_MAX_BODY = 1024 * 1024
_SAFE_CODE = re.compile(r"[^a-z0-9_\-]")


class OAuthError(Exception):
    """An OAuth failure. ``code`` is a short stable identifier; the message never has secrets."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


# --------------------------------------------------------------------------- HTTP seam


@dataclass
class HttpResult:
    status: int | None  # None when the request itself failed
    json: Any = None
    error: str | None = None  # timeout | unreachable | target-rejected | too-large | bad-json


class Http(Protocol):
    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json_body: Any = None,
        form: dict[str, str] | None = None,
        timeout_s: float = 30.0,
    ) -> HttpResult: ...


class AiohttpHttp:
    """The production transport: https only, ``SafeResolver``, no redirects, bounded body.

    Response text is never kept (token responses are parsed to JSON and dropped).
    """

    def __init__(self) -> None:
        self._session: aiohttp.ClientSession | None = None

    def _get(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            s = get_settings()
            self._session = aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(
                    resolver=SafeResolver(), use_dns_cache=False, limit=10
                ),
                headers={"User-Agent": f"{s.bot_name} (+{s.bot_info_url})"},
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json_body: Any = None,
        form: dict[str, str] | None = None,
        timeout_s: float = 30.0,
    ) -> HttpResult:
        try:
            if check_url(url).scheme != "https":
                return HttpResult(None, error="target-rejected")
        except URLSafetyError:
            return HttpResult(None, error="target-rejected")
        try:
            async with asyncio.timeout(timeout_s):
                async with self._get().request(
                    method,
                    url,
                    headers=headers,
                    json=json_body,
                    data=form,
                    allow_redirects=False,
                ) as resp:
                    buf = bytearray()
                    async for chunk in resp.content.iter_chunked(65536):
                        buf.extend(chunk)
                        if len(buf) > _MAX_BODY:
                            return HttpResult(resp.status, error="too-large")
                    if not buf:
                        return HttpResult(resp.status)
                    try:
                        return HttpResult(resp.status, json=json.loads(bytes(buf)))
                    except ValueError:
                        return HttpResult(resp.status, error="bad-json")
        except BlockedAddressError:
            return HttpResult(None, error="target-rejected")
        except TimeoutError:
            return HttpResult(None, error="timeout")
        except aiohttp.ClientConnectorError as exc:
            blocked = isinstance(exc.os_error, BlockedAddressError)
            return HttpResult(None, error="target-rejected" if blocked else "unreachable")
        except aiohttp.ClientError:
            return HttpResult(None, error="unreachable")


def google_error_code(res: HttpResult) -> str:
    """Reduce a Google error body to its short ``error`` code (never the description)."""
    body = res.json
    code = body.get("error") if isinstance(body, dict) else None
    if isinstance(code, dict):  # APIs v1 style: {"error": {"status": "PERMISSION_DENIED"}}
        code = code.get("status")
    if isinstance(code, str) and code:
        return _SAFE_CODE.sub("", code.lower())[:40] or "error"
    return res.error or f"http-{res.status}"


# --------------------------------------------------------------------------- token store


class TokenStore(Protocol):
    def get(self, user_id: str) -> dict[str, Any] | None: ...
    def set(self, user_id: str, record: dict[str, Any]) -> None: ...
    def delete(self, user_id: str) -> None: ...


class MemoryTokenStore:
    def __init__(self) -> None:
        self._d: dict[str, dict[str, Any]] = {}

    def get(self, user_id: str) -> dict[str, Any] | None:
        r = self._d.get(user_id)
        return dict(r) if r else None

    def set(self, user_id: str, record: dict[str, Any]) -> None:
        self._d[user_id] = dict(record)

    def delete(self, user_id: str) -> None:
        self._d.pop(user_id, None)


class FileTokenStore:
    """JSON file keyed by user id, mode 0600, written atomically (see the module docstring)."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def _read(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text())
        except (FileNotFoundError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".google-tokens-")
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w") as fh:
                json.dump(data, fh)
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def get(self, user_id: str) -> dict[str, Any] | None:
        r = self._read().get(user_id)
        return dict(r) if isinstance(r, dict) else None

    def set(self, user_id: str, record: dict[str, Any]) -> None:
        data = self._read()
        data[user_id] = record
        self._write(data)

    def delete(self, user_id: str) -> None:
        data = self._read()
        if data.pop(user_id, None) is not None:
            self._write(data)


# --------------------------------------------------------------------------- client credentials


@dataclass(frozen=True)
class ClientCredentials:
    client_id: str
    client_secret: str = field(repr=False)


def load_client_credentials(settings: Settings) -> ClientCredentials | None:
    """Env (GOOGLE_OAUTH_CLIENT_ID/SECRET) first, then the Cloud Console JSON file."""
    cid = os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
    sec = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")
    if cid and sec:
        return ClientCredentials(cid, sec)
    try:
        raw = json.loads(settings.google_client_path.read_text())
    except (OSError, ValueError):
        return None
    block = raw.get("installed") or raw.get("web") if isinstance(raw, dict) else None
    if isinstance(block, dict) and block.get("client_id") and block.get("client_secret"):
        return ClientCredentials(str(block["client_id"]), str(block["client_secret"]))
    return None


# --------------------------------------------------------------------------- OAuth


@dataclass
class _Pending:
    verifier: str
    user_id: str
    redirect_uri: str
    created: float


class GoogleOAuth:
    def __init__(
        self,
        settings: Settings | None = None,
        store: TokenStore | None = None,
        http: Http | None = None,
        *,
        now: Callable[[], float] = time.time,
    ) -> None:
        self.settings = settings or get_settings()
        self.store: TokenStore = store or FileTokenStore(
            self.settings.data_dir / "google_tokens.json"
        )
        self.http: Http = http or AiohttpHttp()
        self._now = now
        self._pending: dict[str, _Pending] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    # -- configuration / status --------------------------------------------------

    def _credentials(self) -> ClientCredentials | None:
        return load_client_credentials(self.settings)

    def is_configured(self) -> bool:
        return self._credentials() is not None

    def status(self, user_id: str = "local") -> dict[str, Any]:
        rec = self.store.get(user_id)
        connected = bool(rec and rec.get("refresh_token"))
        return {
            "configured": self.is_configured(),
            "connected": connected,
            "email": rec.get("email") if connected and rec else None,
        }

    # -- authorisation --------------------------------------------------------------

    def _purge(self) -> None:
        cutoff = self._now() - STATE_TTL_S
        for k in [k for k, p in self._pending.items() if p.created < cutoff]:
            del self._pending[k]

    def authorization_url(self, redirect_uri: str, user_id: str = "local") -> tuple[str, str]:
        creds = self._credentials()
        if creds is None:
            raise OAuthError("not-configured")
        self._purge()
        verifier = secrets.token_urlsafe(64)
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        state = secrets.token_urlsafe(32)
        self._pending[state] = _Pending(verifier, user_id, redirect_uri, self._now())
        query = urlencode(
            {
                "client_id": creds.client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": " ".join(SCOPES),
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "access_type": "offline",
                "prompt": "consent",  # always returns a refresh token
            }
        )
        return f"{AUTH_URL}?{query}", state

    async def exchange_code(self, state: str, code: str, redirect_uri: str) -> dict[str, Any]:
        """Trade the authorisation code for tokens. The state is single-use."""
        creds = self._credentials()
        if creds is None:
            raise OAuthError("not-configured")
        self._purge()
        pending = self._pending.pop(state, None)  # one-time: a replayed state is rejected
        if pending is None or pending.redirect_uri != redirect_uri:
            raise OAuthError("invalid-state")
        res = await self.http.request(
            "POST",
            TOKEN_URL,
            form={
                "code": code,
                "client_id": creds.client_id,
                "client_secret": creds.client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
                "code_verifier": pending.verifier,
            },
        )
        body = res.json if isinstance(res.json, dict) else {}
        if res.status != 200 or not body.get("access_token"):
            log.warning("token exchange failed: %s", google_error_code(res))
            raise OAuthError("token-exchange-failed")
        if not body.get("refresh_token"):
            raise OAuthError("missing-refresh-token")
        if SCOPE_GSC_READ not in str(body.get("scope", "")).split():
            raise OAuthError("scope-not-granted")
        expires = self._now() + float(body.get("expires_in") or 3600)
        email = await self._email(str(body["access_token"]))
        self.store.set(
            pending.user_id,
            {
                "refresh_token": body["refresh_token"],
                "access_token": body["access_token"],
                "expires_at": expires,
                "email": email,
                "scope": body.get("scope"),
            },
        )
        log.info("google account connected for user %s", pending.user_id)
        return {"email": email, "user_id": pending.user_id}

    async def _email(self, access_token: str) -> str | None:
        res = await self.http.request(
            "GET", USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}
        )
        body = res.json if isinstance(res.json, dict) else {}
        email = body.get("email") if res.status == 200 else None
        return str(email) if email else None

    # -- tokens ---------------------------------------------------------------------

    async def access_token(
        self, user_id: str = "local", *, force_refresh: bool = False
    ) -> str | None:
        """A valid access token, refreshed when needed.

        ``None`` means "not connected" (never connected, or Google revoked the grant).
        A transient failure raises ``OAuthError("refresh-failed")`` instead, so a network
        blip is not mistaken for a revoked connection.
        """
        rec = self.store.get(user_id)
        if not rec or not rec.get("refresh_token"):
            return None
        fresh = (
            not force_refresh
            and rec.get("access_token")
            and float(rec.get("expires_at", 0)) - _EXPIRY_SKEW_S > self._now()
        )
        if fresh:
            return str(rec["access_token"])
        creds = self._credentials()
        if creds is None:
            raise OAuthError("not-configured")
        lock = self._locks.setdefault(user_id, asyncio.Lock())
        async with lock:
            rec = self.store.get(user_id)  # another task may have refreshed meanwhile
            if not rec or not rec.get("refresh_token"):
                return None
            if (
                not force_refresh
                and rec.get("access_token")
                and float(rec.get("expires_at", 0)) - _EXPIRY_SKEW_S > self._now()
            ):
                return str(rec["access_token"])
            res = await self.http.request(
                "POST",
                TOKEN_URL,
                form={
                    "client_id": creds.client_id,
                    "client_secret": creds.client_secret,
                    "refresh_token": str(rec["refresh_token"]),
                    "grant_type": "refresh_token",
                },
            )
            body = res.json if isinstance(res.json, dict) else {}
            if res.status == 400 and google_error_code(res) == "invalid_grant":
                self.store.delete(user_id)  # revoked or expired: the user must reconnect
                log.warning("google grant revoked for user %s", user_id)
                return None
            if res.status != 200 or not body.get("access_token"):
                log.warning("token refresh failed: %s", google_error_code(res))
                raise OAuthError("refresh-failed")
            rec["access_token"] = body["access_token"]
            rec["expires_at"] = self._now() + float(body.get("expires_in") or 3600)
            if body.get("refresh_token"):  # Google may rotate it
                rec["refresh_token"] = body["refresh_token"]
            self.store.set(user_id, rec)
            return str(rec["access_token"])

    async def disconnect(self, user_id: str = "local") -> None:
        rec = self.store.get(user_id)
        if rec and rec.get("refresh_token"):
            try:  # best effort: the local deletion below must happen either way
                await self.http.request(
                    "POST", REVOKE_URL, form={"token": str(rec["refresh_token"])}
                )
            except Exception:  # noqa: BLE001
                log.warning("google token revocation failed")
        self.store.delete(user_id)
