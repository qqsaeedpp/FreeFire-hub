"""Onboarding verification: contact ownership, phone uniqueness, captcha, and
the referral/wallet invariants that hang off finalization.

Every test drives the real services (see ``build_services``); only Redis is
in-process and only the Telegram ``Message``/``Contact`` shapes are stand-ins for
the wire objects, since the code under test reads them as plain data.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from aiogram.exceptions import TelegramAPIError

from app.core.constants import TransactionType
from app.models.user import User
from app.services.verification_service import (
    CaptchaOutcome,
    ContactOwnershipError,
    OnboardingStep,
    PhoneAlreadyUsedError,
    PhoneNotIranianMobileError,
)
from tests.conftest import build_services

PHONE = "+989121234567"
OTHER_PHONE = "+989351112233"


# --------------------------------------------------------------------- helpers
async def make_user(session, telegram_id: int, code: str, **kwargs) -> User:
    user = User(telegram_id=telegram_id, referral_code=code, **kwargs)
    session.add(user)
    await session.flush()
    return user


def contact_message(sender_id: int, contact_user_id, phone: str = "09121234567"):
    """A ``Message`` carrying a shared contact, as Telegram delivers it."""
    return SimpleNamespace(
        contact=SimpleNamespace(user_id=contact_user_id, phone_number=phone),
        from_user=SimpleNamespace(id=sender_id),
    )


async def solve_captcha(svc, user) -> None:
    """Run the captcha step honestly: issue a challenge, answer it correctly."""
    challenge = await svc.verification.issue_captcha(user.telegram_id)
    outcome = await svc.verification.submit_captcha(
        user.telegram_id, challenge.nonce, challenge.answer
    )
    assert outcome is CaptchaOutcome.OK


async def fully_verify(svc, user, phone: str = PHONE):
    await svc.verification.claim_phone(user, phone)
    await solve_captcha(svc, user)
    return await svc.verification.finalize(user)


# ------------------------------------------------------- contact ownership
@pytest.mark.asyncio
async def test_contact_owned_by_sender_is_accepted(session, redis):
    svc = build_services(session, redis)
    phone = svc.verification.extract_owned_phone(contact_message(555, 555))
    assert phone == PHONE


@pytest.mark.asyncio
async def test_contact_belonging_to_someone_else_is_rejected(session, redis):
    svc = build_services(session, redis)
    with pytest.raises(ContactOwnershipError):
        svc.verification.extract_owned_phone(contact_message(555, 999))


@pytest.mark.asyncio
async def test_contact_without_user_id_is_rejected(session, redis):
    """A manually-typed / forwarded contact card carries no ``user_id``."""
    svc = build_services(session, redis)
    with pytest.raises(ContactOwnershipError):
        svc.verification.extract_owned_phone(contact_message(555, None))


@pytest.mark.asyncio
async def test_typed_text_number_is_rejected(session, redis):
    svc = build_services(session, redis)
    typed = SimpleNamespace(
        contact=None, text="09121234567", from_user=SimpleNamespace(id=555)
    )
    with pytest.raises(ContactOwnershipError):
        svc.verification.extract_owned_phone(typed)


@pytest.mark.asyncio
async def test_foreign_number_in_a_valid_contact_is_rejected(session, redis):
    svc = build_services(session, redis)
    with pytest.raises(PhoneNotIranianMobileError):
        svc.verification.extract_owned_phone(
            contact_message(555, 555, phone="+12025550123")
        )


# ------------------------------------------------------------ phone uniqueness
@pytest.mark.asyncio
async def test_claim_phone_stores_e164_and_stamps_only_the_phone_step(session, redis):
    svc = build_services(session, redis)
    user = await make_user(session, 1, "AAA")

    await svc.verification.claim_phone(user, PHONE)

    assert user.phone == PHONE
    assert user.phone_verified_at is not None
    # Verification is NOT complete yet — the captcha still stands between them.
    assert user.captcha_verified_at is None
    assert user.verification_completed_at is None
    assert svc.verification.next_step(user) is OnboardingStep.CAPTCHA


@pytest.mark.asyncio
async def test_resending_own_contact_is_idempotent(session, redis):
    svc = build_services(session, redis)
    user = await make_user(session, 1, "AAA")

    await svc.verification.claim_phone(user, PHONE)
    stamped = user.phone_verified_at
    await svc.verification.claim_phone(user, PHONE)

    assert user.phone_verified_at == stamped


@pytest.mark.asyncio
async def test_phone_owned_by_another_account_is_rejected(session, redis):
    svc = build_services(session, redis)
    first = await make_user(session, 1, "AAA")
    second = await make_user(session, 2, "BBB", pending_referral_code="AAA")
    await svc.verification.claim_phone(first, PHONE)

    with pytest.raises(PhoneAlreadyUsedError):
        await svc.verification.claim_phone(second, PHONE)

    assert second.phone is None
    # The pending code must survive so a retry can still pay the referrer.
    assert second.pending_referral_code == "AAA"


@pytest.mark.asyncio
async def test_concurrent_claims_of_one_number_have_a_single_winner(file_db, redis):
    """Two sessions race past the pre-check; the unique index breaks the tie.

    This exercises the real ``IntegrityError`` path — the loser is converted to
    ``PhoneAlreadyUsedError`` and its transaction stays usable.
    """
    async with file_db() as setup:
        # Seed both accounts up front: SQLite allows only one writer at a time,
        # so the race has to be staged around the claim itself.
        await make_user(setup, 1, "AAA")
        await make_user(setup, 2, "BBB")
        await setup.commit()

    async with file_db() as sa, file_db() as sb:
        svc_a, svc_b = build_services(sa, redis), build_services(sb, redis)
        user_a = await svc_a.users.get_by_telegram_id(1)
        user_b = await svc_b.users.get_by_telegram_id(2)

        # Both read "free" before either writes — this is the interleaving that
        # makes the application-level pre-check insufficient on its own.
        assert await svc_a.users.get_by_phone(PHONE) is None
        assert await svc_b.users.get_by_phone(PHONE) is None

        await svc_a.verification.claim_phone(user_a, PHONE)
        await sa.commit()

        with pytest.raises(PhoneAlreadyUsedError):
            await svc_b.verification.claim_phone(user_b, PHONE)

        # Loser's session is still healthy and its user unmodified.
        await sb.rollback()
        refreshed = await svc_b.users.get_by_telegram_id(2)
        assert refreshed.phone is None


# ------------------------------------------------------------------- captcha
@pytest.mark.asyncio
async def test_challenge_has_four_unique_options_including_the_answer(session, redis):
    svc = build_services(session, redis)
    challenge = await svc.verification.issue_captcha(42)

    assert len(set(challenge.options)) == 4
    assert challenge.answer in challenge.options
    assert challenge.answer == challenge.first + challenge.second
    assert 1 <= challenge.first <= 9 and 1 <= challenge.second <= 9


@pytest.mark.asyncio
async def test_correct_answer_is_accepted_once_only(session, redis):
    """A double-clicked correct answer can only be consumed a single time."""
    svc = build_services(session, redis)
    challenge = await svc.verification.issue_captcha(42)

    first = await svc.verification.submit_captcha(42, challenge.nonce, challenge.answer)
    second = await svc.verification.submit_captcha(42, challenge.nonce, challenge.answer)

    assert first is CaptchaOutcome.OK
    assert second is CaptchaOutcome.EXPIRED


@pytest.mark.asyncio
async def test_wrong_answer_consumes_the_challenge(session, redis):
    svc = build_services(session, redis)
    challenge = await svc.verification.issue_captcha(42)
    wrong = next(o for o in challenge.options if o != challenge.answer)

    assert await svc.verification.submit_captcha(42, challenge.nonce, wrong) is (
        CaptchaOutcome.WRONG
    )
    # The consumed challenge cannot be retried with the right answer afterwards.
    assert await svc.verification.submit_captcha(
        42, challenge.nonce, challenge.answer
    ) is CaptchaOutcome.EXPIRED


@pytest.mark.asyncio
async def test_stale_nonce_cannot_destroy_the_current_challenge(session, redis):
    """An old message's button must not invalidate the question on screen."""
    svc = build_services(session, redis)
    old = await svc.verification.issue_captcha(42)
    current = await svc.verification.issue_captcha(42)

    assert await svc.verification.submit_captcha(42, old.nonce, old.answer) is (
        CaptchaOutcome.STALE
    )
    # The live challenge is untouched and still solvable.
    assert await svc.verification.submit_captcha(
        42, current.nonce, current.answer
    ) is CaptchaOutcome.OK


