"""Settlement lifecycle state machine with hard transition enforcement.

The only legal moves are:

    pending  -> matched
    matched  -> affirmed
    affirmed -> settled
    affirmed -> failed
    failed   -> affirmed   (retry path)

Anything else raises IllegalTransitionError. There are 25 ordered state
pairs and the test suite walks the whole matrix.
"""

from .models import TradeState

ALLOWED_TRANSITIONS = frozenset(
    {
        (TradeState.PENDING, TradeState.MATCHED),
        (TradeState.MATCHED, TradeState.AFFIRMED),
        (TradeState.AFFIRMED, TradeState.SETTLED),
        (TradeState.AFFIRMED, TradeState.FAILED),
        (TradeState.FAILED, TradeState.AFFIRMED),
    }
)


class IllegalTransitionError(RuntimeError):
    def __init__(self, trade_id, current, target):
        self.trade_id = trade_id
        self.current = current
        self.target = target
        super().__init__(
            "trade %s: illegal transition %s -> %s"
            % (trade_id, current.value, target.value)
        )


def can_transition(current, target):
    return (current, target) in ALLOWED_TRANSITIONS


def transition(trade, target):
    """Move trade to target state or raise IllegalTransitionError."""
    if not can_transition(trade.state, target):
        raise IllegalTransitionError(trade.trade_id, trade.state, target)
    trade.state = target
    return trade
