"""Agent readiness module (belge 12 A8): what an AI agent that browses or reads the site meets.

Adapted from the upstream project ``scripts/agentic_check.py`` (llms.txt format rules, Markdown delivery,
Content-Signal, WebMCP traces) and ``skills/seo-agentic/SKILL.md`` (priorities, honest-reporting
rules). MIT.

What this module does NOT do, on purpose:

* No Lighthouse "Agentic Browsing" fraction. That ``X/N`` comes from Lighthouse via PSI; without
  PSI it is not produced (``lighthouse_fraction`` stays ``None``). ``fraction`` below is our own
  small checklist and says so.
* No AI-crawler access analysis and no "llms.txt missing" finding: the robots module already does
  both (``ai_crawlers``, ``llms-txt-missing``); only the *content* of an existing llms.txt is
  judged here.
* ``Accept: text/markdown`` negotiation is not tested: ``FetcherLike`` has no request-header
  parameter. It is reported as a ``NotChecked`` (``fetcher-headers-unsupported``). A ``.md`` sibling
  URL and a ``rel="alternate" type="text/markdown"`` link are checked instead.
* Honest-reporting rules of the skill apply: nothing here is said to affect Google Search or to
  be requested by a named agent; llms.txt, Content-Signal and WebMCP are drafts or community
  practice, so every finding is Info or Low and heuristic.

At most ``MAX_REQUESTS`` requests, all through the safe fetcher; fetched documents are untrusted
data and are only measured, never followed or obeyed.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from seoa.application.analysis.plugin import AnalysisInputs, ModuleResult, register_module
from seoa.application.ports import FetcherLike
from seoa.domain import Category, Finding, NotChecked, Severity
from seoa.domain.parsing.html import _HTML_PARSER
from seoa.domain.rules.registry import CheckDef, make_finding, register, register_messages

MAX_REQUESTS = 6
LLMS_MAX_BYTES = 200_000
DOC_MAX_BYTES = 100_000
LLMS_MAX_LINES = 5000
LLMS_OVERSIZE_BYTES = 100_000
MAX_HTML_CHARS = 1_500_000

AI = Category.AI_READINESS
Status = Literal["pass", "fail", "unknown", "na"]

_SPECS: tuple[tuple[str, Severity], ...] = (
    ("llms-txt-malformed", Severity.LOW),
    ("markdown-not-available", Severity.INFO),
    ("content-signal-missing", Severity.INFO),
    ("agent-unfriendly-controls", Severity.LOW),
)
for _id, _sev in _SPECS:
    register(
        CheckDef(
            id=_id,
            category=AI,
            severity=_sev,
            scope="site" if _id != "agent-unfriendly-controls" else "page",
            heuristic=True,
            effort_default="S",
            impact_default="low",
            message_key=f"finding.{_id}",
            recommendation_key=f"rec.{_id}",
            failure_check_key=f"fail.{_id}",
            leading_indicator_key=f"lead.{_id}",
        )
    )
AGENTIC_RULE_IDS = tuple(s[0] for s in _SPECS)

_MSG: dict[str, tuple[str, str, str, str, str, str, str, str]] = {
    "llms-txt-malformed": (
        "The site's /llms.txt exists but does not follow the llmstxt.org proposal (title, summary, sections with links). Google Search ignores this file.",
        "Sitenin /llms.txt dosyası var ama llmstxt.org önerisine uymuyor (başlık, özet, bağlantılı bölümler). Google Arama bu dosyayı yok sayar.",
        "Start with one H1 title, add a short blockquote summary and H2 sections that list Markdown links with short notes.",
        "Tek bir H1 başlıkla başlayın, kısa bir alıntı özeti ve kısa notlarla Markdown bağlantıları listeleyen H2 bölümleri ekleyin.",
        "A fresh audit finds a title, summary and linked sections in llms.txt.",
        "Yeni bir denetim llms.txt içinde başlık, özet ve bağlantılı bölümleri buluyor.",
        "Format notes of an llms.txt validator you trust.",
        "Güvendiğiniz bir llms.txt doğrulayıcısının biçim notları.",
    ),
    "markdown-not-available": (
        "No Markdown version of the page was found (no .md URL and no alternate Markdown link). Optional; no AI service is confirmed to request it.",
        "Sayfanın Markdown sürümü bulunamadı (.md URL'si ve alternatif Markdown bağlantısı yok). İsteğe bağlıdır; hiçbir yapay zekâ hizmetinin bunu istediği doğrulanmış değildir.",
        "If agents are a target audience, offer a content-equivalent Markdown version through a .md URL or a rel=alternate link.",
        "Hedef kitlenizde yapay zekâ ajanları varsa, içeriği eşdeğer bir Markdown sürümünü .md URL'si veya rel=alternate bağlantısıyla sunun.",
        "A fresh audit finds the Markdown version.",
        "Yeni bir denetim Markdown sürümünü buluyor.",
        "Requests to the Markdown URLs in your server logs.",
        "Sunucu günlüklerinde Markdown URL'lerine gelen istekler.",
    ),
    "content-signal-missing": (
        "robots.txt has no Content-Signal line stating how content may be used (search, ai-input, ai-train). Content-Signal is a draft, and it does not affect Google Search.",
        "robots.txt'de içeriğin nasıl kullanılabileceğini (search, ai-input, ai-train) belirten bir Content-Signal satırı yok. Content-Signal bir taslaktır ve Google Arama'yı etkilemez.",
        "If you want to state a policy, add Content-Signal to the relevant robots.txt groups; decide the ai-train value yourself.",
        "Bir politika belirtmek istiyorsanız ilgili robots.txt gruplarına Content-Signal ekleyin; ai-train değerine kendiniz karar verin.",
        "A fresh audit finds Content-Signal in robots.txt.",
        "Yeni bir denetim robots.txt içinde Content-Signal buluyor.",
        "The policy you stated being read by the services you care about.",
        "Belirttiğiniz politikanın önemsediğiniz hizmetlerce okunması.",
    ),
    "agent-unfriendly-controls": (
        "Some buttons, form fields or links have no accessible name, so an agent (or a screen reader) cannot tell what they do.",
        "Bazı düğmelerin, form alanlarının veya bağlantıların erişilebilir adı yok; bir ajan (veya ekran okuyucu) ne işe yaradıklarını anlayamaz.",
        "Give every button, input and link visible text, a <label>, or an aria-label.",
        "Her düğmeye, alana ve bağlantıya görünür metin, <label> veya aria-label verin.",
        "A fresh audit finds no unnamed controls.",
        "Yeni bir denetim adsız kontrol bulmuyor.",
        "An accessibility checker (for example Lighthouse) reporting no unnamed controls.",
        "Bir erişilebilirlik denetleyicisinin (örneğin Lighthouse) adsız kontrol bildirmemesi.",
    ),
}
register_messages(
    {
        key: {"en": en, "tr": tr}
        for rid, m in _MSG.items()
        for key, en, tr in (
            (f"finding.{rid}", m[0], m[1]),
            (f"rec.{rid}", m[2], m[3]),
            (f"fail.{rid}", m[4], m[5]),
            (f"lead.{rid}", m[6], m[7]),
        )
    }
)


# ------------------------------------------------------------------------------- output model


class AgenticCheck(BaseModel):
    id: str
    status: Status
    detail: str = ""  # stable code(s), the report translates


class AgenticReadiness(BaseModel):
    checks: list[AgenticCheck] = Field(default_factory=list)
    fraction: str = "0/0"  # our own checklist: pass / (pass + fail); unknown and na are excluded
    lighthouse_fraction: str | None = None  # only ever filled from PSI/Lighthouse, never by us
    llms_txt_notes: list[str] = Field(default_factory=list)
    unnamed: dict[str, int] = Field(default_factory=dict)
    requests: int = 0
    notes: list[str] = Field(default_factory=list)


# ------------------------------------------------------------------------------- llms.txt

_LINK = re.compile(r"\[[^\]\n]{1,200}\]\([^)\s]{1,500}\)")
_H1 = re.compile(r"^#\s+\S")
_H2 = re.compile(r"^##\s+\S")
_FENCE = re.compile(r"^(```|~~~)")


def llms_txt_notes(text: str) -> list[str]:
    """Stable note codes for an llms.txt body (Lighthouse-style errors + llmstxt.org structure).

    Linear time; lines beyond ``LLMS_MAX_LINES`` are ignored.
    """
    raw = text.lstrip("﻿")
    if re.match(r"\s*<(!doctype|html)", raw[:200], re.I):
        return ["served-html"]
    notes: list[str] = []
    lines = raw.splitlines()[:LLMS_MAX_LINES]
    content = [ln.strip() for ln in lines if ln.strip()]
    if len(raw.strip()) < 50:
        notes.append("too-short")
    in_fence = False
    h1_count = h2_count = link_count = 0
    first = content[0] if content else ""
    summary_after_title = len(content) > 1 and content[1].startswith(">")
    for ln in content:
        if _FENCE.match(ln):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if _H1.match(ln):
            h1_count += 1
        elif _H2.match(ln):
            h2_count += 1
        link_count += len(_LINK.findall(ln))
    if h1_count == 0:
        notes.append("missing-h1")
    elif not _H1.match(first):
        notes.append("h1-not-first")
    if h1_count > 1:
        notes.append("multiple-h1")
    if h1_count and not any(ln.startswith(">") for ln in content[:5]) and not summary_after_title:
        notes.append("no-summary-blockquote")
    if link_count == 0:
        notes.append("no-markdown-links")
    if h2_count == 0:
        notes.append("no-h2-sections")
    if len(raw.encode("utf-8", "replace")) > LLMS_OVERSIZE_BYTES:
        notes.append("oversize")
    return notes


# Notes that make the file "malformed" (the Lighthouse-style hard errors plus structure);
# the rest are hygiene notes shown in the report only.
_HARD = {"served-html", "too-short", "missing-h1", "no-markdown-links"}
_SOFT_FINDING = {"h1-not-first", "multiple-h1", "no-summary-blockquote", "no-h2-sections"}


# ------------------------------------------------------------------------------- DOM checks

_INPUT_SKIP = {"hidden", "submit", "button", "reset", "image"}


MAX_CONTROLS = 500  # per kind; a page with more is judged on its first 500 (hostile markup)


def _has_label(el: Any, label_for: set[str]) -> bool:
    for attr in ("aria-label", "aria-labelledby", "title", "placeholder"):
        if str(el.get(attr) or "").strip():
            return True
    if str(el.get("id") or "") in label_for:
        return True
    return el.find_parent("label") is not None


def unnamed_controls(html: str) -> dict[str, int]:
    """Counts of buttons, inputs and links without an accessible name (no accessibility tree)."""
    soup = BeautifulSoup(html[:MAX_HTML_CHARS], _HTML_PARSER)
    label_for = {str(lb.get("for")) for lb in soup.find_all("label", attrs={"for": True})}
    buttons = 0
    for b in [*soup.find_all("button"), *soup.find_all(None, {"role": "button"})][:MAX_CONTROLS]:
        name = b.get_text(" ", strip=True)
        has_img_alt = any(str(i.get("alt") or "").strip() for i in b.find_all("img"))
        if not (name or has_img_alt or _has_label(b, label_for)):
            buttons += 1
    inputs = 0
    for i in soup.find_all(["input", "select", "textarea"])[:MAX_CONTROLS]:
        if i.name == "input" and str(i.get("type") or "text").lower() in _INPUT_SKIP:
            continue
        if not _has_label(i, label_for):
            inputs += 1
    links = 0
    for a in soup.find_all("a", href=True)[:MAX_CONTROLS]:
        if a.get_text(" ", strip=True) or any(
            str(i.get("alt") or "").strip() for i in a.find_all("img")
        ):
            continue
        if not _has_label(a, label_for):
            links += 1
    return {"buttons": buttons, "inputs": inputs, "links": links}


_MD_ALTERNATE = re.compile(
    r"<link\b[^>]*\brel=[\"']?alternate[\"']?[^>]*\btype=[\"']?text/markdown", re.I
)
_MD_ALTERNATE_REV = re.compile(
    r"<link\b[^>]*\btype=[\"']?text/markdown[\"']?[^>]*\brel=[\"']?alternate", re.I
)
_WEBMCP_MARKS = ("modelContext", "registerTool(", "ai-plugin+json")


# ------------------------------------------------------------------------------- fetching


@dataclass
class _Doc:
    status: int | None
    body: str
    content_type: str
    error: str | None = None

    @property
    def is_real(self) -> bool:
        """A 200 that is not an HTML catch-all page (the soft-404 trap)."""
        head = self.body[:200].lstrip().lower()
        return (
            self.status == 200
            and bool(self.body.strip())
            and "html" not in self.content_type
            and not head.startswith(("<!doctype", "<html"))
        )


class _Budget:
    def __init__(self, fetcher: FetcherLike, limit: int) -> None:
        self.fetcher = fetcher
        self.left = limit
        self.used = 0

    async def get(self, url: str, max_bytes: int) -> _Doc | None:
        if self.left <= 0:
            return None
        self.left -= 1
        self.used += 1
        try:
            raw = await self.fetcher.fetch_bytes(url, max_bytes=max_bytes)
        except Exception as exc:  # noqa: BLE001 - one fetch must not break the module
            return _Doc(None, "", "", f"internal-error: {type(exc).__name__}")
        return _Doc(
            raw.status,
            raw.body[:max_bytes].decode("utf-8", "replace"),
            raw.headers.get("content-type", "").lower(),
            raw.error,
        )


def _json_dict(doc: _Doc | None) -> dict[str, Any] | None:
    if doc is None or not doc.is_real:
        return None
    try:
        data = json.loads(doc.body)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _md_sibling(entry_url: str) -> str:
    p = urlparse(entry_url)
    path = p.path.rstrip("/")
    return f"{p.scheme}://{p.netloc}" + (path + ".md" if path else "/index.md")


# ------------------------------------------------------------------------------- the audit


async def audit_agentic(
    inp: AnalysisInputs,
) -> tuple[AgenticReadiness, list[Finding], list[NotChecked]]:
    report = AgenticReadiness()
    findings: list[Finding] = []
    not_checked: list[NotChecked] = []
    budget = _Budget(inp.fetcher, MAX_REQUESTS)
    origin = inp.origin.rstrip("/")
    robots = getattr(inp.robots, "raw", None)
    html = (inp.entry_html or inp.entry_fetch.html or "")[:MAX_HTML_CHARS]

    # 1. llms.txt content (its absence is judged by the robots module)
    present = getattr(robots, "llms_txt_present", None)
    if present is False:
        report.checks.append(AgenticCheck(id="llms-txt", status="na", detail="absent-optional"))
    elif present is None and robots is None:
        report.checks.append(
            AgenticCheck(id="llms-txt", status="unknown", detail="robots-unavailable")
        )
    else:
        doc = await budget.get(f"{origin}/llms.txt", LLMS_MAX_BYTES)
        if doc is None or doc.error or doc.status is None:
            report.checks.append(
                AgenticCheck(id="llms-txt", status="unknown", detail="fetch-failed")
            )
            not_checked.append(NotChecked(check_id="llms-txt-malformed", reason_code="unreachable"))
        elif not doc.is_real:
            code = "served-html" if doc.status == 200 else f"http-{doc.status}"
            status: Status = "na" if doc.status != 200 and doc.status < 500 else "fail"
            report.checks.append(AgenticCheck(id="llms-txt", status=status, detail=code))
            if status == "fail":
                report.llms_txt_notes = [code]
        else:
            notes = llms_txt_notes(doc.body)
            report.llms_txt_notes = notes
            hard = [n for n in notes if n in _HARD]
            soft = [n for n in notes if n in _SOFT_FINDING]
            bad = hard or soft
            report.checks.append(
                AgenticCheck(
                    id="llms-txt", status="fail" if bad else "pass", detail=",".join(notes)
                )
            )
            if bad:
                findings.append(
                    make_finding(
                        "llms-txt-malformed",
                        url=f"{origin}/llms.txt",
                        evidence=", ".join(bad),
                        count=len(bad),
                    )
                )

    # 2. Markdown delivery: .md sibling and alternate link; negotiation cannot be tested
    not_checked.append(
        NotChecked(check_id="markdown-negotiation", reason_code="fetcher-headers-unsupported")
    )
    alt_link = bool(_MD_ALTERNATE.search(html) or _MD_ALTERNATE_REV.search(html))
    md = await budget.get(_md_sibling(inp.entry_url), DOC_MAX_BYTES)
    md_ok = md is not None and md.is_real
    if alt_link or md_ok:
        report.checks.append(
            AgenticCheck(
                id="markdown-delivery",
                status="pass",
                detail=",".join(
                    x for x, ok in (("alternate-link", alt_link), ("md-sibling", md_ok)) if ok
                ),
            )
        )
    elif md is None or md.error or md.status is None:
        report.checks.append(
            AgenticCheck(id="markdown-delivery", status="unknown", detail="fetch-failed")
        )
    else:
        report.checks.append(AgenticCheck(id="markdown-delivery", status="na", detail="not-found"))
        findings.append(
            make_finding(
                "markdown-not-available",
                url=inp.entry_url,
                evidence="no .md sibling, no alternate Markdown link; Accept negotiation not tested",
            )
        )

    # 3. Content-Signal in robots.txt
    groups = getattr(getattr(robots, "rules", None), "groups", None)
    if robots is None or groups is None or getattr(robots, "status", "ok") == "unreachable":
        report.checks.append(
            AgenticCheck(id="content-signal", status="unknown", detail="robots-unavailable")
        )
        not_checked.append(
            NotChecked(check_id="content-signal-missing", reason_code="robots-unavailable")
        )
    else:
        signals = [s for g in groups for s in g.content_signal]
        if signals:
            report.checks.append(
                AgenticCheck(id="content-signal", status="pass", detail=signals[0][:80])
            )
        else:
            report.checks.append(
                AgenticCheck(id="content-signal", status="na", detail="absent-optional")
            )
            findings.append(
                make_finding(
                    "content-signal-missing",
                    url=f"{origin}/robots.txt",
                    evidence="no Content-Signal line in any robots.txt group",
                )
            )

    # 4. WebMCP / agent plugin traces
    traces = [m for m in _WEBMCP_MARKS if m in html]
    plugin = _json_dict(await budget.get(f"{origin}/.well-known/ai-plugin.json", DOC_MAX_BYTES))
    mcp = _json_dict(await budget.get(f"{origin}/.well-known/mcp", DOC_MAX_BYTES))
    if plugin is not None:
        traces.append("well-known:ai-plugin.json")
    if mcp is not None:
        traces.append("well-known:mcp")
    report.checks.append(
        AgenticCheck(
            id="agent-discovery",
            status="pass" if traces else "na",
            detail=",".join(dict.fromkeys(traces)) if traces else "none-found",
        )
    )

    # 5. agent-friendly controls
    if html.strip():
        try:
            counts = unnamed_controls(html)
        except Exception:  # noqa: BLE001 - hostile markup must not break the module
            counts = {}
        if counts:
            report.unnamed = counts
            total = sum(counts.values())
            report.checks.append(
                AgenticCheck(
                    id="named-controls",
                    status="fail" if total else "pass",
                    detail=", ".join(f"{k}={v}" for k, v in counts.items() if v) or "all-named",
                )
            )
            if total:
                findings.append(
                    make_finding(
                        "agent-unfriendly-controls",
                        url=inp.entry_url,
                        evidence=", ".join(f"{k}={v}" for k, v in counts.items() if v),
                        count=total,
                    )
                )
        else:
            report.checks.append(
                AgenticCheck(id="named-controls", status="unknown", detail="parse-failed")
            )
    else:
        report.checks.append(AgenticCheck(id="named-controls", status="unknown", detail="no-html"))
        not_checked.append(NotChecked(check_id="agent-unfriendly-controls", reason_code="no-html"))

    passed = sum(c.status == "pass" for c in report.checks)
    counted = sum(c.status in ("pass", "fail") for c in report.checks)
    report.fraction = f"{passed}/{counted}"
    report.requests = budget.used
    report.notes += ["local-checklist-not-lighthouse", "lighthouse-fraction-needs-psi"]
    return report, findings, not_checked


class AgenticModule:
    name = "agentic"
    kind = "agentic"
    timeout_s = 40.0

    async def run(self, inp: AnalysisInputs) -> ModuleResult:
        report, findings, not_checked = await audit_agentic(inp)
        return ModuleResult(kind=self.kind, data=report, findings=findings, not_checked=not_checked)


register_module(AgenticModule())

__all__ = [
    "AGENTIC_RULE_IDS",
    "AgenticModule",
    "AgenticReadiness",
    "audit_agentic",
    "llms_txt_notes",
    "unnamed_controls",
]
