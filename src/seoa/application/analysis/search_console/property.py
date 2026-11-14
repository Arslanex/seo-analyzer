"""Which Search Console property covers a site (belge 11 s.3.6).

``resolve_property`` is pure and **fail-closed**: it either finds a property the user owns for
exactly this site, or returns ``property=None`` with a reason. It never falls back to "the first
property" or any other site, so one customer's data can never be shown for another's domain.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

_NO_ACCESS = {"siteUnverifiedUser"}


@dataclass(frozen=True)
class Resolution:
    property: str | None
    reason: str | None = None  # property-not-found | no-permission (when property is None)
    permission: str | None = None


def _host(domain_or_url: str) -> str:
    raw = domain_or_url.strip()
    p = urlparse(raw if "://" in raw else f"//{raw}")
    return (p.hostname or "").lower().rstrip(".")


def _bare(host: str) -> str:
    return host[4:] if host.startswith("www.") else host


def _property_host(site_url: str) -> tuple[str, bool]:
    """(host, is_domain_property) of a property identifier."""
    if site_url.startswith("sc-domain:"):
        return site_url[len("sc-domain:") :].lower().rstrip("."), True
    return _host(site_url), False


def resolve_property(domain_or_url: str, properties: list[dict[str, Any]]) -> Resolution:
    """Pick the property that covers ``domain_or_url``.

    Priority: a Domain property (``sc-domain:``, which covers every subdomain) over an exact
    URL-prefix property (https before http, www variants of the same host). Properties with
    ``siteUnverifiedUser`` do not count. No match -> ``property-not-found``; matches that are all
    unverified -> ``no-permission``.
    """
    host = _host(domain_or_url)
    if not host:
        return Resolution(None, "property-not-found")
    bare = _bare(host)

    domain_hits: list[tuple[int, dict[str, Any]]] = []
    prefix_hits: list[tuple[int, dict[str, Any]]] = []
    unverified = False
    for prop in properties:
        site = str(prop.get("site_url") or prop.get("siteUrl") or "")
        if not site:
            continue
        phost, is_domain = _property_host(site)
        if not phost:
            continue
        if is_domain:
            # covers the apex and every subdomain: "notexample.com" must not match
            if not (bare == phost or bare.endswith("." + phost)):
                continue
            rank = 0 if phost == bare else 1  # exact apex beats a parent domain
        else:
            if _bare(phost) != bare:
                continue
            p = urlparse(site)
            path_ok = p.path in ("", "/")
            if not path_ok:  # a directory property does not cover the whole site
                continue
            rank = (0 if p.scheme == "https" else 2) + (0 if phost == host else 1)
        perm = str(prop.get("permission") or prop.get("permissionLevel") or "")
        if perm in _NO_ACCESS:
            unverified = True
            continue
        (domain_hits if is_domain else prefix_hits).append((rank, {**prop, "site_url": site}))

    for hits in (domain_hits, prefix_hits):
        if hits:
            _rank, best = min(hits, key=lambda h: (h[0], h[1]["site_url"]))
            return Resolution(
                best["site_url"],
                None,
                str(best.get("permission") or best.get("permissionLevel") or ""),
            )
    return Resolution(None, "no-permission" if unverified else "property-not-found")


# --------------------------------------------------------------------------- client
