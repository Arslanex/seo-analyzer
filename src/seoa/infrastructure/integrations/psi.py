"""PageSpeed Insights v5 client (optional: needs a Google API key).

The rules, rating thresholds and response parsing live in
``application.analysis.performance.web_vitals``; this module only talks to Google.
"""

from __future__ import annotations

import os

import aiohttp

from seoa.application.analysis.performance.web_vitals import parse_psi
from seoa.domain import CheckOutput

ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"


def api_key() -> str | None:
    """One Google Cloud API key serves PageSpeed Insights and the CrUX API."""
    return os.environ.get("SEOA_GOOGLE_API_KEY") or os.environ.get("SEOA_PSI_API_KEY") or None


async def run_psi(
    url: str, *, timeout_s: float = 90.0, session: aiohttp.ClientSession | None = None
) -> CheckOutput | None:
    """None when PSI cannot be used (no key, quota, network): the category stays 'not measured'."""
    key = api_key()
    if not key:
        return None
    own = session is None
    sess = session or aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout_s))
    try:
        async with sess.get(
            ENDPOINT,
            params={"url": url, "strategy": "mobile", "category": "performance", "key": key},
        ) as r:
            if r.status != 200:
                return None
            return parse_psi(await r.json(), url)
    except (aiohttp.ClientError, TimeoutError):
        return None
    finally:
        if own:
            await sess.close()
