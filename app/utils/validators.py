"""Input validators for user-supplied data."""
from __future__ import annotations

import re

_UID_RE = re.compile(r"^\d{6,12}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_uid(value: str) -> bool:
    """Free Fire UID — numeric, 6 to 12 digits."""
    return bool(_UID_RE.match(value.strip()))


def is_valid_email(value: str) -> bool:
    return bool(_EMAIL_RE.match(value.strip()))


def parse_price(value: str) -> int | None:
    """Parse a price string (allows separators / Persian digits) into int Toman."""
    translation = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
    cleaned = value.translate(translation)
    cleaned = re.sub(r"[,\s_]", "", cleaned)
    if not cleaned.isdigit():
        return None
    return int(cleaned)
