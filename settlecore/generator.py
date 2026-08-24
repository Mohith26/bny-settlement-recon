"""Seeded synthetic trade generation and labelled break injection.

The generator is deterministic for a given seed: same seed, same trades,
same account seeding, byte for byte. Break injection corrupts the LIVE
ledger only, never the trade log, and returns exact labels so a recon
run can be graded against ground truth.
"""

import random
from typing import Dict, List, Tuple

from .ledger import Ledger
from .models import Trade

SECURITIES = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH", "III", "JJJ"]

BREAK_MISSED_SETTLE = "missed_settle"
BREAK_WRONG_AMOUNT = "wrong_amount"
BREAK_DUPLICATE_POSTING = "duplicate_posting"


def generate_universe(
    n_trades,
    seed,
    n_accounts=20,
    n_securities=10,
    opening_cash_cents=5_000_000_00,
    opening_shares=50_000,
):
    """Build (trades, ledger, opening_cash, opening_positions).

    Accounts are opened with enough cash and inventory that the large
    majority of trades settle on the first pass; the rest exercise the
    failed/retry path naturally.
    """
    rng = random.Random(seed)
    accounts = ["ACCT-%03d" % i for i in range(n_accounts)]
    securities = SECURITIES[:n_securities]

    ledger = Ledger()
    opening_cash: Dict[str, int] = {}
    opening_positions: Dict[Tuple[str, str], int] = {}
    for account in accounts:
        ledger.open_account(account, opening_cash_cents)
        opening_cash[account] = opening_cash_cents
        for security in securities:
            ledger.open_position(account, security, opening_shares)
            opening_positions[(account, security)] = opening_shares

    trades: List[Trade] = []
    for i in range(n_trades):
        buyer, seller = rng.sample(accounts, 2)
        security = rng.choice(securities)
        quantity = rng.randint(1, 500)
        price_cents = rng.randint(1_00, 500_00)  # $1.00 to $500.00 per share
        trades.append(
            Trade(
                trade_id="T-%07d" % i,
                buyer=buyer,
                seller=seller,
                security=security,
                quantity=quantity,
                price_cents=price_cents,
                trade_date=rng.randint(0, 20),
            )
        )
    return trades, ledger, opening_cash, opening_positions


def inject_breaks(
    ledger,
    settled_trades,
    seed,
    n_missed_settle=0,
    n_wrong_amount=0,
    n_duplicate_posting=0,
):
    """Corrupt the live ledger for distinct settled trades, return labels.

    missed_settle: the trade log says settled but the ledger never moved.
    wrong_amount: cash moved for the trade but by the wrong number of cents
        (still double-entry balanced, which is exactly why balance-level
        checks alone would miss the classification).
    duplicate_posting: the trade's cash and share entries were applied twice.
    """
    rng = random.Random(seed)
    total = n_missed_settle + n_wrong_amount + n_duplicate_posting
    if total > len(settled_trades):
        raise ValueError("not enough settled trades to inject %d breaks" % total)
    victims = rng.sample(settled_trades, total)
    labels = []
    idx = 0

    cash_by_trade = {}
    for entry in ledger.cash_journal:
        cash_by_trade.setdefault(entry.trade_id, []).append(entry)
    pos_by_trade = {}
    for entry in ledger.position_journal:
        pos_by_trade.setdefault(entry.trade_id, []).append(entry)

    for _ in range(n_missed_settle):
        trade = victims[idx]
        idx += 1
        for entry in cash_by_trade.pop(trade.trade_id, []):
            ledger.cash_journal.remove(entry)
            for account, delta in entry.legs:
                ledger.cash[account] -= delta
        for entry in pos_by_trade.pop(trade.trade_id, []):
            ledger.position_journal.remove(entry)
            for account, delta in entry.legs:
                ledger.positions[(account, entry.security)] -= delta
        labels.append((trade.trade_id, BREAK_MISSED_SETTLE))

    for _ in range(n_wrong_amount):
        trade = victims[idx]
        idx += 1
        entry = cash_by_trade[trade.trade_id][0]
        skew = rng.randint(1, 9_999)  # off by 1 cent to $99.99
        if rng.random() < 0.5:
            skew = -min(skew, trade.gross_cents - 1)
        new_legs = []
        for account, delta in entry.legs:
            if delta < 0:
                new_delta = delta - skew
            else:
                new_delta = delta + skew
            ledger.cash[account] += new_delta - delta
            new_legs.append((account, new_delta))
        entry.legs = tuple(new_legs)
        labels.append((trade.trade_id, BREAK_WRONG_AMOUNT))

    for _ in range(n_duplicate_posting):
        trade = victims[idx]
        idx += 1
        for entry in list(cash_by_trade[trade.trade_id]):
            dup = ledger.post_cash(entry.trade_id, list(entry.legs))
            cash_by_trade[trade.trade_id].append(dup)
        for entry in list(pos_by_trade[trade.trade_id]):
            ledger.post_position(entry.trade_id, entry.security, list(entry.legs))
        labels.append((trade.trade_id, BREAK_DUPLICATE_POSTING))

    return labels
