"""Loaders for versioned rule data and prompt files; known-wrong-facts scanning (V5)."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from seoa.config import ROOT

RULES_DIR = ROOT / "data" / "rules"
PROMPTS_DIR = Path(__file__).parent / "prompts"


@lru_cache(maxsize=None)
def load_rules(name: str) -> dict[str, Any]:
    return dict(json.loads((RULES_DIR / name).read_text(encoding="utf-8")))


@lru_cache(maxsize=None)
def _prompt_raw(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8").strip()


@dataclass(frozen=True)
class Prompt:
    text: str
    version: str  # content hash: any edit invalidates the cache (belge 03 s.12)


def load_prompt(name: str, **values: str) -> Prompt:
    """Compile a prompt: ``{{security}}``-style shared blocks, then ``{name}`` values."""
    text = _prompt_raw(name)
    for block in ("security", "honesty", "output"):
        text = text.replace("{{" + block + "}}", _prompt_raw(f"_{block}"))
    for k, v in values.items():
        text = text.replace("{" + k + "}", v)
    shared = "".join(_prompt_raw(f"_{b}") for b in ("security", "honesty", "output"))
    digest = hashlib.sha256((_prompt_raw(name) + shared).encode()).hexdigest()[:10]
    return Prompt(text, f"{name}-{digest}")


@dataclass(frozen=True)
class KnownWrongHit:
    id: str
    statement_right: str
    matched: str


@lru_cache(maxsize=1)
def _compiled() -> list[tuple[dict[str, Any], re.Pattern[str]]]:
    return [(f, re.compile(f["pattern"])) for f in load_rules("known-wrong-facts.json")["facts"]]


def scan_known_wrong(text: str) -> list[KnownWrongHit]:
    """V5: statements the model must never assert."""
    hits: list[KnownWrongHit] = []
    for fact, rx in _compiled():
        if m := rx.search(text):
            hits.append(KnownWrongHit(fact["id"], fact["statement_right"], m.group(0)[:80]))
    return hits
