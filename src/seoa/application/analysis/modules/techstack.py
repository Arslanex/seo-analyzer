"""Technology detection (belge 12 A1): CMS, framework, CDN, analytics, ... from what the entry page
already returned (headers, HTML, scripts, cookies). No extra requests. Informational: it produces
no findings. A signature that fits plain text (a page *talking about* jQuery) does not count:
script/link signatures only look at URLs, cookie signatures only at cookie names.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

from seoa.application.analysis.modules.techstack_db import Confidence, load_technologies
from seoa.application.analysis.plugin import AnalysisInputs, ModuleResult, register_module

MAX_HTML = 300_000
MAX_URLS = 300
_RANK = {"low": 0, "medium": 1, "high": 2}
_SRC = re.compile(
    r"""<(?:script|link|img|iframe)\b[^>]{0,400}?\b(?:src|href)\s*=\s*["']([^"']{1,500})""", re.I
)
_VALUE_CAP = 300


class TechItem(BaseModel):
    name: str
    category: str
    version: str | None = None
    evidence: str
    confidence: Literal["high", "medium", "low"]
    website: str | None = None


class TechStack(BaseModel):
    items: list[TechItem] = Field(default_factory=list)
    by_category: dict[str, list[str]] = Field(default_factory=dict)


def _cookie_names(headers: dict[str, str]) -> list[str]:
    raw = headers.get("set-cookie", "")
    names = []
    for line in raw.split("\n"):
        name = line.split("=", 1)[0].strip()
        if name and len(name) < 100:
            names.append(name)
    return names


def _metas(inp: AnalysisInputs, html: str) -> list[tuple[str, str]]:
    parsed = inp.entry_parsed
    if parsed is not None and getattr(parsed, "meta_tags", None):
        return [(n.lower(), c) for n, _p, c in parsed.meta_tags if n]
    out = []
    for m in re.finditer(r"<meta\b[^>]{0,400}>", html, re.I):
        tag = m.group(0)
        n = re.search(r"""name\s*=\s*["']([^"']{1,80})""", tag, re.I)
        c = re.search(r"""content\s*=\s*["']([^"']{0,200})""", tag, re.I)
        if n and c:
            out.append((n.group(1).lower(), c.group(1)))
    return out


def detect(headers: dict[str, str], html: str, metas: list[tuple[str, str]]) -> TechStack:
    html = html[:MAX_HTML]
    urls = [m.group(1) for m in _SRC.finditer(html)][:MAX_URLS]
    cookies = _cookie_names(headers)
    found: dict[str, list[tuple[str | None, str, Confidence]]] = {}
    techs = {t.name: t for t in load_technologies()}
    for tech in techs.values():
        for sig in tech.signatures:
            cands: list[tuple[str, str]] = []  # (text to match, evidence label)
            if sig.type == "header":
                for hk, hv in headers.items():
                    if sig.key and (
                        hk == sig.key or (sig.key.endswith("-") and hk.startswith(sig.key))
                    ):
                        cands.append((hv[:_VALUE_CAP], f"header {hk}"))
            elif sig.type == "meta":
                cands = [(c[:_VALUE_CAP], f"meta {n}") for n, c in metas if n == sig.key]
            elif sig.type == "script":
                cands = [(u, "script/link URL") for u in urls]
            elif sig.type == "cookie":
                cands = [(c, f"cookie {c}") for c in cookies]
            else:
                cands = [(html, "HTML marker")]
            for text, label in cands:
                m = sig.regex.search(text)
                if m:
                    ver = m.groupdict().get("v") if sig.regex.groupindex.get("v") else None
                    found.setdefault(tech.name, []).append((ver, label, sig.confidence))
                    break
    items: list[TechItem] = []
    for name, matches in found.items():
        tech = techs[name]
        best = max((c for _v, _l, c in matches), key=lambda c: _RANK[c])
        labels = list(dict.fromkeys(label for _v, label, _c in matches))
        if len(labels) >= 2 and best == "medium":
            best = "high"
        version = next((v for v, _l, _c in matches if v), None)
        items.append(
            TechItem(
                name=name,
                category=tech.category,
                version=version,
                evidence=", ".join(labels[:3]),
                confidence=best,
                website=tech.website,
            )
        )
    items.sort(key=lambda i: (i.category, -_RANK[i.confidence], i.name))
    by_cat: dict[str, list[str]] = {}
    for i in items:
        by_cat.setdefault(i.category, []).append(i.name)
    return TechStack(items=items, by_category=by_cat)


class TechStackModule:
    name = "techstack"
    kind = "techstack"
    timeout_s = 20.0

    async def run(self, inp: AnalysisInputs) -> ModuleResult:
        html = inp.entry_html or inp.entry_fetch.html or ""
        stack = detect(inp.entry_fetch.headers, html, _metas(inp, html[:MAX_HTML]))
        return ModuleResult(kind=self.kind, data=stack)


register_module(TechStackModule())
