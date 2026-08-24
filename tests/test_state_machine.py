import itertools

import pytest

from settlecore.models import Trade, TradeState
from settlecore.state_machine import (
    ALLOWED_TRANSITIONS,
    IllegalTransitionError,
    can_transition,
    transition,
)

ALL_STATES = list(TradeState)
ALL_PAIRS = list(itertools.product(ALL_STATES, ALL_STATES))


def make_trade(state):
    t = Trade("T-X", "A", "B", "AAA", 10, 100)
    t.state = state
    return t


def test_transition_matrix_is_exactly_five_legal_moves():
    legal = [p for p in ALL_PAIRS if can_transition(*p)]
    assert len(ALL_PAIRS) == 25
    assert set(legal) == set(ALLOWED_TRANSITIONS)
    assert len(legal) == 5


@pytest.mark.parametrize("current,target", ALL_PAIRS)
def test_every_ordered_state_pair(current, target):
    trade = make_trade(current)
    if (current, target) in ALLOWED_TRANSITIONS:
        transition(trade, target)
        assert trade.state is target
    else:
        with pytest.raises(IllegalTransitionError):
            transition(trade, target)
        assert trade.state is current  # unchanged on rejection


def test_illegal_transition_error_carries_context():
    trade = make_trade(TradeState.SETTLED)
    with pytest.raises(IllegalTransitionError) as exc:
        transition(trade, TradeState.PENDING)
    assert exc.value.trade_id == "T-X"
    assert exc.value.current is TradeState.SETTLED
    assert exc.value.target is TradeState.PENDING
    assert "settled -> pending" in str(exc.value)


def test_settled_is_terminal():
    trade = make_trade(TradeState.SETTLED)
    for target in ALL_STATES:
        with pytest.raises(IllegalTransitionError):
            transition(trade, target)


def test_full_happy_path():
    trade = make_trade(TradeState.PENDING)
    transition(trade, TradeState.MATCHED)
    transition(trade, TradeState.AFFIRMED)
    transition(trade, TradeState.SETTLED)
    assert trade.state is TradeState.SETTLED


def test_fail_and_retry_path():
    trade = make_trade(TradeState.AFFIRMED)
    transition(trade, TradeState.FAILED)
    transition(trade, TradeState.AFFIRMED)
    transition(trade, TradeState.SETTLED)
    assert trade.state is TradeState.SETTLED
