"""Shared fakes for the Google / Search Console tests (offline)."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from seoa.config import Settings
from seoa.infrastructure.integrations.google_oauth import GoogleOAuth, HttpResult, MemoryTokenStore

SECRET = "client-secret-XYZ-123"
REFRESH = "refresh-token-ABC-456"
ACCESS = "access-token-DEF-789"


class FakeHttp:
    """Records requests; ``handler(method, url, kw) -> HttpResult`` answers them."""

    def __init__(self, handler: Callable[[str, str, dict[str, Any]], HttpResult]) -> None:
        self.handler = handler
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    async def request(self, method: str, url: str, **kw: Any) -> HttpResult:
        self.calls.append((method, url, kw))
        return self.handler(method, url, kw)


def make_settings(tmp: Path, *, with_client: bool = True) -> Settings:
    cf = tmp / "google_client.json"
    if with_client:
        cf.write_text(
            json.dumps({"installed": {"client_id": "cid.apps.example", "client_secret": SECRET}})
        )
    return Settings(data_dir=tmp, google_client_file=cf)


def make_oauth(
    tmp: Path,
    http: FakeHttp | None = None,
    *,
    with_client: bool = True,
    connected: bool = False,
    now: Callable[[], float] | None = None,
) -> GoogleOAuth:
    store = MemoryTokenStore()
    if connected:
        store.set(
            "local",
            {
                "refresh_token": REFRESH,
                "access_token": ACCESS,
                "expires_at": 9e12,
                "email": "me@example.com",
            },
        )
    kw: dict[str, Any] = {"now": now} if now else {}
    return GoogleOAuth(
        make_settings(tmp, with_client=with_client),
        store,
        http or FakeHttp(lambda *_: HttpResult(500)),
        **kw,
    )
