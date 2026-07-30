"""Iranian mobile-number normalization.

One place owns the phone rules so no handler re-implements them. Input arrives
from a Telegram ``Contact`` (whose ``phone_number`` may or may not carry a «+»,
and which users occasionally see rendered with Persian digits), so the parser
accepts every common shape and emits exactly one canonical form: **E.164**.

Note: a ``+98`` number proves the line was issued by an Iranian carrier — it is
not proof of nationality or residency.
"""
from __future__ import annotations

import phonenumbers

# Persian (U+06F0-U+06F9) and Arabic-Indic (U+0660-U+0669) digits → ASCII.
_DIGIT_MAP = {ord("۰") + i: str(i) for i in range(10)}
_DIGIT_MAP.update({ord("٠") + i: str(i) for i in range(10)})

# Separators people paste along with a number; all are meaningless to E.164.
_STRIP = str.maketrans("", "", " \t\r\n ‌‏‪‬-()./\\")

_IR_REGION = "IR"
_IR_COUNTRY_CODE = 98


class InvalidPhoneNumberError(ValueError):
    """Raised when a value is not a valid Iranian mobile number.

    A dedicated type so callers can map it to a user-facing Persian message
    without catching (and accidentally swallowing) unrelated ``ValueError``s.
    """


def _prepare(raw: str) -> str:
    """Fold digits/separators and make the international prefix explicit.

    ``phonenumbers`` cannot tell whether a bare ``989121234567`` is an
    international number or a (nonsense) national one, so the ``98``-prefixed
    12-digit form is promoted to ``+98…`` before parsing. ``00`` is the ITU
    international access code and becomes ``+``.
    """
    value = str(raw or "").strip().translate(_DIGIT_MAP).translate(_STRIP)
    if value.startswith("00"):
        return "+" + value[2:]
    if not value.startswith("+") and value.startswith("98") and len(value) == 12:
        return "+" + value
    return value


def normalize_iranian_mobile(raw: str) -> str:
    """Return *raw* as an E.164 Iranian mobile number (``+989121234567``).

    Accepts ``09121234567``, ``9121234567``, ``989121234567``, ``+989121234567``
    and their Persian/Arabic-digit or separator-laden variants.

    Raises :class:`InvalidPhoneNumberError` for anything that is not a *valid*
    *mobile* line in region ``IR`` — landlines, VoIP, foreign numbers, truncated
    numbers and free text all fail here rather than deeper in the flow.
    """
    prepared = _prepare(raw)
    if not prepared:
        raise InvalidPhoneNumberError("empty phone number")

    try:
        parsed = phonenumbers.parse(prepared, _IR_REGION)
    except phonenumbers.NumberParseException as exc:
        raise InvalidPhoneNumberError("unparsable phone number") from exc

    if not phonenumbers.is_valid_number(parsed):
        raise InvalidPhoneNumberError("not a valid phone number")
    if parsed.country_code != _IR_COUNTRY_CODE:
        raise InvalidPhoneNumberError("not an Iranian country code")
    if phonenumbers.region_code_for_number(parsed) != _IR_REGION:
        raise InvalidPhoneNumberError("not an Iranian region")
    if phonenumbers.number_type(parsed) is not phonenumbers.PhoneNumberType.MOBILE:
        raise InvalidPhoneNumberError("not a mobile line")

    return phonenumbers.format_number(
        parsed, phonenumbers.PhoneNumberFormat.E164
    )


def mask_phone(phone: str | None) -> str:
    """Partially redact a number for logs/notifications (``+98912****567``).

    Full numbers are personal data and must never reach the structured log, the
    admin channel or a referrer's notification; this keeps just enough digits to
    correlate a report with a support ticket.
    """
    value = str(phone or "").strip()
    if not value:
        return "-"
    if len(value) <= 8:
        return value[:2] + "*" * max(0, len(value) - 2)
    return f"{value[:6]}****{value[-3:]}"
