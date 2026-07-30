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

    async def get_by_user_id_for_update(self, user_id: int) -> Wallet | None:
        """Read one wallet row under a ``SELECT … FOR UPDATE`` lock.

        Balance mutations must serialize on the row, otherwise two concurrent
        credits both read the same starting balance and one increment is lost.
        The lock is held until the surrounding transaction commits. On SQLite
        (tests) the dialect renders no locking clause and the statement degrades
        to a plain read, which is safe because those sessions are serial.

        ``populate_existing`` is essential: without it SQLAlchemy would return the
        session's already-loaded copy and keep its *stale* balance, so the value
        we increment would predate the lock and the update would still be lost.
        """
        result = await self.session.execute(
            select(Wallet)
            .where(Wallet.user_id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
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
