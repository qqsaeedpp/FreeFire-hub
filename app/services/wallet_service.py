"""Wallet service — balance mutations are always recorded as transactions."""
from __future__ import annotations

from sqlalchemy.exc import IntegrityError

from app.core.constants import TransactionType
from app.models.wallet import Wallet, WalletTransaction
from app.repositories.wallets import WalletRepository


class InsufficientBalanceError(Exception):
    """Raised when a debit would push the wallet below zero."""


class WalletService:
    """Balance mutations lock the wallet row before reading it.

    Lock ordering across the app is fixed as **invitee user row → referrer
    wallet row**; every financial path acquires locks in that order so two
    concurrent referral payouts can never deadlock against each other.
    """

    def __init__(self, wallets: WalletRepository) -> None:
        self.wallets = wallets

    async def _create_wallet(self, user_id: int, *, locked: bool) -> Wallet:
        """Create the wallet, tolerating a concurrent creator.

        ``wallets.user_id`` is unique, so a racing session may have inserted the
        row between our read and our insert. The insert runs inside a SAVEPOINT
        so that losing the race rolls back only this statement and leaves the
        surrounding transaction usable, after which we re-read the winner's row.
        """
        try:
            async with self.wallets.session.begin_nested():
                return await self.wallets.add(Wallet(user_id=user_id, balance=0))
        except IntegrityError:
            wallet = (
                await self.wallets.get_by_user_id_for_update(user_id)
                if locked
                else await self.wallets.get_by_user_id(user_id)
            )
            if wallet is None:  # pragma: no cover - unique violation implies a row
                raise
            return wallet

    async def get_or_create(self, user_id: int) -> Wallet:
        """Read-only accessor (balance display, history). Takes no row lock."""
        wallet = await self.wallets.get_by_user_id(user_id)
        if wallet is None:
            wallet = await self._create_wallet(user_id, locked=False)
        return wallet

    async def _get_locked_or_create(self, user_id: int) -> Wallet:
        """Accessor for mutations — returns the row with a write lock held."""
        wallet = await self.wallets.get_by_user_id_for_update(user_id)
        if wallet is None:
            wallet = await self._create_wallet(user_id, locked=True)
        return wallet

    async def _apply(
        self,
        wallet: Wallet,
        amount: int,
        tx_type: TransactionType,
        description: str | None,
    ) -> WalletTransaction:
        new_balance = wallet.balance + amount
        if new_balance < 0:
            raise InsufficientBalanceError
        wallet.balance = new_balance
        tx = WalletTransaction(
            wallet_id=wallet.id,
            amount=amount,
            type=tx_type,
            description=description,
            balance_after=new_balance,
        )
        return await self.wallets.add_transaction(tx)

    async def credit(
        self,
        user_id: int,
        amount: int,
        tx_type: TransactionType = TransactionType.DEPOSIT,
        description: str | None = None,
    ) -> WalletTransaction:
        wallet = await self._get_locked_or_create(user_id)
        return await self._apply(wallet, abs(amount), tx_type, description)

    async def debit(
        self,
        user_id: int,
        amount: int,
        tx_type: TransactionType = TransactionType.PURCHASE,
        description: str | None = None,
    ) -> WalletTransaction:
        wallet = await self._get_locked_or_create(user_id)
        return await self._apply(wallet, -abs(amount), tx_type, description)

    async def history(self, user_id: int, *, offset: int = 0, limit: int = 10):
        wallet = await self.get_or_create(user_id)
        return await self.wallets.list_transactions(wallet.id, offset=offset, limit=limit)
