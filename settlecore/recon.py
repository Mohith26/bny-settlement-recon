"""Reconciliation: independent statement vs live ledgers, to the cent.

The recon engine never trusts the ledger. It rebuilds an expected
statement purely from opening balances plus the trade log (settled
trades only), then does two things:

1. Balance recon: expected cash per account and expected shares per
   account and security versus live ledger balances. Any nonzero
   difference is a diff, reported in cents or shares.

2. Break classification: for every settled trade, line up the journal
   entries tagged with its trade_id against what DvP should have posted.
   No entries: missed_settle. More than one cash entry: duplicate_posting.
   One entry with the wrong cents: wrong_amount.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from .generator import (
    BREAK_DUPLICATE_POSTING,
    BREAK_MISSED_SETTLE,
    BREAK_WRONG_AMOUNT,
)
from .models import TradeState


@dataclass
class ReconReport:
    cash_diffs: Dict[str, int] = field(default_factory=dict)
    position_diffs: Dict[Tuple[str, str], int] = field(default_factory=dict)
    breaks: List[Tuple[str, str]] = field(default_factory=list)

    @property
    def clean(self):
        return not self.cash_diffs and not self.position_diffs and not self.breaks

    @property
    def diff_count(self):
        return len(self.cash_diffs) + len(self.position_diffs)


def reconcile(trades, ledger, opening_cash, opening_positions):
    settled = [t for t in trades if t.state is TradeState.SETTLED]

    # Independent statement from the trade log.
    expected_cash = dict(opening_cash)
    expected_positions = dict(opening_positions)
    for trade in settled:
        gross = trade.gross_cents
        expected_cash[trade.buyer] = expected_cash.get(trade.buyer, 0) - gross
        expected_cash[trade.seller] = expected_cash.get(trade.seller, 0) + gross
        bkey = (trade.buyer, trade.security)
        skey = (trade.seller, trade.security)
        expected_positions[bkey] = expected_positions.get(bkey, 0) + trade.quantity
        expected_positions[skey] = expected_positions.get(skey, 0) - trade.quantity

    report = ReconReport()

    accounts = set(expected_cash) | set(ledger.cash)
    for account in sorted(accounts):
        diff = ledger.cash.get(account, 0) - expected_cash.get(account, 0)
        if diff != 0:
            report.cash_diffs[account] = diff

    keys = set(expected_positions) | set(ledger.positions)
    for key in sorted(keys):
        diff = ledger.positions.get(key, 0) - expected_positions.get(key, 0)
        if diff != 0:
            report.position_diffs[key] = diff

    # Per-trade break classification.
    cash_by_trade = {}
    for entry in ledger.cash_journal:
        cash_by_trade.setdefault(entry.trade_id, []).append(entry)

    for trade in settled:
        entries = cash_by_trade.get(trade.trade_id, [])
        if not entries:
            report.breaks.append((trade.trade_id, BREAK_MISSED_SETTLE))
            continue
        if len(entries) > 1:
            report.breaks.append((trade.trade_id, BREAK_DUPLICATE_POSTING))
            continue
        entry = entries[0]
        legs = dict(entry.legs)
        gross = trade.gross_cents
        if legs.get(trade.buyer) != -gross or legs.get(trade.seller) != gross:
            report.breaks.append((trade.trade_id, BREAK_WRONG_AMOUNT))

    return report


def grade_against_labels(report, labels):
    """Compare detected breaks with injected ground truth.

    Returns a dict with exact match booleans and per-class counts.
    """
    detected = sorted(report.breaks)
    truth = sorted(labels)

    def counts(pairs):
        out = {
            BREAK_MISSED_SETTLE: 0,
            BREAK_WRONG_AMOUNT: 0,
            BREAK_DUPLICATE_POSTING: 0,
        }
        for _, kind in pairs:
            out[kind] += 1
        return out

    return {
        "exact_match": detected == truth,
        "detected_counts": counts(detected),
        "injected_counts": counts(truth),
        "false_positives": [p for p in detected if p not in truth],
        "false_negatives": [p for p in truth if p not in detected],
    }
