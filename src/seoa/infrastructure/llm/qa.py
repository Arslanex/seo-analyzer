"""Question answering over one finished report (belge 03 s.8): grounded, cited, no fetching."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel

from seoa.application.audit.protocol import QAAnswerRecord
from seoa.infrastructure.llm.budget import BudgetExceeded
from seoa.infrastructure.llm.client import LLMClient, LLMUnavailable
from seoa.infrastructure.llm.input import wrap_untrusted
from seoa.infrastructure.llm.known_facts import load_prompt, scan_known_wrong

RUBRIC_VERSION = "qa-1.0"
MAX_QUESTION = 500
MAX_FINDINGS_IN_CONTEXT = 14
SCORE_REFS = {
    "overall",
    "technical",
    "onpage",
    "content",
    "schema",
    "performance",
    "ai_readiness",
    "images",
    "advisory",
}
_SEV = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3, "Info": 4}
_SYN = {
    "onpage": (
        "title",
        "baslik",
        "başlık",
        "description",
        "aciklama",
        "açıklama",
        "h1",
        "heading",
        "meta",
    ),
    "technical": ("canonical", "robots", "noindex", "sitemap", "tls", "https", "redirect", "hsts"),
    "schema": ("schema", "json-ld", "jsonld", "yapisal", "yapısal"),
    "images": ("image", "gorsel", "görsel", "alt"),
    "content": ("content", "icerik", "içerik", "thin", "word", "kelime"),
    "performance": ("speed", "hiz", "hız", "lcp", "cls", "inp", "performance"),
    "ai_readiness": ("ai", "llm", "chatgpt", "perplexity", "crawler", "citab"),
}
_REFUSE = {
    "en": "This report does not contain information to answer that question.",
    "tr": "Bu rapor bu soruyu yanıtlamak için gerekli bilgiyi içermiyor.",
}


class CitationOut(BaseModel):
    finding_id: str
    score_ref: str
    url: str


class QAOut(BaseModel):
    answer: str
    citations: list[CitationOut]
    out_of_scope: bool


def build_context(report: dict[str, Any], question: str) -> tuple[str, dict[str, set[str]]]:
    """Deterministic context: scores + the most severe findings + keyword-matched findings."""
    findings = sorted(report.get("findings", []), key=lambda f: _SEV.get(str(f.get("severity")), 9))
    q = question.lower()
    tokens = set(re.findall(r"[\w-]{3,}", q))
    # Always the most severe findings (sorted by severity), whatever the question says: a question in
    # any language ("Önce neyi düzeltmeliyim?") must still see what the report found.
    chosen: list[dict[str, Any]] = list(findings[:8])
    for f in findings:
        if len(chosen) >= MAX_FINDINGS_IN_CONTEXT:
            break
        hay = f"{f.get('id', '')} {f.get('message', '')} {f.get('category', '')}".lower()
        cat_hit = any(w in q for w in _SYN.get(str(f.get("category")), ()))
        if f not in chosen and (cat_hit or any(t in hay for t in tokens)):
            chosen.append(f)
    scores = report.get("scores", {})
    lines = [
        "AUDIT: " + json.dumps(report.get("audit", {}), ensure_ascii=False, default=str),
        "SCORES: " + json.dumps(scores, ensure_ascii=False, default=str),
        "METHODOLOGY: "
        + str(report.get("methodology", "Scores are computed by code from deterministic checks.")),
        "FINDINGS:",
    ]
    for f in chosen:
        lines.append(
            json.dumps(
                {k: f.get(k) for k in ("id", "severity", "category", "url", "message", "count")},
                ensure_ascii=False,
                default=str,
            )
        )
        if f.get("evidence"):
            lines.append(wrap_untrusted("evidence", str(f["evidence"])[:120]))
    if report.get("advisory"):
        lines.append(
            "ADVISORY (estimated, not part of the overall score): "
            + json.dumps(report["advisory"], ensure_ascii=False, default=str)[:1500]
        )
    if report.get("not_checked"):
        lines.append(
            "NOT CHECKED: "
            + json.dumps(report["not_checked"][:20], ensure_ascii=False, default=str)
        )
    refs = {"overall"} | {
        str(c.get("id") or c.get("category"))
        for c in scores.get("categories", [])
        if c.get("id") or c.get("category")
    }
    if report.get("advisory"):
        refs.add("advisory")
    allowed = {
        "finding_id": {str(f["id"]) for f in chosen},
        "score_ref": refs & SCORE_REFS,
        "url": {str(f["url"]) for f in chosen if f.get("url")}
        | ({str(report["audit"]["url"])} if report.get("audit", {}).get("url") else set()),
    }
    lines.append("ALLOWED finding_id: " + ", ".join(sorted(allowed["finding_id"])))
    lines.append("ALLOWED score_ref: " + ", ".join(sorted(allowed["score_ref"])))
    return "\n".join(lines), allowed


def _valid_citations(out: QAOut, allowed: dict[str, set[str]]) -> list[dict[str, Any]]:
    good = []
    for c in out.citations:
        d: dict[str, Any] = {}
        if c.finding_id and c.finding_id in allowed["finding_id"]:
            d["finding_id"] = c.finding_id
        if c.score_ref and c.score_ref in allowed["score_ref"]:
            d["score_ref"] = c.score_ref
        if c.url and c.url in allowed["url"]:
            d["url"] = c.url
        if d:
            good.append(d)
    return good


async def answer_question(
    client: LLMClient, report_context: dict[str, Any], question: str, output_language: str = "en"
) -> QAAnswerRecord:
    refuse = _REFUSE.get(output_language, _REFUSE["en"])
    question = question.strip()
    if not question:
        return QAAnswerRecord(answer=refuse, out_of_scope=True)
    if len(question) > MAX_QUESTION:
        return QAAnswerRecord(answer=refuse, out_of_scope=True)
    context, allowed = build_context(report_context, question)
    prompt = load_prompt("qa", output_language=output_language)
    cost = 0.0
    feedback = ""
    for _ in range(2):
        user = f"REPORT CONTEXT\n{context}\n\nQUESTION: {question}{feedback}"
        try:
            res = await client.call_structured(
                "qa", prompt.text, user, QAOut, max_tokens=900,
                cache_key_parts=(RUBRIC_VERSION, prompt.version, output_language),
            )  # fmt: skip
        except (LLMUnavailable, BudgetExceeded) as exc:
            return QAAnswerRecord(answer=f"unavailable: {exc}", out_of_scope=True, cost_usd=cost)
        cost += res.cost_usd
        out: QAOut = res.parsed
        if out.out_of_scope:
            return QAAnswerRecord(
                answer=out.answer.strip() or refuse, out_of_scope=True, cost_usd=cost
            )
        cites = _valid_citations(out, allowed)
        if cites and not scan_known_wrong(out.answer):
            return QAAnswerRecord(answer=out.answer.strip(), citations=cites, cost_usd=cost)
        feedback = (
            "\n\nYour previous answer cited ids that are not in the context or made an unsupported claim. "
            "Cite only the ALLOWED ids above, or set out_of_scope to true."
        )
    return QAAnswerRecord(answer=refuse, out_of_scope=True, cost_usd=cost)
