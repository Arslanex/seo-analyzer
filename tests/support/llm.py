"""Fake LLM transport shared by the llm unit tests (no network, no API key)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from seoa.config import Settings
from seoa.infrastructure.llm.budget import BudgetGuard
from seoa.infrastructure.llm.cache import LLMCache
from seoa.infrastructure.llm.client import LLMClient

SETTINGS = Settings(anthropic_api_key="sk-ant-FAKEKEY0123456789")


class FakeTransport:
    """Scripted responses: each item is a dict (JSON body), a str (raw text), or an Exception."""

    def __init__(
        self, *script: Any, stop_reason: str = "end_turn", in_tok: int = 1000, out_tok: int = 200
    ) -> None:
        self.script = list(script)
        self.calls: list[dict[str, Any]] = []
        self.stop_reason = stop_reason
        self.in_tok, self.out_tok = in_tok, out_tok

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        item = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if isinstance(item, Exception):
            raise item
        text = item if isinstance(item, str) else json.dumps(item)
        stop = self.stop_reason
        if isinstance(item, tuple):  # (text, stop_reason)
            text, stop = item
        return SimpleNamespace(
            usage=SimpleNamespace(
                input_tokens=self.in_tok,
                output_tokens=self.out_tok,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
            ),
            stop_reason=stop,
            content=[SimpleNamespace(type="text", text=text)],
        )


def make_client(tmp_path: Any, transport: FakeTransport, cap: float = 5.0, **kw: Any) -> LLMClient:
    return LLMClient(
        settings=SETTINGS,
        budget=BudgetGuard(tmp_path / "ledger.json", cap),
        cache=LLMCache(tmp_path / "cache.sqlite"),
        transport=transport,
        **kw,
    )