@pytest.mark.asyncio
async def test_repeated_wrong_answers_trigger_a_cooldown(session, redis):
    from app.core.config import settings

    svc = build_services(session, redis)
    outcome = None
    for _ in range(settings.captcha_max_attempts):
        challenge = await svc.verification.issue_captcha(42)
        wrong = next(o for o in challenge.options if o != challenge.answer)
        outcome = await svc.verification.submit_captcha(42, challenge.nonce, wrong)

    assert outcome is CaptchaOutcome.LOCKED
    # While locked, even a fresh correct answer is refused.
    fresh = await svc.verification.issue_captcha(42)
    assert await svc.verification.submit_captcha(
        42, fresh.nonce, fresh.answer
    ) is CaptchaOutcome.LOCKED


@pytest.mark.asyncio
async def test_redis_loss_keeps_phone_and_pending_code_and_reissues_captcha(
    session, redis
):
    svc = build_services(session, redis)
    user = await make_user(session, 2, "BBB", pending_referral_code="AAA")
    await svc.verification.claim_phone(user, PHONE)
    await svc.verification.issue_captcha(user.telegram_id)

    await redis.flushall()  # simulate a Redis restart / eviction

    assert user.phone == PHONE
    assert user.pending_referral_code == "AAA"
    assert svc.verification.next_step(user) is OnboardingStep.CAPTCHA
    fresh = await svc.verification.issue_captcha(user.telegram_id)
    assert await svc.verification.submit_captcha(
        user.telegram_id, fresh.nonce, fresh.answer
    ) is CaptchaOutcome.OK


