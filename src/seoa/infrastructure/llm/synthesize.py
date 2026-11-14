"""Report text (belge 03 s.7): summary, per-finding context, cause links.

Findings, severities, scores and order are decided by code and only *described* here.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel

from seoa.domain import AdviceRecord, SynthesisRecord
from seoa.infrastructure.llm.budget import BudgetExceeded
from seoa.infrastructure.llm.client import LLMClient, LLMUnavailable
from seoa.infrastructure.llm.input import wrap_untrusted
from seoa.infrastructure.llm.known_facts import load_prompt, scan_known_wrong
from seoa.infrastructure.llm.validators import unknown_numbers

log = logging.getLogger("seoa.infrastructure.llm.synthesize")
RUBRIC_VERSION = "synthesis-1.0"
MAX_CONTEXT = 5
MAX_FINDINGS = 10


class ContextNote(BaseModel):
    finding_id: str
    text: str


class LinkNote(BaseModel):
    finding_ids: list[str]
    text: str


class SynthesisOut(BaseModel):
    summary: str
    context: list[ContextNote]
    links: list[LinkNote]


def build_input(scores_summary: dict[str, Any], findings: list[dict[str, Any]]) -> tuple[str, str]:
    """Returns (user message, plain text used by the V6 number check)."""
    top = findings[:MAX_FINDINGS]
    lines = [
        "SCORES (decided by code):",
        json.dumps(scores_summary, ensure_ascii=False, default=str),
    ]
    lines.append(f"context_for (first {MAX_CONTEXT}): {[f['id'] for f in top[:MAX_CONTEXT]]}")
    lines.append("FINDINGS (ordered by code):")
    for f in top:
        head = {
            k: f.get(k)
            for k in ("id", "severity", "category", "category_label", "message", "url", "count")
        }
        lines.append(json.dumps(head, ensure_ascii=False, default=str))
        if f.get("evidence"):
            lines.append(wrap_untrusted("evidence", str(f["evidence"])[:200]))
    text = "\n".join(lines)
    return text, text


async def run_synthesis(
    client: LLMClient,
    *,
    scores_summary: dict[str, Any],
    findings: list[dict[str, Any]],
    output_language: str = "en",
) -> tuple[SynthesisRecord, list[AdviceRecord]]:
    if not findings:
        return SynthesisRecord(summary="", error="no findings"), []
    user, plain = build_input(scores_summary, findings)
    top = findings[:MAX_FINDINGS]
    ids = {f["id"] for f in top}
    first = [f["id"] for f in top[:MAX_CONTEXT]]
    url_of = {f["id"]: f.get("url") for f in top}
    prompt = load_prompt("synthesize", output_language=output_language)
    try:
        res = await client.call_structured(
            "synthesize",
            prompt.text,
            user,
            SynthesisOut,
            max_tokens=1800,
            cache_key_parts=(RUBRIC_VERSION, prompt.version, output_language),
        )
    except (LLMUnavailable, BudgetExceeded) as exc:
        return SynthesisRecord(error=f"unavailable: {exc}"), []
    out = res.parsed
    notes: list[str] = []
    summary = out.summary.strip()
    if scan_known_wrong(summary):
        notes.append("summary rejected (known-wrong statement)")
        summary = ""
    advice: list[AdviceRecord] = []
    seen: set[str] = set()
    for c in out.context:
        if c.finding_id not in first or c.finding_id in seen or scan_known_wrong(c.text):
            continue
        seen.add(c.finding_id)
        advice.append(
            AdviceRecord(
                finding_id=c.finding_id, url=url_of.get(c.finding_id), text=c.text.strip()[:240]
            )
        )
    links: list[dict[str, Any]] = []
    for ln in out.links[:3]:
        lid = [i for i in dict.fromkeys(ln.finding_ids) if i in ids]
        if len(lid) >= 2 and not scan_known_wrong(ln.text):
            links.append({"finding_ids": lid[:3], "text": ln.text.strip()[:240]})
    # V6 is a warning, never a rejection
    for t in [summary, *(a.text for a in advice), *(link["text"] for link in links)]:
        if bad := unknown_numbers(t, plain):
            log.warning("synthesis text contains numbers not in the input: %s", bad[:5])
    return SynthesisRecord(summary=summary, links=links, error="; ".join(notes) or None), advice
