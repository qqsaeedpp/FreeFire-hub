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
    ) -> tuple[User, bool]:
        """Return (user, created). Referral linkage is handled separately by the
        deep-link /start handler via :meth:`ReferralService.link_and_reward`."""
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
        return user, True

    async def set_banned(self, user: User, banned: bool) -> None:
        user.is_banned = banned

    async def mark_purchased(self, user: User) -> None:
        user.has_purchased = True
