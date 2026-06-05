from app.utils.validators import is_valid_email, is_valid_uid, parse_price


def test_valid_uid():
    assert is_valid_uid("123456")
    assert is_valid_uid("123456789012")
    assert not is_valid_uid("123")          # too short
    assert not is_valid_uid("12345678901234")  # too long
    assert not is_valid_uid("abc123")


def test_valid_email():
    assert is_valid_email("user@example.com")
    assert not is_valid_email("not-an-email")
    assert not is_valid_email("a@b")


def test_parse_price():
    assert parse_price("100,000") == 100000
    assert parse_price("۲۵۰۰۰") == 25000  # Persian digits
    assert parse_price("50 000") == 50000
    assert parse_price("abc") is None