# ---------------------------------------------------- referral gating & payout
@pytest.mark.asyncio
async def test_no_referral_before_the_phone_step(session, redis):
    svc = build_services(session, redis)
    await make_user(session, 1, "AAA")
    invitee = await make_user(session, 2, "BBB", pending_referral_code="AAA")

    result = await svc.referral.process_pending(invitee)

    assert result.rewarded is False
    assert await svc.referrals.get_by_referred(invitee.id) is None
    assert invitee.pending_referral_code == "AAA"  # preserved for later


@pytest.mark.asyncio
async def test_no_referral_between_phone_and_captcha(session, redis):
    svc = build_services(session, redis)
    await make_user(session, 1, "AAA")
    invitee = await make_user(session, 2, "BBB", pending_referral_code="AAA")
    await svc.verification.claim_phone(invitee, PHONE)

    result = await svc.referral.process_pending(invitee)

    assert result.rewarded is False
    assert await svc.referrals.get_by_referred(invitee.id) is None
    assert invitee.pending_referral_code == "AAA"


@pytest.mark.asyncio
async def test_full_verification_creates_exactly_one_rewarded_referral(session, redis):
    svc = build_services(session, redis)
    referrer = await make_user(session, 1, "AAA")
    invitee = await make_user(session, 2, "BBB", pending_referral_code="AAA")
    reward = await svc.referral.get_reward()

    result = await fully_verify(svc, invitee)
    await session.commit()

    assert result.completed is True
    assert result.referral.rewarded is True
    assert result.referral.amount == reward
    assert result.referral.referrer_telegram_id == referrer.telegram_id

    referral_row = await svc.referrals.get_by_referred(invitee.id)
    assert referral_row is not None
    assert referral_row.referrer_id == referrer.id
    assert invitee.referred_by_id == referrer.id
    assert invitee.pending_referral_code is None
    assert invitee.verification_completed_at is not None
    assert invitee.captcha_verified_at is not None

    wallet = await svc.wallet.get_or_create(referrer.id)
    assert wallet.balance == reward
    txs = await svc.wallet.history(referrer.id)
    assert len(txs) == 1
    assert txs[0].amount == reward
    assert txs[0].type is TransactionType.REFERRAL_REWARD
    assert txs[0].balance_after == reward

    stats = await svc.referral.stats(referrer)
    assert stats == {"invited": 1, "earned": reward}


@pytest.mark.asyncio
async def test_finalizing_twice_is_a_no_op(session, redis):
    svc = build_services(session, redis)
    referrer = await make_user(session, 1, "AAA")
    invitee = await make_user(session, 2, "BBB", pending_referral_code="AAA")
    reward = await svc.referral.get_reward()

    await fully_verify(svc, invitee)
    second = await svc.verification.finalize(invitee)

    assert second.already_completed is True
    assert second.completed is False
    assert second.referral.rewarded is False
    assert len(await svc.referrals.list_by_referrer(referrer.id)) == 1
    assert (await svc.wallet.get_or_create(referrer.id)).balance == reward
    assert len(await svc.wallet.history(referrer.id)) == 1


