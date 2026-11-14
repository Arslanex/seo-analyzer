from __future__ import annotations

import threading

import pytest

from seoa.infrastructure.llm.budget import BudgetExceeded, BudgetGuard, cost_of


def test_cost_haiku_basic_and_long_context() -> None:
    assert cost_of(
        "claude-haiku-5-5", {"input_tokens": 10_000, "output_tokens": 1_000}
    ) == pytest.approx(0.0015)
    # beyond 100K prompt tokens the long-context rates apply ($0.50 / $2.50)
    assert cost_of(
        "claude-haiku-5-5", {"input_tokens": 200_000, "output_tokens": 0}
    ) == pytest.approx(0.10)


def test_cost_cache_rates_and_unknown_model_is_pessimistic() -> None:
    c = cost_of(
        "claude-sonnet-5-5",
        {"input_tokens": 0, "cache_read_input_tokens": 1_000_000, "output_tokens": 0},
    )
    assert c == pytest.approx(0.2)
    assert cost_of(
        "some-new-model", {"input_tokens": 1_000_000, "output_tokens": 0}
    ) == pytest.approx(10.0)


def test_check_raises_when_cap_would_be_exceeded(tmp_path) -> None:
    g = BudgetGuard(tmp_path / "l.json", cap_usd=1.0)
    g.check(0.5)
    g.charge("claude-sonnet-5-5", {"input_tokens": 400_000, "output_tokens": 0})  # $0.80
    with pytest.raises(BudgetExceeded):
        g.check(0.3)


def test_ledger_persists_across_instances(tmp_path) -> None:
    BudgetGuard(tmp_path / "l.json", 5).charge(
        "claude-haiku-5-5", {"input_tokens": 100_000, "output_tokens": 0}
    )
    assert BudgetGuard(tmp_path / "l.json", 5).spent() == pytest.approx(0.01)


def test_scope_sub_budget(tmp_path) -> None:
    g = BudgetGuard(tmp_path / "l.json", 5)
    g.charge(
        "claude-sonnet-5-5", {"input_tokens": 500_000, "output_tokens": 0}, scope="audit-1"
    )  # $1.00
    with pytest.raises(BudgetExceeded, match="sub-budget"):
        g.check(0.1, scope="audit-1", scope_cap=1.05)
    g.check(0.1, scope="audit-2", scope_cap=1.05)


def test_corrupt_ledger_never_resets_to_zero(tmp_path) -> None:
    p = tmp_path / "l.json"
    p.write_text("{not json")
    with pytest.raises(BudgetExceeded):
        BudgetGuard(p, 5).check(0.01)


def test_concurrent_charges_are_not_lost(tmp_path) -> None:
    g = BudgetGuard(tmp_path / "l.json", 100)

    def work() -> None:
        for _ in range(20):
            BudgetGuard(tmp_path / "l.json", 100).charge(
                "claude-haiku-5-5", {"input_tokens": 100_000, "output_tokens": 0}
            )

    ts = [threading.Thread(target=work) for _ in range(5)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert g.snapshot()["calls"] == 100
    assert g.spent() == pytest.approx(100 * 0.01)
