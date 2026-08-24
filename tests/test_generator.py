import pytest

from settlecore.engine import SettlementEngine
from settlecore.generator import (
    BREAK_DUPLICATE_POSTING,
    BREAK_MISSED_SETTLE,
    BREAK_WRONG_AMOUNT,
    generate_universe,
    inject_breaks,
)
from settlecore.models import TradeState


def test_generator_is_deterministic_per_seed():
    t1, _, c1, p1 = generate_universe(500, seed=7)
    t2, _, c2, p2 = generate_universe(500, seed=7)
    assert [
        (t.trade_id, t.buyer, t.seller, t.security, t.quantity, t.price_cents)
        for t in t1
    ] == [
        (t.trade_id, t.buyer, t.seller, t.security, t.quantity, t.price_cents)
        for t in t2
    ]
    assert c1 == c2 and p1 == p2


def test_different_seeds_differ():
    t1, _, _, _ = generate_universe(500, seed=7)
    t2, _, _, _ = generate_universe(500, seed=8)
    assert [(t.buyer, t.quantity, t.price_cents) for t in t1] != [
        (t.buyer, t.quantity, t.price_cents) for t in t2
    ]


def test_generated_trades_are_valid():
    trades, _, _, _ = generate_universe(1_000, seed=1)
    assert len(trades) == 1_000
    assert len({t.trade_id for t in trades}) == 1_000
    for t in trades:
        assert t.quantity > 0
        assert t.price_cents > 0
        assert t.buyer != t.seller
        assert t.state is TradeState.PENDING


def _settled_universe(n=2_000, seed=3):
    trades, ledger, oc, op = generate_universe(n, seed)
    engine = SettlementEngine(ledger)
    settled, failed = engine.run(trades)
    return trades, ledger, oc, op, settled


def test_inject_breaks_returns_exact_labels():
    _, ledger, _, _, settled = _settled_universe()
    labels = inject_breaks(
        ledger, settled, seed=99, n_missed_settle=3, n_wrong_amount=4,
        n_duplicate_posting=5,
    )
    assert len(labels) == 12
    kinds = [k for _, k in labels]
    assert kinds.count(BREAK_MISSED_SETTLE) == 3
    assert kinds.count(BREAK_WRONG_AMOUNT) == 4
    assert kinds.count(BREAK_DUPLICATE_POSTING) == 5
    # distinct victims
    assert len({tid for tid, _ in labels}) == 12


def test_inject_breaks_rejects_too_many():
    _, ledger, _, _, settled = _settled_universe(n=10, seed=3)
    with pytest.raises(ValueError):
        inject_breaks(ledger, settled, seed=1, n_missed_settle=len(settled) + 1)


def test_missed_settle_removes_postings():
    _, ledger, _, _, settled = _settled_universe()
    labels = inject_breaks(ledger, settled, seed=5, n_missed_settle=1)
    tid = labels[0][0]
    assert all(e.trade_id != tid for e in ledger.cash_journal)
    assert all(e.trade_id != tid for e in ledger.position_journal)


def test_duplicate_posting_doubles_entries():
    _, ledger, _, _, settled = _settled_universe()
    labels = inject_breaks(ledger, settled, seed=5, n_duplicate_posting=1)
    tid = labels[0][0]
    assert sum(1 for e in ledger.cash_journal if e.trade_id == tid) == 2
    assert sum(1 for e in ledger.position_journal if e.trade_id == tid) == 2


def test_wrong_amount_changes_cents_but_stays_balanced():
    trades, ledger, _, _, settled = _settled_universe()
    labels = inject_breaks(ledger, settled, seed=5, n_wrong_amount=1)
    tid = labels[0][0]
    trade = next(t for t in trades if t.trade_id == tid)
    entry = next(e for e in ledger.cash_journal if e.trade_id == tid)
    legs = dict(entry.legs)
    assert legs[trade.buyer] != -trade.gross_cents
    assert sum(legs.values()) == 0  # still double-entry balanced
