"""Property-style tests: whatever order trades arrive in, a run must
still reconcile to the cent, conserve cash and shares, and stay off
floats. Also pins down end-to-end determinism per seed."""

import random

import pytest

from settlecore.engine import SettlementEngine
from settlecore.generator import generate_universe
from settlecore.models import TradeState
from settlecore.recon import reconcile


@pytest.mark.parametrize("shuffle_seed", [0, 1, 2, 3, 4, 5, 6, 7])
def test_random_interleavings_still_reconcile(shuffle_seed):
    trades, ledger, oc, op = generate_universe(1_000, seed=17)
    rng = random.Random(shuffle_seed)
    rng.shuffle(trades)
    engine = SettlementEngine(ledger)
    engine.run(trades)
    report = reconcile(trades, ledger, oc, op)
    assert report.clean
    ledger.assert_no_floats()


@pytest.mark.parametrize("shuffle_seed", [0, 1, 2, 3])
def test_interleavings_conserve_cash_and_shares(shuffle_seed):
    trades, ledger, oc, op = generate_universe(1_000, seed=19)
    total_cash_before = sum(ledger.cash.values())
    total_shares_before = sum(ledger.positions.values())
    rng = random.Random(shuffle_seed)
    rng.shuffle(trades)
    SettlementEngine(ledger).run(trades)
    assert sum(ledger.cash.values()) == total_cash_before
    assert sum(ledger.positions.values()) == total_shares_before


def test_stepwise_interleaved_lifecycles_reconcile():
    # Advance trades through lifecycle stages in interleaved random order,
    # not batch by batch, and prove recon still holds.
    trades, ledger, oc, op = generate_universe(300, seed=23)
    engine = SettlementEngine(ledger)
    rng = random.Random(99)
    ops = []
    for t in trades:
        ops.extend([(t, "capture"), (t, "match"), (t, "affirm"), (t, "settle")])
    # Shuffle while preserving per-trade op order.
    rng.shuffle(ops)
    done = {t.trade_id: 0 for t in trades}
    order = {"capture": 0, "match": 1, "affirm": 2, "settle": 3}
    pending_ops = ops
    while pending_ops:
        rest = []
        for trade, action in pending_ops:
            if order[action] != done[trade.trade_id]:
                rest.append((trade, action))
                continue
            getattr(engine, action)(trade)
            done[trade.trade_id] += 1
        pending_ops = rest
    # One retry pass for anything that failed on ordering.
    for t in trades:
        if t.state is TradeState.FAILED:
            engine.retry(t)
    report = reconcile(trades, ledger, oc, op)
    assert report.clean


def test_end_to_end_determinism_same_seed_same_balances():
    def run(seed):
        trades, ledger, oc, op = generate_universe(2_000, seed=seed)
        SettlementEngine(ledger).run(trades)
        states = tuple(t.state.value for t in trades)
        return states, dict(ledger.cash), dict(ledger.positions)

    s1, c1, p1 = run(42)
    s2, c2, p2 = run(42)
    assert s1 == s2
    assert c1 == c2
    assert p1 == p2


def test_determinism_breaks_across_seeds():
    def run(seed):
        trades, ledger, _, _ = generate_universe(2_000, seed=seed)
        SettlementEngine(ledger).run(trades)
        return dict(ledger.cash)

    assert run(42) != run(43)


def test_no_floats_after_large_run():
    trades, ledger, oc, op = generate_universe(5_000, seed=29)
    SettlementEngine(ledger).run(trades)
    assert ledger.assert_no_floats() is True
    for balance in ledger.cash.values():
        assert type(balance) is int
    for qty in ledger.positions.values():
        assert type(qty) is int
