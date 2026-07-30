"""Guards for the verification gate's fragile edges.

The middleware's routing decisions hinge on two things that can silently drift:
the callback prefixes it lets through (if a factory is renamed, onboarding would
dead-end) and the lazily-imported helpers it calls while blocking (a module-level
import there would be circular, so the failure would only show at runtime).
"""
from __future__ import annotations

from types import SimpleNamespace

from app.keyboards.callbacks import ChannelCB, VerificationCB
from app.middlewares.verification import (
    _CHANNEL_CHECK_PREFIX,
    _VERIFY_PREFIX,
    VerificationMiddleware,
    _is_start,
)


def message(text: str) -> SimpleNamespace:
    return SimpleNamespace(text=text)


def test_start_is_recognized_in_all_its_forms():
    assert _is_start(message("/start"))
    assert _is_start(message("/start REF12345"))       # deep link
    assert _is_start(message("/start@FreeFire_Hubbot"))  # group-style mention
    assert _is_start(message("/START"))                 # case-insensitive


def test_other_input_is_not_mistaken_for_start():
    assert not _is_start(message("/menu"))
    assert not _is_start(message("/started"))
    assert not _is_start(message("👛 کیف پول"))
    assert not _is_start(message(""))
    assert not _is_start(message(None))


def test_captcha_callbacks_match_the_allowed_prefix():
    """Every button the captcha renders must survive the gate."""
    packed = VerificationCB(action="answer", nonce="abcdefghijk", choice=12).pack()
    assert packed.startswith(_VERIFY_PREFIX)
    # Telegram hard-limits callback_data to 64 bytes.
    assert len(packed.encode()) <= 64


def test_channel_recheck_callback_matches_the_allowed_prefix():
    """«✅ عضو شدم» must pass, or a channel-locked user can never reach onboarding."""
    assert ChannelCB(action="check").pack().startswith(_CHANNEL_CHECK_PREFIX)


def test_unrelated_callbacks_do_not_match_either_prefix():
    from app.keyboards.callbacks import NavCB, WalletTopUpCB

    for other in (NavCB(action="cancel").pack(), WalletTopUpCB(action="page").pack()):
        assert not other.startswith(_VERIFY_PREFIX)
        assert not other.startswith(_CHANNEL_CHECK_PREFIX)


def test_blocking_path_helpers_are_importable():
    """``_show_step`` imports these lazily; prove the deferred imports resolve."""
    from app.handlers.user.common import prompt_captcha, prompt_phone
    from app.services.verification_service import OnboardingStep
    from app.states.user_states import VerificationFlow

    assert callable(prompt_phone) and callable(prompt_captcha)
    assert OnboardingStep.PHONE and VerificationFlow.waiting_phone
    assert hasattr(VerificationMiddleware, "_show_step")
