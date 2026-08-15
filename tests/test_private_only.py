"""The bot must be invisible outside private chats, and must accept private
channels in the forced-join lock."""
from __future__ import annotations

import pytest
from aiogram.types import Chat

from app.middlewares.private_only import PrivateOnlyMiddleware
from app.services.channel_lock_service import ChannelAccessError, _parse_identifier


async def _run(chat_type: str | None):
    """Run the gate with the given chat type; returns the handler's result."""
    mw = PrivateOnlyMiddleware()

    async def handler(event, data):
        return "handled"

    data = {} if chat_type is None else {"event_chat": Chat(id=1, type=chat_type)}
    return await mw(handler, object(), data)


@pytest.mark.asyncio
async def test_private_chat_reaches_handler():
    assert await _run("private") == "handled"


@pytest.mark.parametrize("chat_type", ["group", "supergroup", "channel"])
@pytest.mark.asyncio
async def test_group_updates_are_dropped_silently(chat_type):
    # None = handler never ran; the middleware also sends nothing back, so the
    # bot neither replies nor reacts in groups.
    assert await _run(chat_type) is None


@pytest.mark.asyncio
async def test_event_without_chat_passes_through():
    """Chat-less updates (e.g. inline queries) keep their previous behavior."""
    assert await _run(None) == "handled"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("@mychannel", "@mychannel"),
        ("mychannel", "@mychannel"),
        ("https://t.me/mychannel", "@mychannel"),
        ("t.me/mychannel/", "@mychannel"),
        ("-1001234567890", -1001234567890),
    ],
)
def test_parse_identifier_accepts_public_forms(raw, expected):
    assert _parse_identifier(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "https://t.me/+AbCdEf123",  # private invite link
        "t.me/joinchat/AbCdEf123",  # legacy private invite link
        "   ",
    ],
)
def test_parse_identifier_rejects_unresolvable_input(raw):
    """Telegram cannot resolve an invite link to a chat id, so we must not try —
    the admin is told to forward a post from the private channel instead."""
    with pytest.raises(ChannelAccessError):
        _parse_identifier(raw)
