"""Outbound HTTP for user-supplied URLs: the SSRF-safe client and resolver."""

from seoa.infrastructure.http.fetcher import Fetcher
from seoa.infrastructure.http.resolver import BlockedAddressError, DNSResolutionError, SafeResolver

__all__ = ["BlockedAddressError", "DNSResolutionError", "Fetcher", "SafeResolver"]
