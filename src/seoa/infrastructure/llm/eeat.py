"""E-E-A-T danisma skoru (belge 03 s.3-5): the LLM only extracts signals with quotes.

Everything numeric (bands, factor values, advisory score, label, coverage) is computed by
code from verified signal states, so the same signal states always give the same score.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import Any, Literal

from pydantic import BaseModel

from seoa.domain import AdvisoryRecord
from seoa.infrastructure.llm.budget import BudgetExceeded
from seoa.infrastructure.llm.client import LLMClient, LLMUnavailable
from seoa.infrastructure.llm.input import ContentInput
from seoa.infrastructure.llm.known_facts import load_prompt, load_rules, scan_known_wrong
from seoa.infrastructure.llm.validators import norm, unknown_numbers, verify_quote

SignalId = Literal[
    "E1", "E2", "E3", "E4", "E5", "E6", "X1", "X3", "X6",
    "A4", "A6", "A7", "T1", "T2", "T4", "T5", "T6", "T9",
]  # fmt: skip
Field = Literal["main_text", "byline", "title", "h1", "outline", "chrome_link", "none"]


class SignalOut(BaseModel):
    signal_id: SignalId
    status: Literal["present", "absent", "unclear"]
    field: Field
    quote: str
    note: str


class ObservationOut(BaseModel):
    kind: Literal["strength", "gap"]
    signal_ids: list[SignalId]
    text: str
    quote: str


class SignalExtraction(BaseModel):
    signals: list[SignalOut]
    observations: list[ObservationOut]


_RULES = load_rules("eeat-signals.json")
RUBRIC_VERSION: str = _RULES["rubric_version"]
FACTORS = ("experience", "expertise", "authoritativeness", "trustworthiness")
_CATALOG: dict[str, dict[str, Any]] = {s["id"]: s for s in _RULES["signals"]}
_ALL_FIELDS = ("main_text", "byline", "title", "h1", "outline", "chrome_link")


def applicable_ids(page_type: str) -> list[str]:
    return [
        sid
        for sid, s in _CATALOG.items()
        if not s.get("applies_to") or page_type in s["applies_to"]
    ]


def llm_ids(page_type: str) -> list[str]:
    return [sid for sid in applicable_ids(page_type) if _CATALOG[sid]["assessor"] != "det"]


# ------------------------------------------------------------------ deterministic signals


def _parse_date(v: str | None) -> date | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(v[:10])
        except ValueError:
            return None


def det_signals(ci: ContentInput, today: date) -> dict[str, dict[str, Any]]:
    """Signals decided by code. A 'present' from code always wins over the LLM's answer."""
    out: dict[str, dict[str, Any]] = {}
    f = ci.facts

    def put(sid: str, status: str, note: str = "") -> None:
        out[sid] = {
            "signal_id": sid,
            "status": status,
            "field": "facts",
            "quote": note,
            "source": "code",
        }

    https = f.get("https_valid", f.get("https"))
    put("T3", "present" if https else "absent", "https")
    dates = f.get("dates") or {}
    d = _parse_date(dates.get("modified")) or _parse_date(dates.get("published"))
    if d is None:
        put("X5", "unclear")
    else:
        put("X5", "present" if (today - d).days <= 730 else "absent", d.isoformat())
    if ci.byline:
        put("X6", "present", ci.byline[:100])
    if (f.get("outbound_external_links_in_main") or 0) >= 2:
        put("X3", "present", f"{f['outbound_external_links_in_main']} external links")
    if f.get("contact"):
        put("T1", "present", ",".join(sorted(f["contact"])))
    if dates.get("modified"):
        put("T6", "present", str(dates["modified"]))
    return out


# ------------------------------------------------------------------ validation (V2/V3/V4)


