"""Onboarding verification — Iranian mobile ownership + a math captcha.

Design rules this service exists to enforce:

* **MySQL is the only source of truth.** The current step is derived from the
  three ``users`` timestamps, never from FSM state or Redis, so a bot restart, a
  cleared FSM or a flushed Redis cannot lose progress or re-ask for a phone.
* **Redis holds only the throwaway captcha challenge**, always with a TTL.
* **No referral before verification.** Finalization sets the timestamps and pays
  the referral inside one transaction; :class:`ReferralService` independently
  refuses to pay an unverified user.
* **Lock order is fixed**: invitee ``users`` row → referrer ``wallets`` row.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.logger import get_logger
from app.repositories.users import UserRepository
from app.models.user import User
from app.services.referral_service import ReferralResult, ReferralService
from app.utils.phone import (
    InvalidPhoneNumberError,
    mask_phone,
    normalize_iranian_mobile,
)

log = get_logger("verification")

_CAPTCHA_KEY = "verification:captcha:{tg_id}"
_FAILS_KEY = "verification:captcha:fails:{tg_id}"

# Atomically validate-and-consume a challenge.
#
# Deleting the hash *inside* the script is what makes a challenge single-use:
# two callbacks racing on the same nonce cannot both observe it, so a
# double-clicked correct answer can only finalize once. A stale nonce (an old
# message's button) returns early WITHOUT deleting, so replaying an expired
# callback can never destroy the challenge the user is currently looking at.
_CONSUME_LUA = """
local current = redis.call('HGET', KEYS[1], 'nonce')
if not current then return 'expired' end
if current ~= ARGV[1] then return 'stale' end
local answer = redis.call('HGET', KEYS[1], 'answer')
redis.call('DEL', KEYS[1])
if answer == ARGV[2] then return 'ok' end
return 'wrong'
"""


class OnboardingStep(str, Enum):
    """Where a user stands, resolved purely from durable MySQL columns."""

    PHONE = "phone"
    CAPTCHA = "captcha"
    DONE = "done"


class CaptchaOutcome(str, Enum):
    OK = "ok"
    WRONG = "wrong"
    EXPIRED = "expired"
    STALE = "stale"
    LOCKED = "locked"


class PhoneVerificationError(Exception):
    """Base class for a *user-correctable* phone problem."""


class ContactOwnershipError(PhoneVerificationError):
    """The contact was typed, forwarded, or belongs to somebody else."""


class PhoneNotIranianMobileError(PhoneVerificationError):
    """Structurally not a valid Iranian mobile line."""


class PhoneAlreadyUsedError(PhoneVerificationError):
    """The number is already verified on a different Telegram account."""


@dataclass(frozen=True)
class CaptchaChallenge:
    """One math question. ``answer`` never leaves the server."""

    nonce: str
    first: int
    second: int
    answer: int
    options: tuple[int, ...]

    @property
    def question(self) -> str:
        return f"{self.first} + {self.second} = ؟"


@dataclass(frozen=True)
class VerificationResult:
    """Outcome of finalization: what changed, and what to announce."""

    completed: bool
    already_completed: bool
    referral: ReferralResult


class VerificationService:
    def __init__(
        self,
        users: UserRepository,
        referrals: ReferralService,
        redis,
    ) -> None:
        self.users = users
        self.referrals = referrals
        self.redis = redis

    # ------------------------------------------------------------------ state
    @staticmethod
    def is_complete(user: User | None) -> bool:
        return bool(user and user.verification_completed_at is not None)

    @staticmethod
    def next_step(user: User) -> OnboardingStep:
        """Resolve the pending step from durable columns only.

        A pre-existing ``phone`` with no ``phone_verified_at`` (hand-entered
        before this feature shipped) deliberately still requires the contact
        step — the value was never proven to belong to the account.
        """
        if user.verification_completed_at is not None:
            return OnboardingStep.DONE
        if user.phone_verified_at is None:
            return OnboardingStep.PHONE
        return OnboardingStep.CAPTCHA

    # ------------------------------------------------------------------ phone
    @staticmethod
    def extract_owned_phone(message) -> str:
        """Return the E.164 number proven to belong to *message*'s sender.

        Telegram only sets ``contact.user_id`` when the contact card is a real
        Telegram account, and it equals the sender only when the sender shared
        *themselves* via ``request_contact``. Everything else — typed text, a
        forwarded card, a friend's contact — is rejected, so the number cannot be
        forged.
        """
        contact = getattr(message, "contact", None)
        sender = getattr(message, "from_user", None)
        if contact is None or sender is None:
            raise ContactOwnershipError("no contact attached")
        if contact.user_id is None or contact.user_id != sender.id:
            raise ContactOwnershipError("contact does not belong to the sender")
        try:
            return normalize_iranian_mobile(contact.phone_number)
        except InvalidPhoneNumberError as exc:
            raise PhoneNotIranianMobileError(str(exc)) from exc

    async def claim_phone(self, user: User, phone: str) -> None:
        """Bind *phone* to *user* and stamp ``phone_verified_at``.

        Idempotent for the same owner: re-sending your own contact is a no-op
        rather than an error. Uniqueness is ultimately enforced by the database
        index, not by the pre-check — two accounts submitting the same number at
        once both pass the read, so the losing INSERT/UPDATE raises
        ``IntegrityError``, which is caught inside a SAVEPOINT and converted into
        :class:`PhoneAlreadyUsedError`. The transaction stays usable and the
        user's ``pending_referral_code`` is untouched.
        """
        owner = await self.users.get_by_phone(phone)
        if owner is not None and owner.id != user.id:
            raise PhoneAlreadyUsedError("phone belongs to another account")

        if user.phone == phone and user.phone_verified_at is not None:
            return  # already verified by this same user

        user.phone = phone
        user.phone_verified_at = datetime.now(timezone.utc).replace(tzinfo=None)
        try:
            async with self.users.session.begin_nested():
                await self.users.session.flush()
        except IntegrityError as exc:
            # A racing account won the unique index; discard our optimistic write.
            self.users.session.expire(user, ["phone", "phone_verified_at"])
            log.info(
                "phone_claim_conflict",
                telegram_id=user.telegram_id,
                phone=mask_phone(phone),
            )
            raise PhoneAlreadyUsedError("phone belongs to another account") from exc

        log.info(
            "phone_verified",
            telegram_id=user.telegram_id,
            phone=mask_phone(phone),
        )

    # ---------------------------------------------------------------- captcha
    async def issue_captcha(self, telegram_id: int) -> CaptchaChallenge:
        """Create (and store, with TTL) a fresh challenge bound to *telegram_id*.

        Replaces any previous challenge, so the newest question is always the
        only valid one. The answer is stored server-side; the callback carries
        only an opaque nonce and the tapped value.
        """
        first = secrets.randbelow(9) + 1
        second = secrets.randbelow(9) + 1
        answer = first + second

        options = {answer}
        while len(options) < 4:
            # Plausible near-misses, clamped to the range a sum of 1..9 can take.
            candidate = answer + secrets.randbelow(7) - 3
            if 2 <= candidate <= 18:
                options.add(candidate)
        shuffled = list(options)
        for i in range(len(shuffled) - 1, 0, -1):
            j = secrets.randbelow(i + 1)
            shuffled[i], shuffled[j] = shuffled[j], shuffled[i]

        challenge = CaptchaChallenge(
            nonce=secrets.token_urlsafe(8),
            first=first,
            second=second,
            answer=answer,
            options=tuple(shuffled),
        )
        key = _CAPTCHA_KEY.format(tg_id=telegram_id)
        await self.redis.delete(key)
        await self.redis.hset(
            key, mapping={"nonce": challenge.nonce, "answer": str(answer)}
        )
        await self.redis.expire(key, settings.captcha_ttl_seconds)
        return challenge

    async def submit_captcha(
        self, telegram_id: int, nonce: str, choice: int
    ) -> CaptchaOutcome:
        """Atomically validate and consume the current challenge."""
        fails_key = _FAILS_KEY.format(tg_id=telegram_id)
        raw_fails = await self.redis.get(fails_key)
        if raw_fails is not None and int(raw_fails) >= settings.captcha_max_attempts:
            return CaptchaOutcome.LOCKED

        verdict = await self.redis.eval(
            _CONSUME_LUA,
            1,
            _CAPTCHA_KEY.format(tg_id=telegram_id),
            nonce,
            str(choice),
        )
        outcome = CaptchaOutcome(verdict)
        if outcome is CaptchaOutcome.WRONG:
            fails = await self.redis.incr(fails_key)
            await self.redis.expire(fails_key, settings.captcha_cooldown_seconds)
            if fails >= settings.captcha_max_attempts:
                return CaptchaOutcome.LOCKED
        elif outcome is CaptchaOutcome.OK:
            await self.redis.delete(fails_key)
        return outcome

    # ------------------------------------------------------------- finalize
    async def finalize(self, user: User) -> VerificationResult:
        """Complete verification and settle the referral in ONE transaction.

        Steps, in the documented lock order:

        1. Re-read the invitee ``users`` row ``FOR UPDATE`` — this serializes
           concurrent finalizations for the same account.
        2. Bail out as a no-op if verification already completed (idempotency).
        3. Require a proven phone; refuse otherwise.
        4. Stamp ``captcha_verified_at`` + ``verification_completed_at``.
        5. Hand off to :meth:`ReferralService.process_pending`, which now sees a
           verified user, consumes ``pending_referral_code`` and — via
           ``link_and_reward`` — locks the *referrer's wallet* row before
           crediting it and writing the matching ``WalletTransaction``.

        The caller commits exactly once and only then sends notifications, so a
        failed Telegram send can never roll back a payout, and any exception
        rolls back the whole unit — including the pending code, which therefore
        survives transient database errors.
        """
        locked = await self.users.get_for_update(user.id)
        target = locked if locked is not None else user

        if target.verification_completed_at is not None:
            return VerificationResult(
                completed=False,
                already_completed=True,
                referral=ReferralResult(False, None, 0),
            )
        if not target.phone or target.phone_verified_at is None:
            raise PhoneVerificationError("phone step not completed")

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        target.captcha_verified_at = now
        target.verification_completed_at = now
        await self.users.session.flush()

        referral = await self.referrals.process_pending(target)
        await self.users.session.flush()

        log.info(
            "verification_completed",
            telegram_id=target.telegram_id,
            rewarded=referral.rewarded,
        )
        return VerificationResult(
            completed=True, already_completed=False, referral=referral
        )
