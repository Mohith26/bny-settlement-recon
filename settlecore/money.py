"""Integer-cent money helpers.

Every amount that touches a ledger goes through check_cents. Floats are
rejected outright, including bools (which are ints in Python but never
a sane amount of money).
"""


class MoneyTypeError(TypeError):
    """Raised when a money or quantity value is not a plain int."""


def check_cents(value, label="amount"):
    """Return value if it is a plain int, else raise MoneyTypeError."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise MoneyTypeError(
            "%s must be a plain int of cents, got %r (%s)"
            % (label, value, type(value).__name__)
        )
    return value


def check_quantity(value, label="quantity"):
    """Share quantities follow the same rule: plain ints only."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise MoneyTypeError(
            "%s must be a plain int of shares, got %r (%s)"
            % (label, value, type(value).__name__)
        )
    return value


def cents_to_str(cents):
    """Render integer cents as a dollar string for logs and reports."""
    check_cents(cents)
    sign = "-" if cents < 0 else ""
    mag = abs(cents)
    return "%s%d.%02d" % (sign, mag // 100, mag % 100)
