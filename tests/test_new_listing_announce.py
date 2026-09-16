"""The public «اکانت جدید برای فروش» announcement: the green «خرید» link under it,
and its mirror into the sales channel."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.config import Settings, settings
from app.handlers.account_form import _VIEW_PROMPT, _post_new_listing_to_channel
from app.keyboards.callbacks import AccountCB
from app.keyboards.inline import new_listing_announce_menu

CHANNEL_ID = -1003783566987


class FakeBot:
    """Records every send; ``fail`` makes the first send raise."""

    def __init__(self, fail: Exception | None = None) -> None:
        self.calls: list[tuple] = []
        self.fail = fail

    async def me(self):
        return SimpleNamespace(username="shop_bot")

    def _record(self, *call) -> None:
        if self.fail is not None:
            exc, self.fail = self.fail, None
            raise exc
        self.calls.append(call)

    async def send_photo(self, chat_id, photo, **kwargs):
        self._record("photo", chat_id, photo, kwargs)

    async def send_media_group(self, chat_id, media):
        self._record("album", chat_id, media)

    async def send_message(self, chat_id, text, **kwargs):
        self._record("message", chat_id, text, kwargs)


def _buttons(markup):
    return [button for row in markup.inline_keyboard for button in row]


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


def test_defaults_point_at_the_sales_channel_and_admin_chat():
    configured = Settings(_env_file=None)
    assert configured.listing_channel_id == CHANNEL_ID
    assert configured.listing_buy_url == "https://t.me/ffshah_bot"


@pytest.mark.asyncio
async def test_channel_gets_the_same_album_and_text(monkeypatch):
    monkeypatch.setattr(settings, "listing_channel_id", CHANNEL_ID)
    bot = FakeBot()

    await _post_new_listing_to_channel(bot, 7, "body", None, ["f1", "f2"], admin_chat_id=1)

    album, prompt = bot.calls
    assert album[:2] == ("album", CHANNEL_ID)
    assert [item.media for item in album[2]] == ["f1", "f2"]
    assert album[2][0].caption == "body"
    assert prompt[:3] == ("message", CHANNEL_ID, _VIEW_PROMPT)
    assert [b.url for b in _buttons(prompt[3]["reply_markup"])] == [
        settings.listing_buy_url,
        "https://t.me/shop_bot",
    ]


@pytest.mark.asyncio
async def test_single_image_is_one_captioned_photo_with_buttons(monkeypatch):
    monkeypatch.setattr(settings, "listing_channel_id", CHANNEL_ID)
    bot = FakeBot()

    await _post_new_listing_to_channel(bot, 7, "body", None, ["f1"], admin_chat_id=1)

    (photo,) = bot.calls
    assert photo[:3] == ("photo", CHANNEL_ID, "f1")
    assert photo[3]["caption"] == "body"
    assert _buttons(photo[3]["reply_markup"])[0].url == settings.listing_buy_url


@pytest.mark.asyncio
async def test_failed_channel_post_warns_the_posting_admin(monkeypatch):
    monkeypatch.setattr(settings, "listing_channel_id", CHANNEL_ID)
    bot = FakeBot(fail=RuntimeError("Forbidden: bot is not a member of the <channel>"))

    await _post_new_listing_to_channel(bot, 7, "body", None, ["f1", "f2"], admin_chat_id=42)

    (warning,) = bot.calls
    assert warning[:2] == ("message", 42)
    assert "#7" in warning[2]
    assert "&lt;channel&gt;" in warning[2]


@pytest.mark.asyncio
async def test_zero_channel_id_disables_the_mirror(monkeypatch):
    monkeypatch.setattr(settings, "listing_channel_id", 0)
    bot = FakeBot()

    await _post_new_listing_to_channel(bot, 7, "body", None, ["f1"], admin_chat_id=1)

    assert bot.calls == []
