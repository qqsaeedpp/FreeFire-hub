"""Referral service — rewards a referrer once their invitee makes a first purchase."""
from __future__ import annotations

from app.core.config import settings
from app.core.constants import TransactionType
from app.models.referral import Referral
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

    async def link_and_reward(
        self, new_user: User, referral_code: str
    ) -> ReferralResult:
        """Register ``new_user`` as a referral of ``referral_code``'s owner and pay
        the referrer once.

        Anti-abuse: the referrer must exist and differ from the invitee, and the
        invitee may be referred only once (enforced both here and by the unique
        ``referrals.referred_id`` constraint). Callers must additionally gate this
        on the invitee being a genuinely new user so a repeat /start can't re-pay.
        """
        referrer = await self.users.get_by_referral_code(referral_code)
        if referrer is None or referrer.id == new_user.id:
            return ReferralResult(False, None, 0)
        if await self.referrals.get_by_referred(new_user.id):
            return ReferralResult(False, None, 0)

        amount = settings.referral_reward
        new_user.referred_by_id = referrer.id
        await self.referrals.add(
            Referral(
                referrer_id=referrer.id,
                referred_id=new_user.id,
                rewarded=True,
                reward_amount=amount,
            )
        )
        await self.wallets.credit(
            referrer.id,
            amount,
            TransactionType.REFERRAL_REWARD,
            description=f"پاداش دعوت کاربر {new_user.telegram_id}",
        )
        return ReferralResult(True, referrer.telegram_id, amount)

    async def stats(self, user: User) -> dict[str, int]:
        total = await self.referrals.count_by_referrer(user.id)
        earned = await self.referrals.total_rewarded(user.id)
        return {"invited": total, "earned": earned}
