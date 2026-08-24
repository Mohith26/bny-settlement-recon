import pytest

from settlecore.money import MoneyTypeError, cents_to_str, check_cents, check_quantity


def test_check_cents_accepts_int():
    assert check_cents(12345) == 12345


def test_check_cents_accepts_negative_and_zero():
    assert check_cents(0) == 0
    assert check_cents(-500) == -500


def test_check_cents_rejects_float():
    with pytest.raises(MoneyTypeError):
        check_cents(123.45)


def test_check_cents_rejects_bool():
    with pytest.raises(MoneyTypeError):
        check_cents(True)


def test_check_cents_rejects_string_and_none():
    with pytest.raises(MoneyTypeError):
        check_cents("100")
    with pytest.raises(MoneyTypeError):
        check_cents(None)


def test_check_quantity_rejects_float():
    with pytest.raises(MoneyTypeError):
        check_quantity(10.0)


def test_cents_to_str_formats():
    assert cents_to_str(0) == "0.00"
    assert cents_to_str(1) == "0.01"
    assert cents_to_str(123456) == "1234.56"
    assert cents_to_str(-205) == "-2.05"


def test_cents_to_str_rejects_float():
    with pytest.raises(MoneyTypeError):
        cents_to_str(1.0)
