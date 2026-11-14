"""Technology signature database (``data/rules/techstack.json``) for the tech-stack module.

A signature is one regex on one *kind* of evidence: a response header (``key`` = header name; a
key ending in ``-`` matches any header with that prefix), a ``<meta name>`` content, a script/link
URL, a cookie name, or the raw HTML. Regexes are short and bounded; the module only ever runs
them on the first ``MAX_HTML`` characters. ``(?P<v>...)`` captures a version.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from seoa.config import ROOT, get_settings

PatternType = Literal["header", "meta", "script", "html", "cookie"]
Confidence = Literal["high", "medium", "low"]
_FALLBACK = ROOT / "data" / "rules" / "techstack.json"


@dataclass(frozen=True)
class Signature:
    type: PatternType
    key: str | None
    regex: re.Pattern[str]
    confidence: Confidence


@dataclass(frozen=True)
class Technology:
    name: str
    category: str
    website: str | None
    signatures: tuple[Signature, ...]


def _path() -> Path:
    p = get_settings().data_dir / "rules" / "techstack.json"
    return p if p.exists() else _FALLBACK


@lru_cache(maxsize=1)
def load_technologies() -> tuple[Technology, ...]:
    raw = json.loads(_path().read_text(encoding="utf-8"))
    techs: list[Technology] = []
    for t in raw["technologies"]:
        sigs = tuple(
            Signature(
                p["type"],
                (p.get("key") or None) and p["key"].lower(),
                re.compile(p["regex"], re.IGNORECASE),
                p.get("confidence", "medium"),
            )
            for p in t["patterns"]
        )
        techs.append(Technology(t["name"], t["category"], t.get("website"), sigs))
    return tuple(techs)
