import pytest

from settlecore.engine import SettlementEngine
from settlecore.generator import (
    BREAK_DUPLICATE_POSTING,
    BREAK_MISSED_SETTLE,
    BREAK_WRONG_AMOUNT,
    generate_universe,
    inject_breaks,
)
from settlecore.recon import grade_against_labels, reconcile


def run_universe(n=2_000, seed=11):
    trades, ledger, oc, op = generate_universe(n, seed)
    engine = SettlementEngine(ledger)
    settled, failed = engine.run(trades)
    return trades, ledger, oc, op, settled


def test_clean_run_reconciles_to_the_cent():
    trades, ledger, oc, op, settled = run_universe()
    report = reconcile(trades, ledger, oc, op)
    assert report.clean
    assert report.diff_count == 0
    assert report.breaks == []
    assert len(settled) > 0


def test_clean_run_with_failed_trades_still_reconciles():
    # Tight cash so some trades fail permanently; recon must ignore them.
    trades, ledger, oc, op = generate_universe(
        500, seed=13, opening_cash_cents=40_000_00, opening_shares=300
    )
    engine = SettlementEngine(ledger)
    settled, failed = engine.run(trades)
    assert failed, "expected some permanent fails in this tight universe"
    report = reconcile(trades, ledger, oc, op)
    assert report.clean


def test_missed_settle_detected_and_classified():
    trades, ledger, oc, op, settled = run_universe()
    labels = inject_breaks(ledger, settled, seed=21, n_missed_settle=5)
    report = reconcile(trades, ledger, oc, op)
    grade = grade_against_labels(report, labels)
    assert grade["exact_match"]
    assert grade["detected_counts"][BREAK_MISSED_SETTLE] == 5


def test_wrong_amount_detected_and_classified():
    trades, ledger, oc, op, settled = run_universe()
    labels = inject_breaks(ledger, settled, seed=22, n_wrong_amount=5)
    report = reconcile(trades, ledger, oc, op)
    grade = grade_against_labels(report, labels)
    assert grade["exact_match"]
    assert grade["detected_counts"][BREAK_WRONG_AMOUNT] == 5


def test_duplicate_posting_detected_and_classified():
    trades, ledger, oc, op, settled = run_universe()
    labels = inject_breaks(ledger, settled, seed=23, n_duplicate_posting=5)
    report = reconcile(trades, ledger, oc, op)
    grade = grade_against_labels(report, labels)
    assert grade["exact_match"]
    assert grade["detected_counts"][BREAK_DUPLICATE_POSTING] == 5


def test_mixed_breaks_all_classified_exactly():
    trades, ledger, oc, op, settled = run_universe()
    labels = inject_breaks(
        ledger, settled, seed=24, n_missed_settle=7, n_wrong_amount=6,
        n_duplicate_posting=5,
    )
    report = reconcile(trades, ledger, oc, op)
    grade = grade_against_labels(report, labels)
    assert grade["exact_match"]
    assert len(report.breaks) == 18
    assert grade["false_positives"] == []
    assert grade["false_negatives"] == []
    assert grade["detected_counts"] == grade["injected_counts"]


def test_breaks_produce_balance_diffs():
    trades, ledger, oc, op, settled = run_universe()
    inject_breaks(ledger, settled, seed=25, n_missed_settle=1)
    report = reconcile(trades, ledger, oc, op)
    assert not report.clean
    assert report.diff_count > 0


def test_wrong_amount_diff_is_exact_skew():
    trades, ledger, oc, op, settled = run_universe()
    labels = inject_breaks(ledger, settled, seed=26, n_wrong_amount=1)
    tid = labels[0][0]
    trade = next(t for t in trades if t.trade_id == tid)
    entry = next(e for e in ledger.cash_journal if e.trade_id == tid)
    skew = dict(entry.legs)[trade.seller] - trade.gross_cents
    report = reconcile(trades, ledger, oc, op)
    assert report.cash_diffs[trade.seller] == skew
    assert report.cash_diffs[trade.buyer] == -skew


def test_grade_flags_false_positive():
    trades, ledger, oc, op, settled = run_universe(n=200, seed=31)
    labels = inject_breaks(ledger, settled, seed=32, n_missed_settle=2)
    report = reconcile(trades, ledger, oc, op)
    fake_labels = labels[:1]  # pretend only one was injected
    grade = grade_against_labels(report, fake_labels)
    assert not grade["exact_match"]
    assert len(grade["false_positives"]) == 1
