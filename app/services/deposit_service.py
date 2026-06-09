"""Deposit (بیعانه) settings service.

Provides the admin-managed deposit amount + destination card for each flow. On
first access a row is lazily seeded from the ``.env`` defaults (used only as a
one-time seed — the live values then live in the DB, nothing stays hardcoded).
"""
from __future__ import annotations

from app.core.config import settings
from app.core.constants import DepositType
from app.models.deposit_setting import DepositSetting
from app.repositories.deposit_settings import DepositSettingRepository


# One-time seed defaults per deposit type, sourced from env (not hardcoded logic).
def _seed_defaults(deposit_type: DepositType) -> tuple[int, str, str]:
    if deposit_type is DepositType.ACCOUNT_REQUEST:
        return (
            settings.requested_account_deposit,
            settings.card_number,
            settings.card_holder,
        )
    # ACCOUNT_PURCHASE: no preset amount; card seeded from the env default.
    return (0, settings.card_number, settings.card_holder)


class DepositService:
    def __init__(self, repo: DepositSettingRepository) -> None:
        self.repo = repo

    async def get_or_seed(self, deposit_type: DepositType) -> DepositSetting:
        """Return the setting for ``deposit_type``, creating a seeded row if absent."""
        existing = await self.repo.get_by_type(deposit_type)
        if existing is not None:
            return existing
        amount, card_number, card_holder = _seed_defaults(deposit_type)
        row = DepositSetting(
            deposit_type=deposit_type,
            amount=amount,
            card_number=card_number,
            card_holder=card_holder,
        )
        return await self.repo.add(row)

    async def set_amount(self, deposit_type: DepositType, amount: int) -> DepositSetting:
        row = await self.get_or_seed(deposit_type)
        row.amount = amount
        await self.repo.session.flush()
        return row

    async def set_card_number(
        self, deposit_type: DepositType, card_number: str
    ) -> DepositSetting:
        row = await self.get_or_seed(deposit_type)
        row.card_number = card_number
        await self.repo.session.flush()
        return row

    async def set_card_holder(
        self, deposit_type: DepositType, card_holder: str
    ) -> DepositSetting:
        row = await self.get_or_seed(deposit_type)
        row.card_holder = card_holder
        await self.repo.session.flush()
        return row
