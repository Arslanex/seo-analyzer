"""``SafeResolver``: validate every address at the moment aiohttp connects.

aiohttp connects to the address a resolver returns and keeps the ``Host``
header and TLS server name as the original hostname (verified empirically in
the P1 prototype). Judging the addresses *inside* the resolver therefore closes
the validate-then-connect race of a separate pre-flight check: the address that
was judged is the address that is dialled, and every redirect hop to a hostname
goes through the same resolver.

Two limits, both handled elsewhere:

* aiohttp never calls the resolver for IP-literal URLs, so those must pass
  ``policy.check_url`` first (the fetcher does this for every hop).
* a resolver cannot stop a redirect to an IP literal on its own, so redirects
  are followed manually, one validated hop at a time.
"""

from __future__ import annotations

import asyncio
import socket
from collections.abc import Awaitable, Callable

from aiohttp.abc import AbstractResolver, ResolveResult

from seoa.domain.url_safety import (
    BLOCKED_HOSTNAMES,
    URLSafetyError,
    check_resolved,
    is_safe_ip,
    normalize_hostname,
)

# lookup(host, port) -> every address string for the host, all families
Lookup = Callable[[str, int], Awaitable[list[str]]]

_NUMERIC = socket.AI_NUMERICHOST | socket.AI_NUMERICSERV


class BlockedAddressError(URLSafetyError, OSError):
    """Policy refusal raised from inside aiohttp's connect path.

    Also an ``OSError`` so aiohttp wraps it as ``ClientConnectorError`` instead
    of letting a bare ``ValueError`` escape.
    """


class DNSResolutionError(URLSafetyError, OSError):
    """DNS failure, surfaced with the same uniform type as a policy refusal."""


async def system_lookup(host: str, port: int) -> list[str]:
    """Resolve through the event loop's resolver; ALL families, never one."""
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError) as exc:
        raise DNSResolutionError(f"DNS resolution failed for {host}: {exc}") from exc
    return [str(info[4][0]) for info in infos]


class SafeResolver(AbstractResolver):
    def __init__(self, lookup: Lookup = system_lookup) -> None:
        self._lookup = lookup

    async def resolve(
        self, host: str, port: int = 0, family: socket.AddressFamily = socket.AF_INET
    ) -> list[ResolveResult]:
        try:
            name = normalize_hostname(host)
        except URLSafetyError as exc:
            raise BlockedAddressError(str(exc)) from exc
        if name in BLOCKED_HOSTNAMES:
            raise BlockedAddressError(f"Blocked hostname: {name}")

        try:
            literal = socket.inet_pton(socket.AF_INET, name)
            literal_ip: str | None = socket.inet_ntop(socket.AF_INET, literal)
        except OSError:
            try:
                literal_ip = socket.inet_ntop(
                    socket.AF_INET6, socket.inet_pton(socket.AF_INET6, name)
                )
            except OSError:
                literal_ip = None
        if literal_ip is not None:
            if not is_safe_ip(literal_ip):
                raise BlockedAddressError(f"Blocked IP literal: {name}")
            addresses = [literal_ip]
        else:
            try:
                resolved = await self._lookup(name, port)
                addresses = check_resolved(name, resolved)
            except URLSafetyError as exc:
                if isinstance(exc, OSError):
                    raise
                raise BlockedAddressError(str(exc)) from exc

        results: list[ResolveResult] = []
        for ip in addresses:
            fam = socket.AF_INET6 if ":" in ip else socket.AF_INET
            if family not in (socket.AF_UNSPEC, fam):
                continue
            results.append(
                {
                    "hostname": host,
                    "host": ip,
                    "port": port,
                    "family": fam,
                    "proto": 0,
                    "flags": _NUMERIC,
                }
            )
        if not results:
            raise DNSResolutionError(f"No usable {family.name} address for {host}")
        return results

    async def close(self) -> None:
        return None
