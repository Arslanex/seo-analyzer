"""Google connection routes (localhost only; belge 11 s.3.6).

The router is built by ``create_google_router`` and included by ``create_app``. The OAuth
callback redirect URI is derived from the request origin, so it works on whatever loopback
port the app runs on (Desktop-app clients accept any loopback port).
"""

from __future__ import annotations

import html
import logging
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from seoa.infrastructure.integrations.google_oauth import GoogleOAuth, OAuthError
from seoa.infrastructure.integrations.gsc import GscClient, GscError
from seoa.presentation.api.errors import ApiError

log = logging.getLogger("seoa.google")

CALLBACK_PATH = "/oauth/google/callback"
_USER = "local"

_ERRORS_TR = {
    "access_denied": "Erişim izni verilmedi. Bağlanmak için Google'daki izin ekranında "
    "'İzin ver'i seçin (OAuth ekranında kendinizi test kullanıcısı olarak eklemeniz gerekir).",
    "invalid-state": "Bağlantı isteği geçersiz veya süresi dolmuş (10 dakika). Baştan deneyin.",
    "missing-refresh-token": "Google yenileme anahtarı vermedi. Hesabın erişimini "
    "myaccount.google.com/permissions adresinden kaldırıp yeniden bağlanın.",
    "scope-not-granted": "Search Console okuma izni verilmedi. Yeniden bağlanıp izni işaretleyin.",
    "token-exchange-failed": "Google kodu kabul etmedi. Yeniden deneyin; sürerse docs/google-setup.md "
    "içindeki 'redirect_uri_mismatch' bölümüne bakın.",
    "not-configured": "Google OAuth istemcisi tanımlı değil. docs/google-setup.md adımlarını izleyin.",
}


def _origin(request: Request) -> str:
    return f"{request.url.scheme}://{request.headers.get('host') or request.url.netloc}"


def _redirect_uri(request: Request) -> str:
    return _origin(request) + CALLBACK_PATH


def _page(title: str, body: str, status: int = 200) -> HTMLResponse:
    doc = (
        '<!doctype html><html lang="tr"><meta charset="utf-8">'
        f"<title>{html.escape(title)}</title>"
        f'<body style="font-family:system-ui;max-width:40rem;margin:3rem auto;padding:0 1rem">'
        f"<h1>{html.escape(title)}</h1>{body}"
        '<p><a href="/">&larr; Ana sayfa</a></p></body></html>'
    )
    return HTMLResponse(doc, status_code=status)


def _same_origin(request: Request) -> bool:
    """CSRF guard for the state-changing POST: Origin (or Referer) must be this server."""
    src = request.headers.get("origin") or request.headers.get("referer")
    if not src:
        return False
    p = urlparse(src)
    host = request.headers.get("host") or request.url.netloc
    return bool(p.scheme and p.netloc == host)


def create_google_router(
    oauth: GoogleOAuth, client_factory: Callable[[], GscClient] | None = None
) -> APIRouter:
    router = APIRouter()

    def client() -> GscClient:
        return client_factory() if client_factory else GscClient(oauth, _USER)

    @router.get("/connect/google", include_in_schema=False)
    async def connect(request: Request) -> Response:
        if not oauth.is_configured():
            return _page(
                "Google bağlantısı kurulu değil",
                "<p>Önce bir OAuth istemcisi oluşturup JSON dosyasını "
                "<code>data/google_client.json</code> olarak kaydedin. "
                "Adımlar: <code>docs/google-setup.md</code>.</p>",
                status=409,
            )
        url, _state = oauth.authorization_url(_redirect_uri(request), _USER)
        return RedirectResponse(url, status_code=302)

    @router.get(CALLBACK_PATH, include_in_schema=False)
    async def callback(
        request: Request,
        state: str | None = None,
        code: str | None = None,
        error: str | None = None,
    ) -> Response:
        if error:
            key = "access_denied" if error == "access_denied" else "token-exchange-failed"
            return _page("Bağlantı kurulamadı", f"<p>{html.escape(_ERRORS_TR[key])}</p>", 400)
        if not state or not code:
            return _page(
                "Bağlantı kurulamadı", f"<p>{html.escape(_ERRORS_TR['invalid-state'])}</p>", 400
            )
        try:
            await oauth.exchange_code(state, code, _redirect_uri(request))
        except OAuthError as exc:
            msg = _ERRORS_TR.get(exc.code, _ERRORS_TR["token-exchange-failed"])
            return _page("Bağlantı kurulamadı", f"<p>{html.escape(msg)}</p>", 400)
        return RedirectResponse("/?google=connected", status_code=303)

    @router.post("/disconnect/google", include_in_schema=False)
    async def disconnect(request: Request) -> Response:
        if not _same_origin(request):
            raise ApiError("forbidden", 403, "Cross-origin request rejected.")
        await oauth.disconnect(_USER)
        return RedirectResponse("/?google=disconnected", status_code=303)

    @router.get("/v1/google/status")
    async def status() -> dict[str, Any]:
        return oauth.status(_USER)

    @router.get("/v1/google/properties")
    async def properties() -> dict[str, Any]:
        st = oauth.status(_USER)
        if not st["connected"]:
            raise ApiError("google-not-connected", 409, "Google account is not connected.")
        try:
            items = await client().list_properties()
        except GscError as exc:
            if exc.code == "not-connected":
                raise ApiError(
                    "google-not-connected", 409, "Google account is not connected."
                ) from None
            raise ApiError("google-error", 502, f"Search Console call failed: {exc.code}") from None
        return {"properties": items}

    return router