@pytest.mark.asyncio
async def test_self_referral_verifies_the_user_but_pays_nothing(session, redis):
    svc = build_services(session, redis)
    user = await make_user(session, 1, "AAA", pending_referral_code="AAA")

    result = await fully_verify(svc, user)

    assert result.completed is True
    assert result.referral.rewarded is False
    assert user.verification_completed_at is not None
    assert await svc.referrals.get_by_referred(user.id) is None


@pytest.mark.asyncio
async def test_unknown_referral_code_verifies_the_user_but_pays_nothing(session, redis):
    svc = build_services(session, redis)
    user = await make_user(session, 2, "BBB", pending_referral_code="NOPE")

    result = await fully_verify(svc, user)

    assert result.completed is True
    assert result.referral.rewarded is False
    assert user.verification_completed_at is not None
    # A terminal (unusable) code is cleared so it isn't retried forever.
    assert user.pending_referral_code is None


@pytest.mark.asyncio
async def test_user_with_no_pending_code_just_gets_verified(session, redis):
    svc = build_services(session, redis)
    user = await make_user(session, 2, "BBB")

    result = await fully_verify(svc, user)

    assert result.completed is True
    assert result.referral.rewarded is False
    assert await svc.referrals.get_by_referred(user.id) is None


@pytest.mark.asyncio
async def test_existing_user_cannot_acquire_a_referrer_later(session, redis):
    """``get_or_create`` only stashes a code for brand-new users."""
    from app.services.user_service import UserService

    svc = build_services(session, redis)
    await make_user(session, 1, "AAA")
    returning = await make_user(session, 2, "BBB")
    await session.commit()

    user_service = UserService(svc.users, svc.referrals)
    user, created = await user_service.get_or_create(
        2, username=None, full_name=None, start_referral_code="AAA"
    )

    assert created is False
    assert user.id == returning.id
    assert user.pending_referral_code is None

    result = await fully_verify(svc, user)
    assert result.referral.rewarded is False


@pytest.mark.asyncio
async def test_already_referred_user_is_never_rewarded_again(session, redis):
    svc = build_services(session, redis)
    referrer = await make_user(session, 1, "AAA")
    invitee = await make_user(session, 2, "BBB", pending_referral_code="AAA")
    reward = await svc.referral.get_reward()
    await fully_verify(svc, invitee)

    # Simulate a second deep-link attempt after verification.
    invitee.pending_referral_code = "AAA"
    result = await svc.referral.process_pending(invitee)

    assert result.rewarded is False
    assert len(await svc.referrals.list_by_referrer(referrer.id)) == 1
    assert (await svc.wallet.get_or_create(referrer.id)).balance == reward


@pytest.mark.asyncio
async def test_stats_reset_does_not_reopen_the_reward_path(session, redis):
    """``counted=False`` zeroes the *display* only; the relation still blocks."""
    svc = build_services(session, redis)
    referrer = await make_user(session, 1, "AAA")
    invitee = await make_user(session, 2, "BBB", pending_referral_code="AAA")
    reward = await svc.referral.get_reward()
    await fully_verify(svc, invitee)

    await svc.referral.reset_user_statistics(referrer)
    assert await svc.referral.stats(referrer) == {"invited": 0, "earned": 0}

    # Even with the relation "uncounted" and the link cleared, no second payout.
    invitee.referred_by_id = None
    again = await svc.referral.link_and_reward(invitee, "AAA")

    assert again.rewarded is False
    assert (await svc.wallet.get_or_create(referrer.id)).balance == reward
    assert await svc.referrals.get_by_referred(invitee.id) is not None


@pytest.mark.asyncio
async def test_notification_failure_does_not_undo_a_committed_payout(session, redis):
    """Announcements run after the commit, so a dead Telegram send is harmless."""
    from app.handlers.user.common import announce_referral

    svc = build_services(session, redis)
    referrer = await make_user(session, 1, "AAA")
    invitee = await make_user(session, 2, "BBB", pending_referral_code="AAA")
    reward = await svc.referral.get_reward()

    result = await fully_verify(svc, invitee)
    await session.commit()

    class DeadBot:
        async def send_message(self, *a, **k):
            raise TelegramAPIError(method=None, message="bot blocked")

        async def send_photo(self, *a, **k):
            raise TelegramAPIError(method=None, message="bot blocked")

    await announce_referral(svc, DeadBot(), invitee, result.referral)

    assert (await svc.wallet.get_or_create(referrer.id)).balance == reward
    assert len(await svc.wallet.history(referrer.id)) == 1