def validate_signals(
    ci: ContentInput, raw: SignalExtraction | None, today: date
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    ids = applicable_ids(ci.page_type)
    allowed_llm = set(llm_ids(ci.page_type))
    det = det_signals(ci, today)
    stats = {"rejected_quotes": 0, "dropped_unknown": 0, "reused_quotes": 0, "missing": 0}
    llm: dict[str, SignalOut] = {}
    if raw is not None:
        for s in raw.signals:
            if s.signal_id not in allowed_llm or s.signal_id in llm:
                stats["dropped_unknown"] += 1
                continue
            llm[s.signal_id] = s
    used: set[str] = set()
    result: list[dict[str, Any]] = []
    for sid in ids:
        if sid in det and (det[sid]["status"] == "present" or _CATALOG[sid]["assessor"] == "det"):
            result.append(det[sid])
            continue
        spec = _CATALOG[sid]
        got = llm.get(sid)
        rec: dict[str, Any] = {
            "signal_id": sid,
            "status": "unclear",
            "field": "none",
            "quote": "",
            "source": "llm",
        }
        if got is None:
            stats["missing"] += 1
        elif got.status == "present":
            ok = got.field in spec["fields"] and verify_quote(got.quote, ci.field_text(got.field))
            if not ok:
                stats["rejected_quotes"] += 1
            elif norm(got.quote) in used:
                stats["reused_quotes"] += 1
            else:
                used.add(norm(got.quote))
                rec.update(status="present", field=got.field, quote=got.quote.strip())
        elif got.status == "absent":
            rec["status"] = "absent"
        result.append(rec)
    return result, stats


# ------------------------------------------------------------------ pure scoring


def factor_bands(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    th, vals = _RULES["thresholds"], _RULES["bands"]
    out: list[dict[str, Any]] = []
    for factor in FACTORS:
        mine = [s for s in signals if _CATALOG[s["signal_id"]]["factor"] == factor]
        assessable = [s for s in mine if s["status"] != "unclear"]
        present = [s for s in assessable if s["status"] == "present"]
        entry: dict[str, Any] = {
            "factor": factor,
            "weight": _RULES["weights"][factor],
            "assessed": len(assessable) >= _RULES["min_assessable"],
            "signals_assessable": len(assessable),
            "signals_present": len(present),
            "basis": "on_page_claims" if factor == "authoritativeness" else "on_page_signals",
            "band": None,
            "value": None,
            "r": None,
            "not_assessed_reason": None,
        }
        if entry["assessed"]:
            r = len(present) / len(assessable)
            band = (
                "strong"
                if r >= th["strong"]
                else "moderate"
                if r >= th["moderate"]
                else "weak"
                if r > 0
                else "none"
            )
            entry.update(r=round(r, 3), band=band, value=vals[band])
        else:
            entry["not_assessed_reason"] = "fewer than 2 assessable signals"
        out.append(entry)
    return out


def advisory_score(factors: list[dict[str, Any]]) -> tuple[float | None, str | None, float]:
    assessed = [f for f in factors if f["assessed"]]
    total_w = sum(f["weight"] for f in factors)
    coverage = 100.0 * sum(f["weight"] for f in assessed) / total_w if total_w else 0.0
    if not assessed or coverage < _RULES["min_coverage_for_score"]:
        return None, None, round(coverage, 1)
    wsum = sum(f["weight"] for f in assessed)
    score = round(sum(f["weight"] / wsum * f["value"] for f in assessed), 1)
    label = next(name for floor, name in _RULES["label_bands"] if score >= floor)
    return score, label, round(coverage, 1)


# ------------------------------------------------------------------ module entry point


def _catalog_text(page_type: str) -> str:
    lines = []
    for sid in llm_ids(page_type):
        s = _CATALOG[sid]
        claim = " CLAIM" if s["claim"] else ""
        lines.append(f"{sid} [{', '.join(s['fields'])}]{claim}: {s['definition']}")
    return "\n".join(lines)


def _filter_observations(ci: ContentInput, raw: SignalExtraction | None) -> list[dict[str, Any]]:
    if raw is None:
        return []
    valid_ids = set(llm_ids(ci.page_type))
    kept: list[dict[str, Any]] = []
    for o in raw.observations[:5]:
        if not o.signal_ids or any(i not in valid_ids for i in o.signal_ids):
            continue
        if o.quote and not any(verify_quote(o.quote, ci.field_text(f)) for f in _ALL_FIELDS):
            continue
        if scan_known_wrong(o.text):
            continue
        kept.append(
            {"kind": o.kind, "signal_ids": list(o.signal_ids), "text": o.text, "quote": o.quote}
        )
    return kept


async def run_eeat(
    client: LLMClient, ci: ContentInput, *, output_language: str = "en", today: date | None = None
) -> AdvisoryRecord:
    today = today or datetime.now(UTC).date()
    facts_json = json.dumps(
        {k: ci.facts.get(k) for k in ("https", "word_count", "dates", "contact", "schema_types")},
        ensure_ascii=False,
        default=str,
    )
    prompt = load_prompt(
        "eeat",
        page_type=ci.page_type,
        lang=ci.lang or "unknown",
        facts_json=facts_json,
        signal_catalog=_catalog_text(ci.page_type),
        output_language=output_language,
    )
    raw: SignalExtraction | None = None
    error: str | None = None
    try:
        res = await client.call_structured(
            "eeat",
            prompt.text,
            ci.envelope(),
            SignalExtraction,
            max_tokens=2500,
            cache_key_parts=(ci.content_hash(), RUBRIC_VERSION, prompt.version, output_language),
        )
        raw = res.parsed
    except (LLMUnavailable, BudgetExceeded) as exc:
        error = f"unavailable: {exc}"
    signals, stats = validate_signals(ci, raw, today)
    factors = factor_bands(signals)
    score, label, coverage = advisory_score(factors)
    observations = _filter_observations(ci, raw)
    warnings = [
        n
        for o in observations
        for n in unknown_numbers(o["text"], json.dumps(ci.facts, default=str) + ci.main_text)
    ]
    factors.append({"factor": "_meta", "stats": stats, "warnings": warnings[:10]})
    confidence: Literal["high", "medium", "low"] = (
        "medium" if (coverage >= 75 and stats["rejected_quotes"] == 0 and error is None) else "low"
    )
    return AdvisoryRecord(
        kind="eeat",
        page_url=ci.url,
        score=score,
        label=label,  # type: ignore[arg-type]
        coverage_pct=coverage,
        factors=factors,
        signals=signals,
        observations=observations,
        confidence=confidence,
        rubric_version=RUBRIC_VERSION,
        prompt_version=prompt.version,
        error=error,
    )
