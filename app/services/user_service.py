"""User service — registration, referral linkage, ban/unban."""
from __future__ import annotations

from app.models.user import User
from app.models.wallet import Wallet
from app.repositories.referrals import ReferralRepository
from app.repositories.users import UserRepository
from app.utils.helpers import unique_referral_code


class UserService:
    def __init__(self, users: UserRepository, referrals: ReferralRepository) -> None:
        self.users = users
        self.referrals = referrals

    async def get_or_create(
        self,
        telegram_id: int,
        *,
        username: str | None,
        full_name: str | None,
        referral_code: str | None = None,
    ) -> tuple[User, bool]:
        """Return (user, created). Links referral on first creation."""
        existing = await self.users.get_by_telegram_id(telegram_id)
        if existing:
            # keep profile fields fresh
            existing.username = username
            existing.full_name = full_name
            return existing, False

        code = await unique_referral_code(self.users)
        user = User(
            telegram_id=telegram_id,
            username=username,
            full_name=full_name,
            referral_code=code,
            is_admin=False,
        )
        user.wallet = Wallet(balance=0)
        await self.users.add(user)

        if referral_code:
            await self._link_referral(user, referral_code)

        return user, True

    async def _link_referral(self, new_user: User, referral_code: str) -> None:
        from app.models.referral import Referral

        referrer = await self.users.get_by_referral_code(referral_code)
        if not referrer or referrer.id == new_user.id:
            return
        if await self.referrals.get_by_referred(new_user.id):
            return
        new_user.referred_by_id = referrer.id
        await self.referrals.add(
            Referral(referrer_id=referrer.id, referred_id=new_user.id)
        )

    async def set_banned(self, user: User, banned: bool) -> None:
        user.is_banned = banned

    async def mark_purchased(self, user: User) -> None:
        user.has_purchased = True
