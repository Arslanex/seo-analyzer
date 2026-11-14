from __future__ import annotations

import pytest
from pydantic import BaseModel

from seoa.infrastructure.llm.budget import BudgetExceeded
from seoa.infrastructure.llm.client import LLMUnavailable, scrub
from tests.support.llm import SETTINGS, FakeTransport, make_client


class Out(BaseModel):
    a: int
    b: str


async def test_success_then_cache_hit(tmp_path) -> None:
    t = FakeTransport({"a": 1, "b": "x"})
    c = make_client(tmp_path, t)
    r1 = await c.call_structured("p", "sys", "user", Out)
    r2 = await c.call_structured("p", "sys", "user", Out)
    assert r1.parsed.a == 1 and not r1.cache_hit and r1.cost_usd > 0
    assert r2.cache_hit and r2.cost_usd == 0 and len(t.calls) == 1


async def test_request_shape_has_no_forbidden_params(tmp_path) -> None:
    t = FakeTransport({"a": 1, "b": "x"})
    await make_client(tmp_path, t).call_structured("p", "sys", "u", Out)
    kw = t.calls[0]
    assert (
        "temperature" not in kw
        and "top_p" not in kw
        and "thinking" not in kw
        and "tool_choice" not in kw
    )
    assert kw["output_config"]["effort"] == SETTINGS.llm_effort
    schema = kw["output_config"]["format"]["schema"]
    assert schema["additionalProperties"] is False and set(schema["required"]) == {"a", "b"}
    assert kw["messages"][-1]["role"] == "user"  # no prefill


async def test_budget_exceeded_makes_no_call(tmp_path) -> None:
    t = FakeTransport({"a": 1, "b": "x"})
    c = make_client(tmp_path, t, cap=0.0000001)
    with pytest.raises(BudgetExceeded):
        await c.call_structured("p", "sys", "u", Out)
    assert t.calls == []


async def test_schema_violation_gets_one_correction(tmp_path) -> None:
    t = FakeTransport({"a": "not-int", "b": 1}, {"a": 2, "b": "ok"})
    r = await make_client(tmp_path, t).call_structured("p", "sys", "u", Out)
    assert r.parsed.a == 2 and len(t.calls) == 2
    assert "did not match the schema" in t.calls[1]["messages"][-1]["content"]


async def test_two_violations_raise_unavailable(tmp_path) -> None:
    t = FakeTransport("not json at all")
    with pytest.raises(LLMUnavailable):
        await make_client(tmp_path, t).call_structured("p", "sys", "u", Out)
    assert len(t.calls) == 2


async def test_refusal_is_unavailable_and_still_charged(tmp_path) -> None:
    t = FakeTransport(("", "refusal"))
    c = make_client(tmp_path, t)
    with pytest.raises(LLMUnavailable, match="refused"):
        await c.call_structured("p", "sys", "u", Out)
    assert c.budget.spent() > 0


async def test_max_tokens_retries_once(tmp_path) -> None:
    t = FakeTransport(('{"a":1,', "max_tokens"), {"a": 3, "b": "z"})
    r = await make_client(tmp_path, t).call_structured("p", "sys", "u", Out)
    assert r.parsed.a == 3


async def test_api_key_never_leaks_in_errors(tmp_path) -> None:
    t = FakeTransport(
        RuntimeError(f"401 bad key {SETTINGS.anthropic_api_key} sk-ant-OTHERKEY987654321")
    )
    with pytest.raises(LLMUnavailable) as ei:
        await make_client(tmp_path, t).call_structured("p", "sys", "u", Out)
    assert "FAKEKEY" not in str(ei.value) and "OTHERKEY" not in str(ei.value)


def test_scrub() -> None:
    assert "sk-ant-" in scrub("x sk-ant-abcdefgh12345 y") and "abcdefgh" not in scrub(
        "x sk-ant-abcdefgh12345 y"
    )
