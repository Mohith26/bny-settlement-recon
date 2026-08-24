"""Trade model and lifecycle states."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .money import check_cents, check_quantity


class TradeState(Enum):
    PENDING = "pending"
    MATCHED = "matched"
    AFFIRMED = "affirmed"
    SETTLED = "settled"
    FAILED = "failed"


class FailReason(Enum):
    INSUFFICIENT_CASH = "insufficient_cash"
    INSUFFICIENT_SHARES = "insufficient_shares"


@dataclass
class Trade:
    """A single equity trade between two custody accounts.

    price_cents is per share, in integer cents. gross_cents is the DvP
    cash amount: quantity * price_cents. No fees or accrued interest in v1.
    """

    trade_id: str
    buyer: str
    seller: str
    security: str
    quantity: int
    price_cents: int
    trade_date: int = 0
    state: TradeState = TradeState.PENDING
    fail_reason: Optional[FailReason] = None
    attempts: int = 0

    def __post_init__(self):
        check_quantity(self.quantity, "quantity")
        check_cents(self.price_cents, "price_cents")

    @property
    def gross_cents(self):
        return self.quantity * self.price_cents
