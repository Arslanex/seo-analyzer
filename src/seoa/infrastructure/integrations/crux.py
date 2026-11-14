"""Chrome UX Report (CrUX) API: real-user Core Web Vitals (28-day p75). Public data, one API key,
no site-owner authorisation. Sites with too little traffic have no record (that is normal).

Thresholds: Google's published CWV values (the upstream project references/cwv-thresholds.md; psi.THRESHOLDS).
INP is the only interactivity metric (FID was removed from CrUX in 2024).
"""

from __future__ import annotations

from typing import Any

import aiohttp

from seoa.application.analysis.performance.web_vitals import rate
from seoa.domain import CheckOutput, FieldData, FieldMetric, NotChecked
from seoa.infrastructure.integrations._public_http import make_session
from seoa.infrastructure.integrations.psi import api_key

ENDPOINT = "https://chromeuxreport.googleapis.com/v1/records:queryRecord"
METRICS = {
    "largest_contentful_paint": "lcp",
    "interaction_to_next_paint": "inp",
    "cumulative_layout_shift": "cls",
    "first_contentful_paint": "fcp",
    "experimental_time_to_first_byte": "ttfb",
}
_RATED = ("lcp", "inp", "cls")  # the Core Web Vitals


def _date(d: dict[str, Any] | None) -> str | None:
    if not d:
        return None
    return f"{d.get('year', 0):04d}-{d.get('month', 0):02d}-{d.get('day', 0):02d}"


def _num(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_crux(data: dict[str, Any], scope: str, form_factor: str | None) -> FieldData:
    rec = data.get("record", {})
    out: list[FieldMetric] = []
    for api_name, short in METRICS.items():
        m = rec.get("metrics", {}).get(api_name)
        if not m:
            continue
        p75 = _num(m.get("percentiles", {}).get("p75"))
        hist = m.get("histogram") or []
        shares = [_num(b.get("density")) for b in hist[:3]] + [None, None, None]
        out.append(
            FieldMetric(
                metric=short,  # type: ignore[arg-type]
                p75=p75,
                rating=rate(short, p75) if (p75 is not None and short in _RATED) else None,  # type: ignore[arg-type]
                good_share=shares[0],
                needs_improvement_share=shares[1],
                poor_share=shares[2],
            )
        )
    cp = rec.get("collectionPeriod") or {}
    return FieldData(
        scope=scope,  # type: ignore[arg-type]
        form_factor=form_factor,
        period={"first": _date(cp.get("firstDate")) or "", "last": _date(cp.get("lastDate")) or ""},
        metrics=out,
        error=None if out else "no-data",
    )


async def _query(session: Any, key: str, body: dict[str, Any]) -> tuple[int | None, dict[str, Any]]:
    try:
        async with session.post(ENDPOINT, params={"key": key}, json=body) as r:
            try:
                return r.status, await r.json(content_type=None)
            except (aiohttp.ContentTypeError, ValueError):
                return r.status, {}
    except (aiohttp.ClientError, TimeoutError):
        return None, {}


async def fetch_crux(
    url: str, origin: str, *, session: Any = None, key: str | None = None
) -> FieldData:
    """Page-level record when the page has one, else origin-level. Never raises."""
    key = key or api_key()
    if not key:
        return FieldData(error="no-api-key")
    own = session is None
    sess = session or make_session(30.0)
    try:
        for scope, body in (("url", {"url": url}), ("origin", {"origin": origin})):
            status, data = await _query(sess, key, body)
            if status == 200:
                fd = parse_crux(data, scope, None)
                if fd.metrics:
                    return fd
            elif status == 404:
                continue  # no record at this level: try the broader one
            elif status is None:
                return FieldData(error="unreachable")
            elif status in (400, 403):
                return FieldData(error=f"http-{status}")  # bad/unauthorised key or API not enabled
            elif status == 429:
                return FieldData(error="rate-limited")
            else:
                return FieldData(error=f"http-{status}")
        return FieldData(error="no-data")
    finally:
        if own:
            await sess.close()


def field_checks(fd: FieldData | None, url: str) -> CheckOutput:
    """Findings from real-user data. The same rule ids as the lab checks; evidence says "field"."""
    from seoa.domain.rules.registry import make_finding

    out = CheckOutput()
    if fd is None or fd.error or not fd.metrics:
        return out
    for m in fd.metrics:
        if m.metric in _RATED and m.p75 is not None and m.rating and m.rating != "good":
            unit = "" if m.metric == "cls" else " ms"
            out.findings.append(
                make_finding(
                    f"cwv-{m.metric}-{m.rating}",
                    url=url,
                    evidence=f"{m.metric.upper()} p75 {m.p75:g}{unit} (field, {fd.scope})",
                )
            )
    got = {m.metric for m in fd.metrics}
    for metric in _RATED:
        if metric not in got:
            out.not_checked.append(
                NotChecked(check_id=f"cwv-{metric}-poor", reason_code="field-data-unavailable")
            )
    return out
