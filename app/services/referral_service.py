"""Referral service — rewards a referrer once their invitee makes a first purchase."""
from __future__ import annotations

from redis.asyncio import Redis

from app.core.config import settings
from app.core.constants import TransactionType
from app.models.referral import Referral
from app.models.user import User
from app.repositories.referrals import ReferralRepository
from app.services.wallet_service import WalletService

# Admin-editable referral reward (Toman). Stored in Redis so it can be changed
# live from the admin panel; falls back to the REFERRAL_REWARD env default.
_REWARD_KEY = "referral:reward"


class ReferralResult:
    def __init__(
        self,
        rewarded: bool,
        referrer_telegram_id: int | None,
        amount: int,
        referrer_username: str | None = None,
    ):
        self.rewarded = rewarded
        self.referrer_telegram_id = referrer_telegram_id
        self.amount = amount
        self.referrer_username = referrer_username


class ReferralService:
    def __init__(
        self,
        referrals: ReferralRepository,
        wallets: WalletService,
        users_repo,
        redis: Redis | None = None,
    ) -> None:
        self.referrals = referrals
        self.wallets = wallets
        self.users = users_repo
        self.redis = redis

    async def get_reward(self) -> int:
        """Current referral reward — admin-editable value or the env default."""
        if self.redis is not None:
            raw = await self.redis.get(_REWARD_KEY)
            if raw is not None:
                try:
                    return int(raw)
                except (TypeError, ValueError):
                    pass
        return settings.referral_reward

    async def set_reward(self, amount: int) -> None:
        if self.redis is not None:
            await self.redis.set(_REWARD_KEY, int(amount))

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

        amount = await self.get_reward()
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
            description="پاداش دعوت کاربر جدید",
        )
        return ReferralResult(True, referrer.telegram_id, amount, referrer.username)

    async def process_pending(self, user: User) -> ReferralResult:
        """Reward a referral that was captured at /start but couldn't be paid yet.

        ``pending_referral_code`` is set (for new users only) by
        :meth:`UserService.get_or_create`. This consumes it — clearing it first so
        it can never be processed twice or retried on a bad code — and pays the
        referrer via :meth:`link_and_reward`, whose own anti-abuse guards (referrer
        exists, no self-invite, invitee referred at most once) still apply. If the
        user already has a referrer, nothing happens.
        """
        code = user.pending_referral_code
        if not code:
            return ReferralResult(False, None, 0)
        user.pending_referral_code = None
        if user.referred_by_id is not None:
            return ReferralResult(False, None, 0)
        return await self.link_and_reward(user, code)

    async def stats(self, user: User) -> dict[str, int]:
        total = await self.referrals.count_by_referrer(user.id)
        earned = await self.referrals.total_rewarded(user.id)
        return {"invited": total, "earned": earned}
