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
from app.repositories.admins import AdminRepository
from app.repositories.app_settings import AppSettingRepository
from app.repositories.backup_settings import BackupSettingRepository
from app.repositories.banned_users import BannedUserRepository
from app.repositories.bot_texts import BotTextRepository
from app.repositories.button_settings import ButtonSettingsRepository
from app.repositories.cards import PaymentCardRepository
from app.repositories.deposit_settings import DepositSettingRepository
from app.repositories.discounts import DiscountCodeRepository
from app.repositories.locked_channels import LockedChannelRepository
from app.repositories.orders import OrderRepository
from app.repositories.payments import PaymentRepository
from app.repositories.referrals import ReferralRepository
from app.repositories.tickets import TicketRepository
from app.repositories.tutorial_media import TutorialMediaRepository
from app.repositories.users import UserRepository
from app.repositories.wallets import WalletRepository
from app.repositories.wallet_topup_requests import WalletTopUpRequestRepository
from app.services.account_service import AccountService
from app.services.admin_service import AdminService
from app.services.backup_service import BackupService
from app.services.ban_service import BanService
from app.services.button_service import ButtonService
from app.services.card_service import CardService
from app.services.channel_lock_service import ChannelLockService
from app.services.deposit_service import DepositService
from app.services.diamond_service import DiamondService
from app.services.discount_service import DiscountService
from app.services.order_service import OrderService
from app.services.referral_service import ReferralService
from app.services.settings_service import SettingsService
from app.services.text_service import TextService
from app.services.ticket_service import TicketService
from app.services.tutorial_service import TutorialService
from app.services.user_service import UserService
from app.services.verification_service import VerificationService
from app.services.wallet_service import WalletService
from app.services.wallet_topup_service import WalletTopUpService


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
        self.wallet_topup_requests_repo = WalletTopUpRequestRepository(session)
        self.tickets_repo = TicketRepository(session)
        self.referrals_repo = ReferralRepository(session)
        self.cards_repo = PaymentCardRepository(session)
        self.discounts_repo = DiscountCodeRepository(session)
        self.bot_texts_repo = BotTextRepository(session)
        self.tutorial_repo = TutorialMediaRepository(session)
        self.button_repo = ButtonSettingsRepository(session)
        self.locked_channels_repo = LockedChannelRepository(session)
        self.deposit_repo = DepositSettingRepository(session)
        self.admins_repo = AdminRepository(session)
        self.banned_repo = BannedUserRepository(session)
        self.backup_repo = BackupSettingRepository(session)
        self.app_settings_repo = AppSettingRepository(session)

        # services
        # Durable settings store (MySQL source of truth) — must be built before the
        # services that read/write settings through it (referral, diamond).
        self.settings = SettingsService(self.app_settings_repo)
        self.wallet = WalletService(self.wallets_repo)
        self.wallet_topup = WalletTopUpService(
            self.wallet_topup_requests_repo, self.wallet
        )
        self.user = UserService(self.users, self.referrals_repo)
        self.referral = ReferralService(
            self.referrals_repo, self.wallet, self.users, self.settings
        )
        # Onboarding gate — owns the referral payout hand-off, so it must be
        # built after the referral service it delegates to.
        self.verification = VerificationService(
            self.users, self.referral, redis_client
        )
        self.diamond = DiamondService(self.settings, self.orders)
        self.account = AccountService(
            self.accounts_repo,
            self.sale_requests_repo,
            self.requested_repo,
            self.orders,
        )
        self.order = OrderService(self.orders, self.payments)
        self.ticket = TicketService(self.tickets_repo)
        self.card = CardService(self.cards_repo)
        self.discount = DiscountService(self.discounts_repo)
        self.text = TextService(self.bot_texts_repo)
        self.tutorial = TutorialService(self.tutorial_repo)
        self.button = ButtonService(self.button_repo)
        self.channel = ChannelLockService(self.locked_channels_repo, redis_client)
        self.deposit = DepositService(self.deposit_repo)
        self.admin = AdminService(self.admins_repo, self.users, redis_client)
        self.ban = BanService(self.banned_repo, self.users)
        self.backup = BackupService(self.backup_repo)

    async def commit(self) -> None:
        await self.session.commit()
