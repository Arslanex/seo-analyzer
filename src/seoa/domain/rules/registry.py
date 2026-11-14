"""Check registry (belge 01 s.5): one CheckDef per rule; code, docs and tests derive from it."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from seoa.domain import Category, Finding, Layer, Severity

RULE_VERSION = "1.0"


@dataclass(frozen=True)
class CheckDef:
    id: str  # kebab-case, stable
    category: Category
    severity: Severity  # initial severity; may be lowered by context (belge 01 s.7.3)
    layer: Layer = Layer.A
    scope: Literal["page", "site"] = "page"
    heuristic: bool = False  # True -> "not a search engine rule" note
    effort_default: Literal["S", "M", "L"] = "S"
    impact_default: Literal["low", "medium", "high"] = "medium"
    message_key: str = ""
    recommendation_key: str = ""
    failure_check_key: str = ""
    leading_indicator_key: str = ""
    depends_on: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()  # "headers" | "rendered" | "lab" | "psi" | "robots" | "sitemap"
    modes: tuple[str, ...] = ("page", "site")  # audit modes in which the rule can apply
    references: tuple[str, ...] = ()
    since: str = RULE_VERSION

    def __post_init__(self) -> None:
        if not self.message_key:
            object.__setattr__(self, "message_key", f"finding.{self.id}")
        if not self.recommendation_key:
            object.__setattr__(self, "recommendation_key", f"rec.{self.id}")


RULES: dict[str, CheckDef] = {}
# key -> {"en": text, "tr": text}. Fixed texts only; never page data.
MESSAGES: dict[str, dict[str, str]] = {}


def register(defn: CheckDef) -> CheckDef:
    if defn.id in RULES and RULES[defn.id] != defn:
        raise ValueError(f"duplicate rule id with different definition: {defn.id}")
    RULES[defn.id] = defn
    return defn


def register_messages(entries: dict[str, dict[str, str]]) -> None:
    for key, texts in entries.items():
        MESSAGES.setdefault(key, {}).update(texts)


def message(key: str, lang: str = "en") -> str:
    texts = MESSAGES.get(key, {})
    return texts.get(lang) or texts.get("en") or key


def get(check_id: str) -> CheckDef:
    return RULES[check_id]


def make_finding(
    check_id: str,
    *,
    url: str | None = None,
    evidence: object = None,
    count: int | None = None,
    severity: Severity | None = None,
    severity_reason: str | None = None,
    confidence: Literal["high", "medium", "low"] = "high",
) -> Finding:
    """Build a Finding from the registry (evidence is trimmed to 200 chars)."""
    d = RULES[check_id]
    sev = severity or d.severity
    ev = None if evidence is None else str(evidence).strip()[:200]
    return Finding(
        id=d.id,
        rule_version=d.since,
        category=d.category,
        layer=d.layer,
        severity=sev,
        severity_original=d.severity if severity and severity != d.severity else None,
        severity_reason=severity_reason if severity and severity != d.severity else None,
        scope=d.scope,
        url=url,
        message_key=d.message_key,
        message=message(d.message_key, "en"),
        evidence=ev,
        count=count,
        heuristic=d.heuristic,
        confidence=confidence,
        recommendation_key=d.recommendation_key,
        effort=d.effort_default,
        impact=d.impact_default,
    )
