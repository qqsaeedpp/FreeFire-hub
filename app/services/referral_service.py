"""Referral service — rewards a referrer once their invitee makes a first purchase."""
from __future__ import annotations

from app.core.config import settings
from app.core.constants import TransactionType
from app.models.user import User
from app.repositories.referrals import ReferralRepository
from app.services.wallet_service import WalletService


class ReferralResult:
    def __init__(self, rewarded: bool, referrer_telegram_id: int | None, amount: int):
        self.rewarded = rewarded
        self.referrer_telegram_id = referrer_telegram_id
        self.amount = amount


class ReferralService:
    def __init__(
        self,
        referrals: ReferralRepository,
        wallets: WalletService,
        users_repo,
    ) -> None:
        self.referrals = referrals
        self.wallets = wallets
        self.users = users_repo

    async def reward_on_first_purchase(self, buyer: User) -> ReferralResult:
        """Called after a successful purchase. Pays the referrer exactly once."""
        referral = await self.referrals.get_by_referred(buyer.id)
        if referral is None or referral.rewarded:
            return ReferralResult(False, None, 0)

        amount = settings.referral_reward
        await self.wallets.credit(
            referral.referrer_id,
            amount,
            TransactionType.REFERRAL_REWARD,
            description=f"پاداش دعوت کاربر {buyer.telegram_id}",
        )
        referral.rewarded = True
        referral.reward_amount = amount

        referrer = await self.users.get(referral.referrer_id)
        tg_id = referrer.telegram_id if referrer else None
        return ReferralResult(True, tg_id, amount)

    async def stats(self, user: User) -> dict[str, int]:
        total = await self.referrals.count_by_referrer(user.id)
        earned = await self.referrals.total_rewarded(user.id)
        return {"invited": total, "earned": earned}