# --------------------------------------------------------- restart / recovery
@pytest.mark.asyncio
async def test_step_is_recovered_from_mysql_after_a_restart(file_db, redis):
    """A brand-new session (as after a restart) resumes the right step."""
    async with file_db() as first:
        svc = build_services(first, redis)
        user = await make_user(first, 2, "BBB", pending_referral_code="AAA")
        await make_user(first, 1, "AAA")
        await svc.verification.claim_phone(user, PHONE)
        await first.commit()

    await redis.flushall()  # Redis and FSM are gone too

    async with file_db() as second:
        svc = build_services(second, redis)
        reloaded = await svc.users.get_by_telegram_id(2)
        assert svc.verification.next_step(reloaded) is OnboardingStep.CAPTCHA
        assert reloaded.pending_referral_code == "AAA"

        await solve_captcha(svc, reloaded)
        result = await svc.verification.finalize(reloaded)
        await second.commit()
        assert result.referral.rewarded is True


@pytest.mark.asyncio
async def test_restart_after_commit_does_not_pay_twice(file_db, redis):
    async with file_db() as first:
        svc = build_services(first, redis)
        referrer = await make_user(first, 1, "AAA")
        invitee = await make_user(first, 2, "BBB", pending_referral_code="AAA")
        reward = await svc.referral.get_reward()
        await fully_verify(svc, invitee)
        await first.commit()

    async with file_db() as second:
        svc = build_services(second, redis)
        reloaded = await svc.users.get_by_telegram_id(2)
        assert svc.verification.next_step(reloaded) is OnboardingStep.DONE

        repeat = await svc.verification.finalize(reloaded)
        await second.commit()

        assert repeat.already_completed is True
        assert (await svc.wallet.get_or_create(referrer.id)).balance == reward
        assert len(await svc.wallet.history(referrer.id)) == 1


@pytest.mark.asyncio
async def test_preexisting_phone_without_stamp_still_requires_the_contact_step(
    session, redis
):
    """A hand-entered legacy phone must never auto-verify an account."""
    svc = build_services(session, redis)
    legacy = await make_user(session, 3, "CCC", phone=OTHER_PHONE)

    assert legacy.verification_completed_at is None
    assert svc.verification.next_step(legacy) is OnboardingStep.PHONE
    assert svc.verification.is_complete(legacy) is False


# ----------------------------------------------------------- wallet integrity
@pytest.mark.asyncio
async def test_two_invitees_for_one_referrer_both_pay(session, redis):
    svc = build_services(session, redis)
    referrer = await make_user(session, 1, "AAA")
    first = await make_user(session, 2, "BBB", pending_referral_code="AAA")
    second = await make_user(session, 3, "CCC", pending_referral_code="AAA")
    reward = await svc.referral.get_reward()

    await fully_verify(svc, first, PHONE)
    await fully_verify(svc, second, OTHER_PHONE)
    await session.commit()

    assert (await svc.wallet.get_or_create(referrer.id)).balance == 2 * reward
    history = await svc.wallet.history(referrer.id)
    assert len(history) == 2
    # Newest first: running balances must be exact, with no lost update.
    assert [tx.balance_after for tx in history] == [2 * reward, reward]
    assert len(await svc.referrals.list_by_referrer(referrer.id)) == 2
    assert await svc.referral.stats(referrer) == {
        "invited": 2,
        "earned": 2 * reward,
    }


@pytest.mark.asyncio
async def test_locked_wallet_read_sees_committed_writes_from_another_session(
    file_db, redis
):
    """The locking read must not hand back a stale identity-mapped balance.

    Without ``populate_existing`` the second session would keep the balance it
    loaded earlier and overwrite the other session's credit — the lost update
    this guards against.
    """
    from app.core.constants import TransactionType

    async with file_db() as sa, file_db() as sb:
        svc_a, svc_b = build_services(sa, redis), build_services(sb, redis)
        user = await make_user(sa, 1, "AAA")
        await sa.commit()

        # Session B loads the wallet early (balance 0) and holds the object.
        await svc_b.wallet.get_or_create(user.id)

        await svc_a.wallet.credit(user.id, 5_000, TransactionType.REFERRAL_REWARD)
        await sa.commit()

        await svc_b.wallet.credit(user.id, 3_000, TransactionType.REFERRAL_REWARD)
        await sb.commit()

    async with file_db() as check:
        svc = build_services(check, redis)
        wallet = await svc.wallet.get_or_create(user.id)
        assert wallet.balance == 8_000
        assert [tx.balance_after for tx in await svc.wallet.history(user.id)] == [
            8_000,
            5_000,
        ]
