"""Capture -> validate -> match -> affirm -> settle pipeline with retries.

Settlement is delivery versus payment: the cash entry and the share
entry for a trade post together or not at all. A trade that cannot
settle (buyer short of cash, seller short of shares) moves to failed
with a reason, and the engine retries failed trades in later passes,
because an earlier failure can be cured by someone else's settlement
freeing up cash or shares.
"""

from typing import List

from .models import FailReason, Trade, TradeState
from .money import check_cents, check_quantity
from .state_machine import transition


class ValidationError(ValueError):
    """Trade rejected at capture."""


class SettlementEngine:
    def __init__(self, ledger):
        self.ledger = ledger
        self.captured: List[Trade] = []

    # -- capture ---------------------------------------------------------
    def capture(self, trade):
        if trade.state is not TradeState.PENDING:
            raise ValidationError(
                "trade %s captured in state %s" % (trade.trade_id, trade.state.value)
            )
        check_quantity(trade.quantity, "quantity")
        check_cents(trade.price_cents, "price_cents")
        if trade.quantity <= 0:
            raise ValidationError("trade %s: non-positive quantity" % trade.trade_id)
        if trade.price_cents <= 0:
            raise ValidationError("trade %s: non-positive price" % trade.trade_id)
        if trade.buyer == trade.seller:
            raise ValidationError("trade %s: buyer equals seller" % trade.trade_id)
        self.captured.append(trade)
        return trade

    # -- lifecycle -------------------------------------------------------
    def match(self, trade):
        return transition(trade, TradeState.MATCHED)

    def affirm(self, trade):
        return transition(trade, TradeState.AFFIRMED)

    def settle(self, trade):
        """Attempt DvP settlement of an affirmed trade.

        Returns True if the trade settled, False if it moved to failed.
        """
        if trade.state is not TradeState.AFFIRMED:
            # Let the state machine raise a consistent error.
            transition(trade, TradeState.SETTLED)
        gross = trade.gross_cents
        if self.ledger.cash_balance(trade.buyer) < gross:
            trade.fail_reason = FailReason.INSUFFICIENT_CASH
            transition(trade, TradeState.FAILED)
            return False
        if self.ledger.position(trade.seller, trade.security) < trade.quantity:
            trade.fail_reason = FailReason.INSUFFICIENT_SHARES
            transition(trade, TradeState.FAILED)
            return False
        self.ledger.post_cash(
            trade.trade_id,
            [(trade.buyer, -gross), (trade.seller, gross)],
        )
        self.ledger.post_position(
            trade.trade_id,
            trade.security,
            [(trade.seller, -trade.quantity), (trade.buyer, trade.quantity)],
        )
        trade.fail_reason = None
        transition(trade, TradeState.SETTLED)
        return True

    def retry(self, trade):
        """Re-affirm a failed trade and attempt settlement again."""
        transition(trade, TradeState.AFFIRMED)
        trade.attempts += 1
        return self.settle(trade)

    # -- batch driver ----------------------------------------------------
    def run(self, trades, max_retry_passes=3):
        """Run the full pipeline over a list of pending trades.

        Returns (settled, failed) lists after retry passes.
        """
        for trade in trades:
            self.capture(trade)
            self.match(trade)
            self.affirm(trade)
            self.settle(trade)
        failed = [t for t in trades if t.state is TradeState.FAILED]
        for _ in range(max_retry_passes):
            if not failed:
                break
            still_failed = []
            for trade in failed:
                if not self.retry(trade):
                    still_failed.append(trade)
            if len(still_failed) == len(failed):
                break  # no progress, stop retrying
            failed = still_failed
        settled = [t for t in trades if t.state is TradeState.SETTLED]
        failed = [t for t in trades if t.state is TradeState.FAILED]
        return settled, failed
