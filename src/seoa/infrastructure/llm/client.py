"""Thin structured-output LLM client: cache -> budget check -> call -> validate -> charge.

Design notes
* Current Claude models reject ``temperature``/``top_p``/``top_k`` (400): determinism comes
  from the persistent cache, JSON-schema constrained output, fixed rubrics and effort=low.
* The API key never leaves ``Settings``; error messages are scrubbed before they propagate.
* ``transport`` is an injection point: any object with ``async create(**kwargs) -> message``.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from seoa.config import Settings, get_settings
from seoa.infrastructure.llm.budget import BudgetExceeded, BudgetGuard, estimate_cost
from seoa.infrastructure.llm.cache import LLMCache, cache_key

T = TypeVar("T", bound=BaseModel)


class LLMUnavailable(RuntimeError):
    """The module could not produce a validated result (refusal, schema, API error)."""


class Transport(Protocol):
    async def create(self, **kwargs: Any) -> Any: ...


@dataclass
class LLMResult:
    parsed: Any
    usage: dict[str, int]
    cost_usd: float
    cache_hit: bool
    stop_reason: str | None
    call_id: str
    latency_ms: int = 0


_KEY_RE = re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}")


def scrub(text: str, settings: Settings | None = None) -> str:
    s = settings or get_settings()
    out = _KEY_RE.sub("sk-ant-***", text)
    if s.anthropic_api_key:
        out = out.replace(s.anthropic_api_key, "***")
    return out


class _AnthropicTransport:
    def __init__(self, api_key: str, timeout: float) -> None:
        import anthropic

        self._c = anthropic.AsyncAnthropic(api_key=api_key, max_retries=2, timeout=timeout)

    async def create(self, **kwargs: Any) -> Any:
        return await self._c.messages.create(**kwargs)


def _strict_schema(model_cls: type[BaseModel]) -> dict[str, Any]:
    """Pydantic JSON schema adapted to the API's structured-output rules ($ref inlined)."""
    schema = model_cls.model_json_schema()
    defs = schema.pop("$defs", {})

    def fix(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return fix(dict(defs[node["$ref"].rsplit("/", 1)[-1]]))
            for k in (
                "title",
                "default",
                "minLength",
                "maxLength",
                "maxItems",
                "minItems",
                "format",
            ):
                node.pop(k, None)
            if node.get("type") == "object" or "properties" in node:
                node["additionalProperties"] = False
                node["required"] = list(node.get("properties", {}).keys())
            return {k: fix(v) for k, v in node.items()}
        if isinstance(node, list):
            return [fix(v) for v in node]
        return node

    return dict(fix(schema))


class LLMClient:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        budget: BudgetGuard | None = None,
        cache: LLMCache | None = None,
        transport: Transport | None = None,
        model: str | None = None,
        scope: str | None = None,
        scope_cap: float | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.model = model or self.settings.llm_model
        self.budget = budget or BudgetGuard()
        self.cache = cache or LLMCache()
        self.scope = scope
        self.scope_cap = scope_cap
        if transport is None:
            if not self.settings.anthropic_api_key:
                raise LLMUnavailable("ANTHROPIC_API_KEY is not configured")
            transport = _AnthropicTransport(self.settings.anthropic_api_key, 60.0)
        self._t = transport

    async def call_structured(
        self,
        purpose: str,
        system: str,
        user: str,
        model_cls: type[T],
        *,
        max_tokens: int = 2000,
        cache_key_parts: tuple[str, ...] = (),
    ) -> LLMResult:
        key = cache_key(self.model, purpose, system, user, *cache_key_parts)
        if (hit := self.cache.get(key)) is not None:
            return LLMResult(
                model_cls.model_validate(hit), {}, 0.0, True, "cache", uuid.uuid4().hex
            )

        est = estimate_cost(self.model, (len(system) + len(user)) // 3 + 200, max_tokens)
        self.budget.check(est, scope=self.scope, scope_cap=self.scope_cap)  # raises BudgetExceeded

        schema = _strict_schema(model_cls)
        total_cost = 0.0
        usage_acc: dict[str, int] = {}
        last_err = ""
        correction = ""
        t0 = time.monotonic()
        for _attempt in range(2):  # one correction attempt
            try:
                resp = await self._t.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": user + correction}],
                    output_config={
                        "effort": self.settings.llm_effort,
                        "format": {"type": "json_schema", "schema": schema},
                    },
                )
            except BudgetExceeded:
                raise
            except Exception as exc:  # noqa: BLE001 - scrubbed and re-raised as one type
                raise LLMUnavailable(scrub(f"{type(exc).__name__}: {exc}", self.settings)) from None
            total_cost += self.budget.charge(self.model, resp.usage, scope=self.scope)
            for k in ("input_tokens", "output_tokens", "cache_read_input_tokens"):
                usage_acc[k] = usage_acc.get(k, 0) + int(getattr(resp.usage, k, 0) or 0)
            stop = getattr(resp, "stop_reason", None)
            if stop == "refusal":
                raise LLMUnavailable("model refused the request (safety classifier)")
            text = "".join(
                getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text"
            )
            if stop == "max_tokens":
                last_err = "output truncated (max_tokens)"
                correction = "\n\nYour previous answer was cut off. Answer again, shorter."
                continue
            try:
                parsed = model_cls.model_validate(json.loads(text))
            except (json.JSONDecodeError, ValidationError) as exc:
                last_err = f"schema violation: {type(exc).__name__}"
                correction = (
                    "\n\nYour previous answer did not match the schema. Return only valid JSON."
                )
                continue
            self.cache.put(key, purpose, parsed.model_dump(mode="json"))
            return LLMResult(
                parsed,
                usage_acc,
                total_cost,
                False,
                stop,
                uuid.uuid4().hex,
                int((time.monotonic() - t0) * 1000),
            )
        raise LLMUnavailable(last_err or "no valid response")
