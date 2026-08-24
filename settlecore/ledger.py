"""Double-entry cash ledger and share position ledger.

Cash moves as journal entries with two or more legs that must sum to
zero, all in integer cents. Positions move the same way in whole shares.
Every posting is tagged with the trade_id that caused it, which is what
lets the reconciliation engine line postings up against the trade log.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from .money import MoneyTypeError, check_cents, check_quantity


class UnbalancedEntryError(ValueError):
    """A journal entry whose legs do not net to zero."""


@dataclass
class CashEntry:
    entry_id: int
    trade_id: str
    legs: Tuple[Tuple[str, int], ...]  # (account, delta_cents)


@dataclass
class PositionEntry:
    entry_id: int
    trade_id: str
    security: str
    legs: Tuple[Tuple[str, int], ...]  # (account, delta_shares)


class Ledger:
    def __init__(self):
        self.cash: Dict[str, int] = {}
        self.positions: Dict[Tuple[str, str], int] = {}
        self.cash_journal: List[CashEntry] = []
        self.position_journal: List[PositionEntry] = []
        self._next_entry_id = 1

    # -- setup -----------------------------------------------------------
    def open_account(self, account, opening_cash_cents=0):
        check_cents(opening_cash_cents, "opening_cash_cents")
        self.cash[account] = self.cash.get(account, 0) + opening_cash_cents

    def open_position(self, account, security, shares=0):
        check_quantity(shares, "shares")
        key = (account, security)
        self.positions[key] = self.positions.get(key, 0) + shares

    # -- balances --------------------------------------------------------
    def cash_balance(self, account):
        return self.cash.get(account, 0)

    def position(self, account, security):
        return self.positions.get((account, security), 0)

    # -- postings --------------------------------------------------------
    def post_cash(self, trade_id, legs):
        """Post a balanced multi-leg cash entry. legs: [(account, delta_cents)]."""
        clean = []
        total = 0
        for account, delta in legs:
            check_cents(delta, "cash leg for %s" % account)
            clean.append((account, delta))
            total += delta
        if total != 0:
            raise UnbalancedEntryError(
                "cash entry for trade %s nets to %d cents, expected 0"
                % (trade_id, total)
            )
        entry = CashEntry(self._next_entry_id, trade_id, tuple(clean))
        self._next_entry_id += 1
        for account, delta in clean:
            self.cash[account] = self.cash.get(account, 0) + delta
        self.cash_journal.append(entry)
        return entry

    def post_position(self, trade_id, security, legs):
        """Post a balanced share movement. legs: [(account, delta_shares)]."""
        clean = []
        total = 0
        for account, delta in legs:
            check_quantity(delta, "position leg for %s" % account)
            clean.append((account, delta))
            total += delta
        if total != 0:
            raise UnbalancedEntryError(
                "position entry for trade %s nets to %d shares, expected 0"
                % (trade_id, total)
            )
        entry = PositionEntry(self._next_entry_id, trade_id, security, tuple(clean))
        self._next_entry_id += 1
        for account, delta in clean:
            key = (account, security)
            self.positions[key] = self.positions.get(key, 0) + delta
        self.position_journal.append(entry)
        return entry

    # -- integrity -------------------------------------------------------
    def assert_no_floats(self):
        """Walk every balance and journal leg and verify plain ints."""
        for account, bal in self.cash.items():
            check_cents(bal, "cash balance of %s" % account)
        for key, qty in self.positions.items():
            check_quantity(qty, "position %s" % (key,))
        for entry in self.cash_journal:
            for account, delta in entry.legs:
                check_cents(delta, "journal leg %s" % account)
        for entry in self.position_journal:
            for account, delta in entry.legs:
                check_quantity(delta, "journal leg %s" % account)
        return True
