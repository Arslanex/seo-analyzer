"""Post-processing gates for model output (belge 03 s.10): V3 quotes, V4 unique quotes, V6 numbers.

V1 (schema) is enforced by structured outputs + pydantic in ``client``; V2 (id integrity) and
V5 (known-wrong scan, ``known_facts.scan_known_wrong``) are applied by each agent module.
"""

from __future__ import annotations

import re
import unicodedata

MIN_QUOTE = 12
MAX_QUOTE = 200
_WS = re.compile(r"\s+")
# Turkish dotted/dotless i: fold all four to one letter *for comparison only*, so a quote copied
# with a different casing/dot of i still matches. Same function is applied to both sides.
_I_FOLD = str.maketrans({"İ": "i", "I": "i", "ı": "i"})
_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-"})


def norm(text: str) -> str:
    t = unicodedata.normalize("NFKC", text).translate(_QUOTES).translate(_I_FOLD)
    t = t.casefold().replace("̇", "")  # strip the combining dot casefold may leave
    return _WS.sub(" ", t).strip()


def verify_quote(quote: str | None, field_text: str) -> bool:
    """V3: the quote is 12-200 chars and occurs verbatim (after normalisation) in the field."""
    if not quote:
        return False
    q = quote.strip()
    if not (MIN_QUOTE <= len(q) <= MAX_QUOTE):
        return False
    return norm(q) in norm(field_text)


_NUM = re.compile(r"\d+(?:[.,]\d+)?")


def unknown_numbers(text: str, allowed_source: str) -> list[str]:
    """V6 (warning only): numbers in generated text that do not occur in the input."""
    allowed = set(_NUM.findall(allowed_source))
    return [n for n in _NUM.findall(text) if n not in allowed]
