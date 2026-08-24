import pytest

from settlecore.engine import SettlementEngine, ValidationError
from settlecore.ledger import Ledger
from settlecore.models import FailReason, Trade, TradeState
from settlecore.state_machine import IllegalTransitionError


def make_engine(cash_a=1_000_00, cash_b=1_000_00, shares_a=100, shares_b=100):
    lg = Ledger()
    lg.open_account("A", cash_a)
    lg.open_account("B", cash_b)
    lg.open_position("A", "AAA", shares_a)
    lg.open_position("B", "AAA", shares_b)
    return SettlementEngine(lg)


def make_trade(buyer="A", seller="B", qty=10, price=5_00, tid="T-1"):
    return Trade(tid, buyer, seller, "AAA", qty, price)


def test_capture_accepts_valid_trade():
    eng = make_engine()
    trade = make_trade()
    assert eng.capture(trade) is trade
    assert trade in eng.captured


def test_capture_rejects_non_positive_quantity():
    eng = make_engine()
    with pytest.raises(ValidationError):
        eng.capture(make_trade(qty=0))


def test_capture_rejects_non_positive_price():
    eng = make_engine()
    with pytest.raises(ValidationError):
        eng.capture(make_trade(price=0))


def test_capture_rejects_self_trade():
    eng = make_engine()
    with pytest.raises(ValidationError):
        eng.capture(make_trade(buyer="A", seller="A"))


def test_capture_rejects_already_started_trade():
    eng = make_engine()
    trade = make_trade()
    trade.state = TradeState.MATCHED
    with pytest.raises(ValidationError):
        eng.capture(trade)


def test_trade_model_rejects_float_price():
    from settlecore.money import MoneyTypeError

    with pytest.raises(MoneyTypeError):
        Trade("T-1", "A", "B", "AAA", 10, 5.00)


def test_dvp_settlement_moves_cash_and_shares_atomically():
    eng = make_engine()
    trade = make_trade(qty=10, price=5_00)  # gross 50.00
    eng.capture(trade)
    eng.match(trade)
    eng.affirm(trade)
    assert eng.settle(trade) is True
    assert trade.state is TradeState.SETTLED
    assert eng.ledger.cash_balance("A") == 1_000_00 - 50_00
    assert eng.ledger.cash_balance("B") == 1_000_00 + 50_00
    assert eng.ledger.position("A", "AAA") == 110
    assert eng.ledger.position("B", "AAA") == 90
    assert len(eng.ledger.cash_journal) == 1
    assert len(eng.ledger.position_journal) == 1


def test_settle_fails_on_insufficient_cash_with_reason():
    eng = make_engine(cash_a=10_00)
    trade = make_trade(qty=10, price=5_00)  # needs 50.00
    eng.capture(trade)
    eng.match(trade)
    eng.affirm(trade)
    assert eng.settle(trade) is False
    assert trade.state is TradeState.FAILED
    assert trade.fail_reason is FailReason.INSUFFICIENT_CASH
    # Nothing moved.
    assert eng.ledger.cash_balance("A") == 10_00
    assert eng.ledger.cash_journal == []
    assert eng.ledger.position_journal == []


def test_settle_fails_on_insufficient_shares_with_reason():
    eng = make_engine(shares_b=5)
    trade = make_trade(qty=10)
    eng.capture(trade)
    eng.match(trade)
    eng.affirm(trade)
    assert eng.settle(trade) is False
    assert trade.fail_reason is FailReason.INSUFFICIENT_SHARES
    assert eng.ledger.position("B", "AAA") == 5


def test_settle_from_wrong_state_raises():
    eng = make_engine()
    trade = make_trade()
    eng.capture(trade)
    with pytest.raises(IllegalTransitionError):
        eng.settle(trade)  # pending, never matched or affirmed


def test_retry_succeeds_after_cash_arrives():
    eng = make_engine(cash_a=10_00)
    trade = make_trade(qty=10, price=5_00)
    eng.capture(trade)
    eng.match(trade)
    eng.affirm(trade)
    assert eng.settle(trade) is False
    # Counterparty wires cash in via another settlement's proceeds.
    eng.ledger.post_cash("FUNDING", [("A", 100_00), ("B", -100_00)])
    assert eng.retry(trade) is True
    assert trade.state is TradeState.SETTLED
    assert trade.attempts == 1
    assert trade.fail_reason is None


def test_run_retry_pass_cures_ordering_failure():
    # A buys before A gets paid; first pass fails, retry pass settles.
    lg = Ledger()
    lg.open_account("A", 0)
    lg.open_account("B", 200_00)
    lg.open_account("C", 0)
    lg.open_position("A", "AAA", 100)
    lg.open_position("B", "AAA", 0)
    lg.open_position("C", "AAA", 100)
    eng = SettlementEngine(lg)
    t1 = Trade("T-1", "A", "C", "AAA", 10, 5_00)  # A needs 50.00, has 0
    t2 = Trade("T-2", "B", "A", "AAA", 20, 5_00)  # pays A 100.00
    settled, failed = eng.run([t1, t2])
    assert {t.trade_id for t in settled} == {"T-1", "T-2"}
    assert failed == []
    assert t1.attempts == 1


def test_run_permanent_failure_stays_failed():
    eng = make_engine(cash_a=1_00)
    trade = make_trade(qty=100, price=5_00)  # needs 500.00 forever
    settled, failed = eng.run([trade])
    assert settled == []
    assert failed == [trade]
    assert trade.state is TradeState.FAILED
    assert trade.fail_reason is FailReason.INSUFFICIENT_CASH


def test_run_full_batch_settles_and_balances():
    eng = make_engine()
    trades = [
        make_trade(tid="T-1", qty=10, price=5_00),
        make_trade(tid="T-2", buyer="B", seller="A", qty=4, price=2_50),
    ]
    settled, failed = eng.run(trades)
    assert len(settled) == 2 and failed == []
    total_cash = sum(eng.ledger.cash.values())
    assert total_cash == 2_000_00  # cash is conserved
    total_shares = sum(eng.ledger.positions.values())
    assert total_shares == 200  # shares are conserved
