"""Stratified, seeded sampling (belge 05 s.9.4; core vs exploration, belge 00 s.3.3).

Deterministic: the same candidates + seed give the same sample.
"""

from __future__ import annotations

import hashlib
import random
from collections import defaultdict
from dataclasses import dataclass
from typing import Literal

from seoa.domain.urls import is_low_value, template_key, url_key


@dataclass(frozen=True)
class Candidate:
    url: str
    lastmod: str | None = None
    in_sitemap: bool = False
    linked: bool = False


@dataclass(frozen=True)
class Sampled:
    url: str
    sample_kind: Literal["core", "exploration"]
    template_key: str


def _stable(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()


def select_sample(
    candidates: list[Candidate],
    *,
    n: int,
    seed: int,
    mandatory: list[str] | None = None,
    max_template_share: float = 1 / 3,
) -> tuple[list[Sampled], dict[str, dict[str, int]]]:
    """Returns (sample, template_stats). ``mandatory`` URLs are always core."""
    mandatory = mandatory or []
    seen: set[str] = set()
    out: list[Sampled] = []

    def add(url: str, kind: Literal["core", "exploration"]) -> bool:
        k = url_key(url)
        if k in seen or len(out) >= n:
            return False
        seen.add(k)
        out.append(Sampled(url, kind, template_key(url)))
        return True

    for u in mandatory:
        add(u, "core")

    by_tpl: dict[str, list[Candidate]] = defaultdict(list)
    uniq: dict[str, Candidate] = {}
    for c in sorted(candidates, key=lambda c: c.url):
        uniq.setdefault(url_key(c.url), c)
    for c in uniq.values():
        by_tpl[template_key(c.url)].append(c)
    stats = {t: {"discovered": len(cs), "sampled": 0} for t, cs in by_tpl.items()}

    # 1) one fixed representative per template -> core (stable across seeds)
    templates = sorted(by_tpl, key=lambda t: (-len(by_tpl[t]), t))
    templates.sort(key=lambda t: is_low_value(by_tpl[t][0].url))  # low-value templates last
    for t in templates:
        rep = min(by_tpl[t], key=lambda c: _stable(c.url))
        add(rep.url, "core")

    # 2) exploration quota proportional to template size, seeded, capped per template
    remaining = n - len(out)
    if remaining > 0:
        cap = max(1, int(n * max_template_share))
        weights = {
            t: len(cs) * (0.3 if is_low_value(cs[0].url) else 1.0) for t, cs in by_tpl.items()
        }
        total_w = sum(weights.values()) or 1.0
        rng = random.Random(seed)
        quota = {t: min(cap, max(0, round(remaining * w / total_w))) for t, w in weights.items()}
        for t in sorted(by_tpl):
            pool = [c for c in by_tpl[t] if url_key(c.url) not in seen]
            newest = sorted(pool, key=lambda c: (c.lastmod or "", c.url), reverse=True)
            take: list[Candidate] = newest[: max(0, quota[t] // 2)]
            rest = [c for c in pool if c not in take]
            rng.shuffle(rest)
            take += rest[: max(0, quota[t] - len(take))]
            for c in take:
                add(c.url, "exploration")
        # top up deterministically if rounding left slots; the per-template cap holds
        # unless no other template has candidates left
        if len(out) < n:
            counts: dict[str, int] = defaultdict(int)
            for x in out:
                counts[x.template_key] += 1
            leftovers = [c for c in uniq.values() if url_key(c.url) not in seen]
            rng.shuffle(leftovers)
            for relax in (False, True):
                for c in leftovers:
                    if len(out) >= n:
                        break
                    t = template_key(c.url)
                    if not relax and counts[t] >= cap:
                        continue
                    if add(c.url, "exploration"):
                        counts[t] += 1

    for s in out:
        if s.template_key in stats:
            stats[s.template_key]["sampled"] += 1
        else:
            stats[s.template_key] = {"discovered": 1, "sampled": 1}
    return out, stats
