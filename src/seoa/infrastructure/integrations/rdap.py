"""Domain registration date via RDAP (keyless). Informational only.

TLD -> RDAP server comes from the IANA bootstrap file (cached per process). A TLD missing from
the bootstrap (for example ``.tr``) yields ``error="rdap-unsupported-tld"``.

Registrable-domain extraction is deliberately simple: the last two labels, or three when the
last two form a known multi-label suffix (small list below). The Public Suffix List is NOT used
and this is not verified against it (doğrulanmadı); an unlisted multi-label suffix would query
the wrong name and normally come back as ``http-404``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from seoa.infrastructure.integrations._public_http import Session, get_json, host_of

BOOTSTRAP = "https://data.iana.org/rdap/dns.json"
MULTI_LABEL_SUFFIXES = frozenset(
    {
        "co.uk", "org.uk", "ac.uk", "gov.uk", "me.uk",
        "com.tr", "org.tr", "gov.tr", "net.tr", "edu.tr", "gen.tr", "web.tr",
        "com.au", "net.au", "org.au", "edu.au", "gov.au",
        "co.nz", "org.nz", "co.jp", "or.jp", "ne.jp", "co.in", "net.in", "org.in",
        "com.br", "net.br", "org.br", "co.za", "org.za", "com.mx", "com.ar", "com.cn", "com.hk", "com.sg",
    }
)  # fmt: skip

_bootstrap_cache: dict[str, str] = {}  # tld -> RDAP base URL


def registrable_domain(host: str) -> str:
    labels = [x for x in host_of(host).split(".") if x]
    if len(labels) <= 2:
        return ".".join(labels)
    if ".".join(labels[-2:]) in MULTI_LABEL_SUFFIXES:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def _parse_bootstrap(data: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    for svc in data.get("services", []) if isinstance(data, dict) else []:
        try:
            tlds, urls = svc[0], svc[1]
        except (IndexError, TypeError):
            continue
        base = next((u for u in urls if isinstance(u, str) and u.startswith("https://")), None)
        if base:
            for t in tlds:
                out[str(t).lower()] = base
    return out


def _registrar(data: dict[str, Any]) -> str | None:
    for ent in data.get("entities", []) or []:
        if "registrar" in (ent.get("roles") or []):
            for item in (ent.get("vcardArray") or [None, []])[1] or []:
                if isinstance(item, list) and len(item) >= 4 and item[0] == "fn":
                    return str(item[3])
    return None


async def lookup_rdap(domain: str, session: Session, *, timeout_s: float = 30.0) -> dict[str, Any]:
    out: dict[str, Any] = {
        "created": None,
        "age_days": None,
        "registrar": None,
        "registry_host": None,
        "error": None,
    }
    reg = registrable_domain(domain)
    tld = reg.rsplit(".", 1)[-1] if "." in reg else ""
    if not tld:
        out["error"] = "invalid-domain"
        return out
    if not _bootstrap_cache:
        data, err = await get_json(session, BOOTSTRAP, timeout_s=timeout_s)
        if err:
            out["error"] = f"bootstrap-{err}"
            return out
        _bootstrap_cache.update(_parse_bootstrap(data))
    base = _bootstrap_cache.get(tld)
    if base is None:
        out["error"] = "rdap-unsupported-tld"
        return out
    out["registry_host"] = urlparse(base).hostname
    data, err = await get_json(session, f"{base.rstrip('/')}/domain/{reg}", timeout_s=timeout_s)
    if err:
        out["error"] = err
        return out
    if not isinstance(data, dict):
        out["error"] = "bad-json"
        return out
    out["registrar"] = _registrar(data)
    for ev in data.get("events", []) or []:
        if isinstance(ev, dict) and ev.get("eventAction") == "registration":
            try:
                dt = datetime.fromisoformat(str(ev["eventDate"]).replace("Z", "+00:00"))
            except (KeyError, ValueError):
                continue
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            out["created"] = dt.date().isoformat()
            out["age_days"] = max(0, (datetime.now(UTC) - dt).days)
            break
    if out["created"] is None:
        out["error"] = "no-registration-event"
    return out
