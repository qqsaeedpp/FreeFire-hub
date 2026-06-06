"""Discount-code service — creation, validation and redemption.

Discount codes apply to diamond purchases only (enforced by the call sites).
"""
from __future__ import annotations

from datetime import datetime, timedelta

from app.models.discount import DiscountCode
from app.repositories.discounts import DiscountCodeRepository


class DiscountError(Exception):
    """Raised with a user-facing Persian reason when a code can't be applied."""


class DiscountService:
    def __init__(self, codes: DiscountCodeRepository) -> None:
        self.codes = codes

    async def create_code(
        self,
        code: str,
        percent: int,
        *,
        max_uses: int = 0,
        valid_days: int | None = None,
    ) -> DiscountCode:
        expires_at = (
            datetime.utcnow() + timedelta(days=valid_days) if valid_days else None
        )
        return await self.codes.add(
            DiscountCode(
                code=code,
                percent=percent,
                max_uses=max_uses,
                expires_at=expires_at,
            )
        )

    async def validate(self, code: str) -> DiscountCode:
        """Return the code if usable, else raise :class:`DiscountError`."""
        entry = await self.codes.get_by_code(code.strip())
        if entry is None or not entry.is_active:
            raise DiscountError("کد تخفیف نامعتبر است.")
        if entry.expires_at is not None and entry.expires_at < datetime.utcnow():
            raise DiscountError("این کد تخفیف منقضی شده است.")
        if entry.max_uses and entry.used_count >= entry.max_uses:
            raise DiscountError("ظرفیت استفاده از این کد به پایان رسیده است.")
        return entry

    async def redeem(self, entry: DiscountCode) -> None:
        entry.used_count += 1

    async def list_codes(self, *, limit: int = 20) -> list[DiscountCode]:
        return await self.codes.list_all(limit=limit)

    @staticmethod
    def apply(amount: int, percent: int) -> int:
        """Return ``amount`` reduced by ``percent`` (rounded down to a Toman)."""
        return amount - (amount * percent) // 100
