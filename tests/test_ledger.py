import pytest

from settlecore.ledger import Ledger, UnbalancedEntryError
from settlecore.money import MoneyTypeError


@pytest.fixture
def ledger():
    lg = Ledger()
    lg.open_account("A", 10_000)
    lg.open_account("B", 5_000)
    lg.open_position("A", "AAA", 100)
    lg.open_position("B", "AAA", 50)
    return lg


def test_opening_balances(ledger):
    assert ledger.cash_balance("A") == 10_000
    assert ledger.cash_balance("B") == 5_000
    assert ledger.position("A", "AAA") == 100
    assert ledger.position("B", "AAA") == 50


def test_unknown_account_defaults_to_zero(ledger):
    assert ledger.cash_balance("ZZZ") == 0
    assert ledger.position("ZZZ", "AAA") == 0


def test_balanced_cash_posting_moves_money(ledger):
    ledger.post_cash("T-1", [("A", -3_000), ("B", 3_000)])
    assert ledger.cash_balance("A") == 7_000
    assert ledger.cash_balance("B") == 8_000
    assert len(ledger.cash_journal) == 1
    assert ledger.cash_journal[0].trade_id == "T-1"


def test_unbalanced_cash_posting_rejected(ledger):
    with pytest.raises(UnbalancedEntryError):
        ledger.post_cash("T-1", [("A", -3_000), ("B", 2_999)])
    assert ledger.cash_balance("A") == 10_000
    assert ledger.cash_journal == []


def test_float_cash_leg_rejected(ledger):
    with pytest.raises(MoneyTypeError):
        ledger.post_cash("T-1", [("A", -30.0), ("B", 30)])
    assert ledger.cash_balance("A") == 10_000


def test_balanced_position_posting_moves_shares(ledger):
    ledger.post_position("T-1", "AAA", [("A", -25), ("B", 25)])
    assert ledger.position("A", "AAA") == 75
    assert ledger.position("B", "AAA") == 75


def test_unbalanced_position_posting_rejected(ledger):
    with pytest.raises(UnbalancedEntryError):
        ledger.post_position("T-1", "AAA", [("A", -25), ("B", 24)])
    assert ledger.position("A", "AAA") == 100


def test_float_position_leg_rejected(ledger):
    with pytest.raises(MoneyTypeError):
        ledger.post_position("T-1", "AAA", [("A", -25.5), ("B", 25.5)])


def test_float_opening_cash_rejected():
    lg = Ledger()
    with pytest.raises(MoneyTypeError):
        lg.open_account("A", 100.0)


def test_journal_entry_ids_are_unique_and_increasing(ledger):
    e1 = ledger.post_cash("T-1", [("A", -1), ("B", 1)])
    e2 = ledger.post_position("T-1", "AAA", [("A", -1), ("B", 1)])
    e3 = ledger.post_cash("T-2", [("A", -2), ("B", 2)])
    assert e1.entry_id < e2.entry_id < e3.entry_id


def test_assert_no_floats_passes_on_clean_ledger(ledger):
    ledger.post_cash("T-1", [("A", -1), ("B", 1)])
    assert ledger.assert_no_floats() is True


def test_assert_no_floats_catches_corrupted_balance(ledger):
    ledger.cash["A"] = 10.0  # simulate a bug slipping a float in
    with pytest.raises(MoneyTypeError):
        ledger.assert_no_floats()


def test_multi_leg_cash_entry(ledger):
    ledger.open_account("C", 0)
    ledger.post_cash("T-9", [("A", -100), ("B", 60), ("C", 40)])
    assert ledger.cash_balance("C") == 40
