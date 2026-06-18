"""Wallet top-up service — the single source of truth shared by both paths.

Both the user flow (which raises a request + fires the admin notification) and the
admin panel (the «💰 سفارش‌های کیف پول» list + approve/reject) go through this one
service, so a request is created once and read/decided consistently everywhere.

The wallet is credited **only** on approval, and approval is *idempotent*: the
status guard means clicking «تایید» twice (e.g. from duplicate admin notifications)
credits the wallet exactly once — the second call is a no-op.
"""
from __future__ import annotations

from app.core.constants import PaymentMethod, TransactionType, WalletTopUpStatus
from app.models.wallet_topup_request import WalletTopUpRequest
from app.repositories.wallet_topup_requests import WalletTopUpRequestRepository
from app.services.wallet_service import WalletService


class WalletTopUpService:
    def __init__(
        self, requests: WalletTopUpRequestRepository, wallet: WalletService
    ) -> None:
        self.requests = requests
        self.wallet = wallet

    async def create_request(
        self,
        *,
        user_id: int,
        amount: int,
        payment_method: PaymentMethod | None = None,
        receipt_file_id: str | None = None,
    ) -> WalletTopUpRequest:
        """Persist a PENDING charge request (no wallet change yet)."""
        return await self.requests.add(
            WalletTopUpRequest(
                user_id=user_id,
                amount=amount,
                payment_method=payment_method,
                receipt_file_id=receipt_file_id,
                status=WalletTopUpStatus.PENDING,
            )
        )

    async def get(self, req_id: int) -> WalletTopUpRequest | None:
        return await self.requests.get(req_id)

    async def list_pending(
        self, *, page: int = 1, page_size: int = 10
    ) -> tuple[list[WalletTopUpRequest], int]:
        offset = max(0, (page - 1) * page_size)
        items = await self.requests.list_by_status(
            WalletTopUpStatus.PENDING, offset=offset, limit=page_size
        )
        total = await self.requests.count_by_status(WalletTopUpStatus.PENDING)
        return items, total

    async def approve(self, req: WalletTopUpRequest) -> int | None:
        """Approve & credit the wallet exactly once (idempotent).

        Returns the credited amount, or ``None`` if the request was already
        processed (so the caller can avoid a double notification / message).
        """
        if req.status is not WalletTopUpStatus.PENDING:
            return None
        req.status = WalletTopUpStatus.APPROVED
        await self.wallet.credit(
            req.user_id,
            req.amount,
            TransactionType.WALLET_CHARGE,
            description=f"شارژ کیف پول (درخواست #{req.id})",
        )
        return req.amount

    async def reject(self, req: WalletTopUpRequest) -> bool:
        """Decline the request (no credit). Idempotent — ``False`` if already acted on."""
        if req.status is not WalletTopUpStatus.PENDING:
            return False
        req.status = WalletTopUpStatus.REJECTED
        return True
