"""The public «اکانت جدید برای فروش» announcement: the green «خرید» link under it,
and its mirror into every active advertising channel."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.handlers import account_form
from app.handlers.account_form import _VIEW_PROMPT, _post_new_listing_to_channels
from app.keyboards.callbacks import AccountCB
from app.keyboards.inline import new_listing_announce_menu

ADMIN_CHAT = 42
BUY = "https://t.me/picked_admin"


class FakeBot:
    """Records every send; a chat listed in ``fail`` raises on its first send."""

    def __init__(self, fail: dict[int, Exception] | None = None) -> None:
        self.calls: list[tuple] = []
        self.fail = dict(fail or {})

    async def me(self):
        return SimpleNamespace(id=999, username="shop_bot")

    def _record(self, kind, chat_id, *rest) -> None:
        if chat_id in self.fail:
            raise self.fail.pop(chat_id)
        self.calls.append((kind, chat_id, *rest))

    async def send_photo(self, chat_id, photo, **kwargs):
        self._record("photo", chat_id, photo, kwargs)

    async def send_media_group(self, chat_id, media):
        self._record("album", chat_id, media)

    async def send_message(self, chat_id, text, **kwargs):
        self._record("message", chat_id, text, kwargs)


def _buttons(markup):
    return [button for row in markup.inline_keyboard for button in row]


def _targets(monkeypatch, targets):
    async def fake_targets():
        if isinstance(targets, Exception):
            raise targets
        return targets

    monkeypatch.setattr(account_form, "_ad_channel_targets", fake_targets)


def test_users_get_green_buy_link_above_the_shop_button():
    markup = new_listing_announce_menu("https://t.me/ffshah_bot")

    assert [len(row) for row in markup.inline_keyboard] == [1, 1]
    buy, view = _buttons(markup)
    assert (buy.text, buy.url, buy.style) == ("✅ خرید", "https://t.me/ffshah_bot", "success")
    assert view.text == "🛒 مشاهده اکانت‌ها"
    assert view.callback_data == AccountCB(action="ready").pack()
    assert view.style == "primary"


def test_channel_keyboard_uses_links_only():
    """Callback buttons are dead in a channel, so every CTA there is a URL."""
    markup = new_listing_announce_menu("https://t.me/ffshah_bot", view_url="https://t.me/shop_bot")

    buy, view = _buttons(markup)
    assert buy.url == "https://t.me/ffshah_bot"
    assert (view.text, view.url, view.callback_data) == (
        "🛒 مشاهده اکانت‌ها",
        "https://t.me/shop_bot",
        None,
    )


@pytest.mark.parametrize("username", ["ffshah_bot", "@ffshah_bot", " @ffshah_bot "])
def test_buy_url_tolerates_at_sign(username):
    configured = Settings(_env_file=None, LISTING_BUY_USERNAME=username)
    assert configured.listing_buy_url == "https://t.me/ffshah_bot"


def test_buy_url_defaults_to_vasete_shah():
    assert Settings(_env_file=None).listing_buy_url == "https://t.me/vasete_shah"


@pytest.mark.asyncio
async def test_every_ad_channel_gets_the_same_album_and_text(monkeypatch):
    _targets(monkeypatch, [(-1001, "A"), (-1002, "B")])
    bot = FakeBot()

    await _post_new_listing_to_channels(bot, 7, "body", None, ["f1", "f2"], ADMIN_CHAT, BUY)

    assert [(kind, chat) for kind, chat, *_ in bot.calls] == [
        ("album", -1001),
        ("message", -1001),
        ("album", -1002),
        ("message", -1002),
    ]
    for kind, _chat, *rest in bot.calls:
        if kind == "album":
            media = rest[0]
            assert [item.media for item in media] == ["f1", "f2"]
            assert media[0].caption == "body"
        else:
            text, kwargs = rest
            assert text == _VIEW_PROMPT
            assert [b.url for b in _buttons(kwargs["reply_markup"])] == [
                BUY,
                "https://t.me/shop_bot",
            ]


@pytest.mark.asyncio
async def test_single_image_is_one_captioned_photo_with_buttons(monkeypatch):
    _targets(monkeypatch, [(-1001, "A")])
    bot = FakeBot()

    await _post_new_listing_to_channels(bot, 7, "body", None, ["f1"], ADMIN_CHAT, BUY)

    (photo,) = bot.calls
    assert photo[:3] == ("photo", -1001, "f1")
    assert photo[3]["caption"] == "body"
    assert _buttons(photo[3]["reply_markup"])[0].url == BUY


@pytest.mark.asyncio
async def test_a_failing_channel_does_not_stop_the_others(monkeypatch):
    _targets(monkeypatch, [(-1001, "<Broken>"), (-1002, "Good")])
    bot = FakeBot(fail={-1001: RuntimeError("Forbidden: bot is not a member")})

    await _post_new_listing_to_channels(bot, 7, "body", None, ["f1"], ADMIN_CHAT, BUY)

    sent = [(kind, chat) for kind, chat, *_ in bot.calls]
    assert ("photo", -1002) in sent
    warning = bot.calls[-1]
    assert warning[:2] == ("message", ADMIN_CHAT)
    assert "#7" in warning[2]
    assert "&lt;Broken&gt;" in warning[2]
    assert "Forbidden: bot is not a member" in warning[2]
    assert "Good" not in warning[2]


@pytest.mark.asyncio
async def test_no_ad_channels_means_nothing_is_sent(monkeypatch):
    _targets(monkeypatch, [])
    bot = FakeBot()

    await _post_new_listing_to_channels(bot, 7, "body", None, ["f1"], ADMIN_CHAT, BUY)

    assert bot.calls == []


@pytest.mark.asyncio
async def test_unreadable_channel_list_warns_the_admin(monkeypatch):
    _targets(monkeypatch, RuntimeError("db down"))
    bot = FakeBot()

    await _post_new_listing_to_channels(bot, 7, "body", None, ["f1"], ADMIN_CHAT, BUY)

    (warning,) = bot.calls
    assert warning[:2] == ("message", ADMIN_CHAT)
    assert "db down" in warning[2]
