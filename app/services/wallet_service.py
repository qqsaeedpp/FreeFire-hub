"""Wallet service — balance mutations are always recorded as transactions."""
from __future__ import annotations

from app.core.constants import TransactionType
from app.models.wallet import Wallet, WalletTransaction
from app.repositories.wallets import WalletRepository


class InsufficientBalanceError(Exception):
    """Raised when a debit would push the wallet below zero."""


class WalletService:
    def __init__(self, wallets: WalletRepository) -> None:
        self.wallets = wallets

    async def get_or_create(self, user_id: int) -> Wallet:
        wallet = await self.wallets.get_by_user_id(user_id)
        if wallet is None:
            wallet = await self.wallets.add(Wallet(user_id=user_id, balance=0))
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
        wallet = await self.get_or_create(user_id)
        return await self._apply(wallet, abs(amount), tx_type, description)

    async def debit(
        self,
        user_id: int,
        amount: int,
        tx_type: TransactionType = TransactionType.PURCHASE,
        description: str | None = None,
    ) -> WalletTransaction:
        wallet = await self.get_or_create(user_id)
        return await self._apply(wallet, -abs(amount), tx_type, description)

    async def history(self, user_id: int, *, offset: int = 0, limit: int = 10):
        wallet = await self.get_or_create(user_id)
        return await self.wallets.list_transactions(wallet.id, offset=offset, limit=limit)
