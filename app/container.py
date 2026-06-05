"""Dependency-injection container.

A ``Services`` instance is built per database session (one per update) and
exposes every repository and service already wired together. This keeps the
handlers free of construction boilerplate.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import redis_client
from app.repositories.accounts import (
    AccountRepository,
    AccountSaleRequestRepository,
    RequestedAccountRepository,
)
from app.repositories.orders import OrderRepository
from app.repositories.payments import PaymentRepository
from app.repositories.referrals import ReferralRepository
from app.repositories.tickets import TicketRepository
from app.repositories.users import UserRepository
from app.repositories.wallets import WalletRepository
from app.services.account_service import AccountService
from app.services.diamond_service import DiamondService
from app.services.order_service import OrderService
from app.services.referral_service import ReferralService
from app.services.ticket_service import TicketService
from app.services.user_service import UserService
from app.services.wallet_service import WalletService


class Services:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

        # repositories
        self.users = UserRepository(session)
        self.orders = OrderRepository(session)
        self.accounts_repo = AccountRepository(session)
        self.sale_requests_repo = AccountSaleRequestRepository(session)
        self.requested_repo = RequestedAccountRepository(session)
        self.payments = PaymentRepository(session)
        self.wallets_repo = WalletRepository(session)
        self.tickets_repo = TicketRepository(session)
        self.referrals_repo = ReferralRepository(session)

        # services
        self.wallet = WalletService(self.wallets_repo)
        self.user = UserService(self.users, self.referrals_repo)
        self.referral = ReferralService(self.referrals_repo, self.wallet, self.users)
        self.diamond = DiamondService(redis_client, self.orders)
        self.account = AccountService(
            self.accounts_repo,
            self.sale_requests_repo,
            self.requested_repo,
            self.orders,
        )
        self.order = OrderService(self.orders, self.payments)
        self.ticket = TicketService(self.tickets_repo)

    async def commit(self) -> None:
        await self.session.commit()
