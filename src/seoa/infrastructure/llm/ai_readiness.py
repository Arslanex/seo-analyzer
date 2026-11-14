"""AI-readiness commentary (belge 03 s.6.3): quoted observations, never a score."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel

from seoa.domain import AdvisoryRecord
from seoa.infrastructure.llm.budget import BudgetExceeded
from seoa.infrastructure.llm.client import LLMClient, LLMUnavailable
from seoa.infrastructure.llm.input import ContentInput
from seoa.infrastructure.llm.known_facts import load_prompt, scan_known_wrong
from seoa.infrastructure.llm.validators import verify_quote

RUBRIC_VERSION = "ai-commentary-1.0"


class AIObservation(BaseModel):
    kind: Literal["strength", "gap"]
    signal_ids: list[Literal["AI"]]
    text: str
    quote: str


class CommentaryOut(BaseModel):
    observations: list[AIObservation]


async def run_ai_commentary(
    client: LLMClient, ci: ContentInput, ai_facts: dict[str, Any], *, output_language: str = "en"
) -> AdvisoryRecord:
    prompt = load_prompt(
        "ai_readiness",
        facts_json=json.dumps(ai_facts, ensure_ascii=False, default=str),
        output_language=output_language,
    )
    kept: list[dict[str, Any]] = []
    error: str | None = None
    try:
        res = await client.call_structured(
            "ai_readiness",
            prompt.text,
            ci.envelope(),
            CommentaryOut,
            max_tokens=1500,
            cache_key_parts=(ci.content_hash(), RUBRIC_VERSION, prompt.version, output_language),
        )
        for o in res.parsed.observations[:5]:
            if o.quote and not verify_quote(o.quote, ci.main_text):
                continue
            if scan_known_wrong(o.text):
                continue
            kept.append({"kind": o.kind, "signal_ids": ["AI"], "text": o.text, "quote": o.quote})
    except (LLMUnavailable, BudgetExceeded) as exc:
        error = f"unavailable: {exc}"
    return AdvisoryRecord(
        kind="ai_readiness",
        page_url=ci.url,
        score=None,
        observations=kept,
        confidence="low",
        rubric_version=RUBRIC_VERSION,
        prompt_version=prompt.version,
        error=error,
    )
