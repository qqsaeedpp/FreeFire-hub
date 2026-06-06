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
        now = datetime.utcnow()
        if entry is None or not entry.is_active:
            raise DiscountError("کد تخفیف نامعتبر است.")
        if entry.starts_at is not None and entry.starts_at > now:
            raise DiscountError("این کد تخفیف هنوز فعال نشده است.")
        if entry.expires_at is not None and entry.expires_at < now:
            raise DiscountError("این کد تخفیف منقضی شده است.")
        if entry.max_uses and entry.used_count >= entry.max_uses:
            raise DiscountError("ظرفیت استفاده از این کد به پایان رسیده است.")
        return entry

    async def redeem(self, entry: DiscountCode) -> None:
        entry.used_count += 1

    async def list_codes(self, *, limit: int = 20) -> list[DiscountCode]:
        return await self.codes.list_all(limit=limit)

    async def get_code(self, code_id: int) -> DiscountCode | None:
        return await self.codes.get(code_id)

    async def delete_code(self, entry: DiscountCode) -> None:
        await self.codes.delete(entry)

    async def set_percent(self, entry: DiscountCode, percent: int) -> None:
        entry.percent = percent

    async def set_max_uses(self, entry: DiscountCode, max_uses: int) -> None:
        entry.max_uses = max_uses

    async def set_start_in_days(self, entry: DiscountCode, days: int) -> None:
        """Set the activation date ``days`` from now (0 → active immediately)."""
        entry.starts_at = None if days <= 0 else datetime.utcnow() + timedelta(days=days)

    async def set_expiry_in_days(self, entry: DiscountCode, days: int) -> None:
        """Set the expiry ``days`` from now (0 → no expiry)."""
        entry.expires_at = None if days <= 0 else datetime.utcnow() + timedelta(days=days)

    async def toggle_active(self, entry: DiscountCode) -> bool:
        entry.is_active = not entry.is_active
        return entry.is_active

    @staticmethod
    def apply(amount: int, percent: int) -> int:
        """Return ``amount`` reduced by ``percent`` (rounded down to a Toman)."""
        return amount - (amount * percent) // 100
