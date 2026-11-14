"""Persistent LLM spend ledger with a hard cap (user limit: USD 10, installation cap: 8).

The ledger is a JSON file written atomically and guarded by an inter-process file lock,
so concurrent workers/processes cannot overspend by racing each other.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import logging
import os
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from seoa.config import get_settings

log = logging.getLogger("seoa.infrastructure.llm.budget")


class BudgetExceeded(RuntimeError):
    """The hard cap (or a per-scope sub-budget) would be exceeded; the call is not made."""


@dataclass(frozen=True)
class Price:
    """USD per 1M tokens."""

    input: float
    output: float
    long_input: float | None = None  # input price beyond 100K prompt tokens
    long_output: float | None = None


PRICES: dict[str, Price] = {
    "claude-haiku-5-5": Price(0.10, 0.50, 0.50, 2.50),
    "claude-sonnet-5-5": Price(2.0, 10.0),
    "claude-sonnet-5": Price(2.0, 10.0),
    "claude-opus-5-5": Price(4.0, 20.0),
    "claude-opus-5": Price(5.0, 25.0),
    "claude-haiku-4-5": Price(1.0, 5.0),
}
_FALLBACK = Price(10.0, 50.0)  # unknown model: assume the most expensive tier (never undercount)
CACHE_READ = 0.10
CACHE_WRITE = 1.25


def cost_of(model: str, usage: Any) -> float:
    """Cost in USD from a real ``response.usage`` (object or dict)."""

    def g(name: str) -> int:
        v = usage.get(name) if isinstance(usage, dict) else getattr(usage, name, 0)
        return int(v or 0)

    p = PRICES.get(model, _FALLBACK)
    uncached, read, write, out = (
        g("input_tokens"),
        g("cache_read_input_tokens"),
        g("cache_creation_input_tokens"),
        g("output_tokens"),
    )
    prompt = uncached + read + write
    long = p.long_input is not None and prompt > 100_000
    pin = p.long_input if long and p.long_input is not None else p.input
    pout = p.long_output if long and p.long_output is not None else p.output
    return (
        uncached * pin + read * pin * CACHE_READ + write * pin * CACHE_WRITE + out * pout
    ) / 1_000_000


def estimate_cost(model: str, input_tokens: int, max_output_tokens: int) -> float:
    """Worst-case estimate used for the pre-call check."""
    return cost_of(model, {"input_tokens": input_tokens, "output_tokens": max_output_tokens})


class BudgetGuard:
    def __init__(self, path: Path | None = None, cap_usd: float | None = None) -> None:
        s = get_settings()
        self.path = Path(path) if path else s.data_dir / "llm_ledger.json"
        self.cap_usd = float(cap_usd if cap_usd is not None else s.llm_budget_usd)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._warned = False

    # -- storage ---------------------------------------------------------
    @contextlib.contextmanager
    def _locked(self) -> Iterator[None]:
        lock = self.path.with_suffix(".lock")
        with open(lock, "a+") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"spent_usd": 0.0, "calls": 0, "by_model": {}, "by_scope": {}}
        try:
            return dict(json.loads(self.path.read_text()))
        except (json.JSONDecodeError, OSError):
            # a corrupt ledger must never silently reset spend to zero
            raise BudgetExceeded("LLM ledger unreadable; refusing to spend") from None

    def _write(self, data: dict[str, Any]) -> None:
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".ledger-")
        try:
            with os.fdopen(fd, "w") as fh:
                json.dump(data, fh, indent=1)
            os.replace(tmp, self.path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise

    # -- api ---------------------------------------------------------------
    def spent(self, scope: str | None = None) -> float:
        with self._locked():
            d = self._read()
        if scope:
            return float(d["by_scope"].get(scope, 0.0))
        return float(d["spent_usd"])

    def check(
        self, estimated_usd: float, *, scope: str | None = None, scope_cap: float | None = None
    ) -> None:
        with self._locked():
            d = self._read()
        if d["spent_usd"] + estimated_usd > self.cap_usd:
            raise BudgetExceeded(
                f"LLM cap USD {self.cap_usd:.2f} would be exceeded "
                f"(spent {d['spent_usd']:.4f} + est {estimated_usd:.4f})"
            )
        if scope and scope_cap is not None:
            if d["by_scope"].get(scope, 0.0) + estimated_usd > scope_cap:
                raise BudgetExceeded(
                    f"sub-budget USD {scope_cap:.2f} for {scope} would be exceeded"
                )

    def charge(self, model: str, usage: Any, *, scope: str | None = None) -> float:
        c = cost_of(model, usage)
        with self._locked():
            d = self._read()
            d["spent_usd"] = float(d["spent_usd"]) + c
            d["calls"] = int(d["calls"]) + 1
            d["by_model"][model] = float(d["by_model"].get(model, 0.0)) + c
            if scope:
                d["by_scope"][scope] = float(d["by_scope"].get(scope, 0.0)) + c
            self._write(d)
        if not self._warned and d["spent_usd"] >= 0.9 * self.cap_usd:
            self._warned = True
            log.warning("LLM spend at %.0f%% of cap", 100 * d["spent_usd"] / self.cap_usd)
        return c

    def snapshot(self) -> dict[str, float]:
        with self._locked():
            d = self._read()
        return {
            "spent_usd": float(d["spent_usd"]),
            "cap_usd": self.cap_usd,
            "calls": float(d["calls"]),
        }
