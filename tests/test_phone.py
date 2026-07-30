"""Iranian mobile normalization rules."""
from __future__ import annotations

import pytest

from app.utils.phone import (
    InvalidPhoneNumberError,
    mask_phone,
    normalize_iranian_mobile,
)

E164 = "+989121234567"


@pytest.mark.parametrize(
    "raw",
    [
        "09121234567",       # national, leading zero
        "9121234567",        # national, bare
        "989121234567",      # international without «+»
        "+989121234567",     # already canonical
        "0098 912 123 4567", # ITU access code + spaces
        "0912-123-4567",     # dashes
        "۰۹۱۲۱۲۳۴۵۶۷",       # Persian digits
        "٠٩١٢١٢٣٤٥٦٧",       # Arabic-Indic digits
        "  09121234567  ",   # surrounding whitespace
    ],
)
def test_accepted_forms_all_normalize_to_e164(raw):
    assert normalize_iranian_mobile(raw) == E164


@pytest.mark.parametrize(
    "raw",
    [
        "+12025550123",   # US number
        "+442071838750",  # UK number
        "02112345678",    # Iranian landline (Tehran)
        "۰۲۱۸۸۷۷۶۶۵۵",    # Iranian landline, Persian digits
        "0912123",        # too short
        "091212345678901",  # too long
        "hello",          # free text
        "",               # empty
        "   ",            # whitespace only
    ],
)
def test_rejected_forms_raise(raw):
    with pytest.raises(InvalidPhoneNumberError):
        normalize_iranian_mobile(raw)


def test_normalization_is_idempotent():
    assert normalize_iranian_mobile(normalize_iranian_mobile("09121234567")) == E164


def test_mask_keeps_only_the_edges():
    masked = mask_phone(E164)
    assert masked == "+98912****567"
    assert "1234" not in masked


def test_mask_handles_missing_value():
    assert mask_phone(None) == "-"
