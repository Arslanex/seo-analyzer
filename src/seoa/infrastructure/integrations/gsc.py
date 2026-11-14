"""Search Console API client and property resolution (belge 11 s.3.6).

``resolve_property`` is pure and **fail-closed**: it either finds a property the user owns for
exactly this site, or returns ``property=None`` with a reason. It never falls back to "the first
property" or any other site, so one customer's data can never be shown for another's domain.

Quotas worth knowing: Search Analytics data lags 2-3 days; the URL Inspection API allows
2000 queries/day/property (600/min), so callers must keep their use small.
"""

from __future__ import annotations

import datetime as dt
from typing import Any
from urllib.parse import quote

from seoa.application.analysis.search_console.property import Resolution, resolve_property
from seoa.application.ports import GscError
from seoa.infrastructure.integrations.google_oauth import GoogleOAuth, Http, HttpResult, OAuthError

SITES_URL = "https://www.googleapis.com/webmasters/v3/sites"
INSPECT_URL = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"
DATA_LAG_DAYS = 3


def _quote(prop: str) -> str:
    return quote(prop, safe="")


class GscClient:
    def __init__(
        self, oauth: GoogleOAuth, user_id: str = "local", http: Http | None = None
    ) -> None:
        self.oauth = oauth
        self.user_id = user_id
        self.http: Http = http or oauth.http

    async def _call(
        self, method: str, url: str, *, json_body: Any = None, timeout_s: float = 30.0
    ) -> Any:
        refreshed = False
        while True:
            try:
                token = await self.oauth.access_token(self.user_id, force_refresh=refreshed)
            except OAuthError as exc:
                raise GscError(exc.code) from None
            if token is None:
                raise GscError("not-connected")
            res: HttpResult = await self.http.request(
                method,
                url,
                headers={"Authorization": f"Bearer {token}"},
                json_body=json_body,
                timeout_s=timeout_s,
            )
            if res.status == 401 and not refreshed:
                refreshed = True  # the access token was rejected: refresh once and retry
                continue
            if res.status is None:
                raise GscError(res.error or "unreachable")
            if res.status == 200:
                return res.json if res.json is not None else {}
            raise GscError(
                {
                    401: "not-connected",
                    403: "no-permission",
                    404: "property-not-found",
                    429: "rate-limited",
                }.get(res.status, f"http-{res.status}")
            )

    async def list_properties(self) -> list[dict[str, str]]:
        body = await self._call("GET", SITES_URL)
        out: list[dict[str, str]] = []
        for e in body.get("siteEntry", []) if isinstance(body, dict) else []:
            if isinstance(e, dict) and e.get("siteUrl"):
                out.append(
                    {"site_url": str(e["siteUrl"]), "permission": str(e.get("permissionLevel", ""))}
                )
        return out

    async def search_analytics(
        self,
        property: str,
        *,
        days: int = 28,
        dimensions: list[str] | None = None,
        row_limit: int = 25,
        query: str | None = None,
        query_operator: str = "contains",
    ) -> list[dict[str, Any]]:
        end = dt.date.today() - dt.timedelta(days=DATA_LAG_DAYS)
        start = end - dt.timedelta(days=days - 1)
        payload: dict[str, Any] = {
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "rowLimit": row_limit,
        }
        if dimensions:
            payload["dimensions"] = dimensions
        if query is not None:  # case-insensitive on Google's side
            payload["dimensionFilterGroups"] = [
                {
                    "groupType": "and",
                    "filters": [
                        {"dimension": "query", "operator": query_operator, "expression": query}
                    ],
                }
            ]
        body = await self._call(
            "POST", f"{SITES_URL}/{_quote(property)}/searchAnalytics/query", json_body=payload
        )
        rows = body.get("rows", []) if isinstance(body, dict) else []
        return [r for r in rows if isinstance(r, dict)]

    async def inspect_url(self, property: str, url: str) -> dict[str, Any]:
        body = await self._call(
            "POST", INSPECT_URL, json_body={"inspectionUrl": url, "siteUrl": property}
        )
        result = body.get("inspectionResult", {}) if isinstance(body, dict) else {}
        return result if isinstance(result, dict) else {}

    async def list_sitemaps(self, property: str) -> list[dict[str, Any]]:
        body = await self._call("GET", f"{SITES_URL}/{_quote(property)}/sitemaps")
        items = body.get("sitemap", []) if isinstance(body, dict) else []
        return [s for s in items if isinstance(s, dict)]


__all__ = ["DATA_LAG_DAYS", "GscClient", "GscError", "Resolution", "resolve_property"]
