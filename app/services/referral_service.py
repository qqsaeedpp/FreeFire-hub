"""Referral service — rewards a referrer once their invitee makes a first purchase."""
from __future__ import annotations

from app.core.config import settings
from app.core.constants import TransactionType
from app.models.referral import Referral
from app.models.user import User
from app.repositories.referrals import ReferralRepository
from app.services.settings_service import KEY_REFERRAL_REWARD, SettingsService
from app.services.wallet_service import WalletService


class ReferralResult:
    def __init__(
        self,
        rewarded: bool,
        referrer_telegram_id: int | None,
        amount: int,
        referrer_username: str | None = None,
        referrer_full_name: str | None = None,
    ):
        self.rewarded = rewarded
        self.referrer_telegram_id = referrer_telegram_id
        self.amount = amount
        self.referrer_username = referrer_username
        # Carried so referral notifications can render a tappable profile link
        # for a referrer who has no @username. Optional/defaulted → backward
        # compatible with every existing ``ReferralResult(...)`` construction.
        self.referrer_full_name = referrer_full_name


class ReferralService:
    def __init__(
        self,
        referrals: ReferralRepository,
        wallets: WalletService,
        users_repo,
        app_settings: SettingsService,
    ) -> None:
        self.referrals = referrals
        self.wallets = wallets
        self.users = users_repo
        self.app_settings = app_settings

    async def get_reward(self) -> int:
        """Current referral reward (Toman) — the admin-set value, durable in MySQL.

        The ``REFERRAL_REWARD`` env value is used only as the default until an admin
        sets one; once set, it never auto-changes (no more 0 → 10,000 reverts).
        """
        return await self.app_settings.get_int(
            KEY_REFERRAL_REWARD, settings.referral_reward
        )

    async def set_reward(self, amount: int, *, changed_by: int | None = None) -> str | None:
        """Persist the referral reward (admin action); returns the previous value.

        The caller must ``commit()`` so the value and its audit row land together.
        """
        return await self.app_settings.set_int(
            KEY_REFERRAL_REWARD, amount, changed_by=changed_by
        )

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
        return ReferralResult(
            True, referrer.telegram_id, amount, referrer.username, referrer.full_name
        )

    async def process_pending(self, user: User) -> ReferralResult:
        """Reward a referral that was captured at /start but couldn't be paid yet.

        ``pending_referral_code`` is set (for new users only) by
        :meth:`UserService.get_or_create`. This consumes it — clearing it first so
        it can never be processed twice or retried on a bad code — and pays the
        referrer via :meth:`link_and_reward`, whose own anti-abuse guards (referrer
        exists, no self-invite, invitee referred at most once) still apply. If the
        user already has a referrer, nothing happens.

        A referral may only be created for a **fully verified** invitee. That rule
        is enforced here, not just at the call sites, so no present or future
        handler can pay out a referral for an unverified account. The check runs
        *before* the pending code is read or cleared, so an unverified user keeps
        their code for the retry that follows verification.
        """
        if user.verification_completed_at is None:
            return ReferralResult(False, None, 0)
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

    # ---- admin: reset referral statistics (relations preserved) ----
    async def reset_user_statistics(self, user: User) -> int:
        """Zero one user's referral counters while keeping every relation row.

        Only the *displayed* stats (invite count / rewarded sum) go to zero; the
        invite relations and the double-reward guard stay intact, so a re-/start by
        an already-counted invitee can never trigger a second reward. Returns the
        number of rows reset.
        """
        return await self.referrals.reset_counts_for_referrer(user.id)

    async def reset_all_statistics(self) -> int:
        """Zero *every* referrer's counters globally — deletes no Referral record.

        Same guarantees as :meth:`reset_user_statistics`, applied to all rows.
        Returns the number of rows reset.
        """
        return await self.referrals.reset_all_counts()

    # ---- admin: invite management ----
    async def referrers_overview(self, *, page: int, page_size: int):
        """One page of referrers (busiest first), each resolved to its user object.

        Returns ``(rows, total)`` where each row is ``(user, referrer_id, count)``.
        ``user`` may be ``None`` if that account was since deleted, so the caller
        must fall back to the raw id for display.
        """
        offset = (page - 1) * page_size
        pairs = await self.referrals.list_referrers(offset=offset, limit=page_size)
        total = await self.referrals.count_referrers()
        rows = [(await self.users.get(rid), rid, count) for rid, count in pairs]
        return rows, total

    async def referred_detail(self, referrer_id: int, *, page: int, page_size: int):
        """One page of a referrer's invitees plus header totals.

        Returns ``(rows, total, rewarded_sum)`` where each row is
        ``(referral, invited_user)``; ``invited_user`` may be ``None`` if deleted.
        """
        offset = (page - 1) * page_size
        refs = await self.referrals.list_referred(
            referrer_id, offset=offset, limit=page_size
        )
        total = await self.referrals.count_by_referrer(referrer_id)
        rewarded_sum = await self.referrals.total_rewarded(referrer_id)
        rows = [(r, await self.users.get(r.referred_id)) for r in refs]
        return rows, total, rewarded_sum
