"""Small reusable helpers."""
from __future__ import annotations

import secrets
import string


def generate_referral_code(length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


async def unique_referral_code(users_repo, length: int = 8) -> str:
    """Generate a referral code guaranteed unique against the users repository."""
    while True:
        code = generate_referral_code(length)
        if not await users_repo.get_by_referral_code(code):
            return code


def format_toman(amount: int) -> str:
    """Render an integer amount with thousands separators + Toman suffix."""
    return f"{amount:,} تومان"


def paginate_meta(total: int, page: int, page_size: int) -> tuple[int, int]:
    """Return (offset, total_pages) for 1-based page numbers."""
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = max(1, min(page, total_pages))
    return (page - 1) * page_size, total_pages
