"""Wallet & transaction repository."""
from __future__ import annotations

from sqlalchemy import select

from app.models.wallet import Wallet, WalletTransaction
from app.repositories.base import BaseRepository


class WalletRepository(BaseRepository[Wallet]):
    model = Wallet

    async def get_by_user_id(self, user_id: int) -> Wallet | None:
        result = await self.session.execute(
            select(Wallet).where(Wallet.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def add_transaction(self, tx: WalletTransaction) -> WalletTransaction:
        self.session.add(tx)
        await self.session.flush()
        return tx

    async def list_transactions(
        self, wallet_id: int, *, offset: int = 0, limit: int = 10
    ) -> list[WalletTransaction]:
        result = await self.session.execute(
            select(WalletTransaction)
            .where(WalletTransaction.wallet_id == wallet_id)
            .order_by(WalletTransaction.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())
