"""Findings from lab performance measurements (pure; belge 11 s.3.2, s.3.3).

Input is a list of ``PagePerf`` (desktop and/or mobile per URL). Output is a ``CheckOutput``.
Core Web Vitals use the published thresholds (``integrations.psi.rate``): LCP <= 2.5 s, CLS <= 0.1.
INP is a field metric and cannot be measured in the lab.
"""

from __future__ import annotations

from collections.abc import Callable

from seoa.application.analysis.performance import messages as messages_perf
from seoa.application.analysis.performance import rules as rules_perf
from seoa.application.analysis.performance.rules import (
    LAB_RULE_IDS,
    MAX_REQUESTS,
    MOBILE_RULE_IDS,
    MOBILE_SMALL_FONT_SHARE,
    MOBILE_TAP_TARGETS_MIN,
    NO_CACHE_MIN_FILES,
    PAGE_WEIGHT_BYTES,
    RENDER_BLOCKING_MIN,
    THIRD_PARTY_BYTES_SHARE,
    THIRD_PARTY_REQUESTS,
)
from seoa.application.analysis.performance.web_vitals import rate
from seoa.domain import CheckOutput, Finding, NotChecked, PagePerf
from seoa.domain.rules.registry import make_finding

__all__ = ["perf_checks", "messages_perf", "rules_perf"]

Add = Callable[[Finding], None]

_IMAGE_ISSUES = (
    "image-too-large",
    "image-critically-large",
    "image-oversized-for-display",
    "image-legacy-format",
)


def _mib(n: int) -> str:
    return f"{n / 1048576:.1f} MiB"


def _kb(n: int | None) -> str:
    return "? KB" if n is None else f"{n / 1024:.0f} KB"


def _path(url: str) -> str:
    from urllib.parse import urlsplit

    p = urlsplit(url)
    return (p.path or "/") + (f"?{p.query[:30]}" if p.query else "")


def perf_checks(perfs: list[PagePerf]) -> CheckOutput:
    """Turn lab measurements into findings. One finding per (rule, page); desktop wins on a tie."""
    out = CheckOutput()
    seen: set[tuple[str, str]] = set()  # (check id, url): the two devices must not double-count

    def add(f: Finding) -> None:
        key = (f.id, f.url or "")
        if key not in seen:
            seen.add(key)
            out.findings.append(f)

    ordered = sorted(perfs, key=lambda p: (p.url, 0 if p.device == "desktop" else 1))
    measured = 0
    for p in ordered:
        if p.error:
            for rid in LAB_RULE_IDS:
                if p.device == "desktop" and rid in MOBILE_RULE_IDS:
                    continue
                if p.device == "mobile" and rid not in MOBILE_RULE_IDS:
                    continue
                out.not_checked.append(
                    NotChecked(check_id=rid, reason_code="render-failed", url=p.url)
                )
            continue
        measured += 1
        tag = f"{p.device}, lab"
        if p.lcp_ms is not None:
            r = rate("lcp", float(p.lcp_ms))
            if r != "good":
                add(make_finding(f"cwv-lcp-{r}", url=p.url, evidence=f"LCP {p.lcp_ms} ms ({tag})"))
        if p.cls is not None:
            r = rate("cls", float(p.cls))
            if r != "good":
                add(make_finding(f"cwv-cls-{r}", url=p.url, evidence=f"CLS {p.cls:g} ({tag})"))
        if p.device == "desktop":
            _page_findings(p, add)
        else:
            _mobile_findings(p, add)
        _image_findings(p, add)
    if measured:
        for r in ("poor", "needs-improvement"):
            out.not_checked.append(
                NotChecked(check_id=f"cwv-inp-{r}", reason_code="field-data-unavailable")
            )
    out.facts["lab_pages_measured"] = measured
    return out


def _page_findings(p: PagePerf, add: Add) -> None:
    if p.total_bytes > PAGE_WEIGHT_BYTES:
        add(
            make_finding(
                "page-weight-heavy",
                url=p.url,
                evidence=f"{_mib(p.total_bytes)}, {p.total_requests} requests",
            )
        )
    if p.total_requests > MAX_REQUESTS:
        add(
            make_finding(
                "too-many-requests",
                url=p.url,
                evidence=f"{p.total_requests} requests",
                count=p.total_requests,
            )
        )
    if p.uncompressed_text:
        n = len(p.uncompressed_text)
        add(
            make_finding(
                "uncompressed-text-resources",
                url=p.url,
                count=n,
                evidence=", ".join(_path(u) for u in p.uncompressed_text[:3]),
            )
        )
    if len(p.no_cache_static) >= NO_CACHE_MIN_FILES:
        n = len(p.no_cache_static)
        add(
            make_finding(
                "static-assets-no-cache",
                url=p.url,
                count=n,
                evidence=", ".join(_path(u) for u in p.no_cache_static[:3]),
            )
        )
    if p.render_blocking >= RENDER_BLOCKING_MIN:
        add(
            make_finding(
                "render-blocking-resources",
                url=p.url,
                count=p.render_blocking,
                evidence=f"{p.render_blocking} blocking resources",
            )
        )
    tp_req = sum(int(t.get("requests", 0)) for t in p.third_party)
    tp_bytes = sum(int(t.get("bytes", 0)) for t in p.third_party)
    share = tp_bytes / p.total_bytes if p.total_bytes else 0.0
    if tp_req >= THIRD_PARTY_REQUESTS or share >= THIRD_PARTY_BYTES_SHARE:
        top = ", ".join(str(t["host"]) for t in p.third_party[:3])
        add(
            make_finding(
                "third-party-heavy",
                url=p.url,
                count=tp_req,
                evidence=f"{tp_req} requests, {share:.0%} of bytes: {top}",
            )
        )


def _mobile_findings(p: PagePerf, add: Add) -> None:
    m = p.mobile
    if not m:
        return
    if m.get("horizontal_overflow"):
        add(
            make_finding(
                "mobile-horizontal-scroll",
                url=p.url,
                evidence="page is wider than the screen (390 px)",
            )
        )
    share = float(m.get("small_font_share") or 0.0)
    if share >= MOBILE_SMALL_FONT_SHARE:
        add(
            make_finding(
                "mobile-font-too-small", url=p.url, evidence=f"{share:.0%} of text below 12 px"
            )
        )
    n = int(m.get("small_tap_targets") or 0)
    if n >= MOBILE_TAP_TARGETS_MIN:
        ex = ", ".join(str(x) for x in (m.get("tap_target_examples") or [])[:3])
        add(
            make_finding(
                "mobile-tap-targets-small",
                url=p.url,
                count=n,
                evidence=f"{n} targets under 24 px: {ex}",
            )
        )


def _image_findings(p: PagePerf, add: Add) -> None:
    for issue in _IMAGE_ISSUES:
        # one row per file: a logo repeated in a carousel is still one file to fix
        imgs = list({i.src: i for i in p.images if issue in i.issues}.values())
        if not imgs:
            continue
        top = sorted(imgs, key=lambda i: -(i.bytes or 0))[:3]
        ev = ", ".join(f"{_path(i.src)} ({_kb(i.bytes)})" for i in top)
        add(make_finding(issue, url=p.url, count=len(imgs), evidence=ev))
