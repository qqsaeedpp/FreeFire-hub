"""Advertising channels («📢 مدیریت کانال‌ها ← 📣 کانال‌های تبلیغ»): the admin
menus, the service that stores channels, and migration 0022 that carries the old
LISTING_CHANNEL_ID channel into the new list."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.handlers.admin import ad_channels as ad_handlers
from app.handlers.admin import channel_lock as lock_handlers
from app.handlers.admin.channels import channels_menu
from app.handlers.admin.panel import admin_menu
from app.keyboards.callbacks import AdChannelCB, AdminCB
from app.models.ad_channel import AdChannel
from app.repositories.ad_channels import AdChannelRepository
from app.services.ad_channel_service import AdChannelService, member_can_post
from app.services.channel_lock_service import ChannelAccessError

POSTER = SimpleNamespace(status="administrator", can_post_messages=True)


def _buttons(markup):
    return [button for row in markup.inline_keyboard for button in row]


class TgBot:
    """Just enough of ``aiogram.Bot`` for the channel service."""

    def __init__(self, chats: dict, member=POSTER) -> None:
        self.chats = chats
        self.member = member

    async def me(self):
        return SimpleNamespace(id=999, username="shop_bot")

    async def get_chat(self, key):
        if key not in self.chats:
            raise RuntimeError("Bad Request: chat not found")
        return self.chats[key]

    async def get_chat_member(self, chat_id, user_id):
        return self.member


def _chat(chat_id, title, username=None, kind="channel"):
    return SimpleNamespace(id=chat_id, title=title, username=username, type=kind)


@pytest.fixture
def service(session):
    return AdChannelService(AdChannelRepository(session))


# ------------------------------- admin menus -------------------------------
@pytest.mark.parametrize("is_owner", [False, True])
def test_panel_button_is_renamed_to_channel_management(is_owner):
    buttons = _buttons(admin_menu(is_owner))
    by_text = {b.text: b.callback_data for b in buttons}

    assert by_text["📢 مدیریت کانال‌ها"] == AdminCB(action="channels").pack()
    assert not any("تنظیم کانال قفل" in b.text for b in buttons)


def test_channel_management_holds_lock_then_ad_channels():
    buttons = _buttons(channels_menu())

    assert [(b.text, b.callback_data) for b in buttons] == [
        ("🔒 تنظیم کانال قفل", AdminCB(action="channel_lock").pack()),
        ("📣 کانال‌های تبلیغ", AdminCB(action="ad_channels").pack()),
        ("🔙 بازگشت", AdminCB(action="back_home").pack()),
    ]


def test_lock_list_back_returns_to_channel_management():
    back = _buttons(lock_handlers._list_markup([]))[-1]
    assert back.callback_data == AdminCB(action="channels").pack()


def test_ad_list_shows_each_channel_then_add_then_back():
    channels = [
        AdChannel(id=1, title="Shop", chat_id=-1001, is_active=True),
        AdChannel(id=2, title="Old", chat_id=-1002, is_active=False),
    ]
    buttons = _buttons(ad_handlers._list_markup(channels))

    assert [b.text for b in buttons] == ["🟢 Shop", "🔴 Old", "➕ افزودن کانال", "🔙 بازگشت"]
    assert buttons[0].callback_data == AdChannelCB(action="view", channel_id=1).pack()
    assert buttons[-1].callback_data == AdminCB(action="channels").pack()


def test_detail_text_escapes_the_title():
    channel = AdChannel(id=1, title="<b>x</b>", chat_id=-1001, username=None, is_active=True)
    assert "&lt;b&gt;x&lt;/b&gt;" in ad_handlers._detail_text(channel)


# ---------------------------- posting permission ----------------------------
@pytest.mark.parametrize(
    ("chat_type", "member", "expected"),
    [
        ("channel", POSTER, True),
        ("channel", SimpleNamespace(status="administrator", can_post_messages=False), False),
        ("channel", SimpleNamespace(status="member"), False),
        ("channel", SimpleNamespace(status="left"), False),
        ("supergroup", SimpleNamespace(status="member"), True),
        ("group", SimpleNamespace(status="administrator"), True),
        (
            "supergroup",
            SimpleNamespace(status="restricted", is_member=True, can_send_messages=False),
            False,
        ),
        ("supergroup", SimpleNamespace(status="kicked"), False),
    ],
)
def test_member_can_post(chat_type, member, expected):
    assert member_can_post(chat_type, member) is expected


# --------------------------------- service ---------------------------------
@pytest.mark.asyncio
async def test_add_by_forwarded_id_stores_an_active_channel(service):
    bot = TgBot({-1001: _chat(-1001, "Private shop")})

    channel = await service.add_channel_by_id(bot, -1001)

    assert (channel.title, channel.chat_id, channel.username, channel.is_active) == (
        "Private shop",
        -1001,
        None,
        True,
    )
    assert [c.chat_id for c in await service.list_active()] == [-1001]


@pytest.mark.asyncio
async def test_add_by_username_or_link(service):
    bot = TgBot({"@ffshop": _chat(-1002, "FF Shop", username="ffshop")})

    channel = await service.add_channel(bot, "https://t.me/ffshop")

    assert (channel.chat_id, channel.username) == (-1002, "ffshop")


@pytest.mark.asyncio
async def test_channel_where_bot_cannot_post_is_refused(service):
    bot = TgBot(
        {-1001: _chat(-1001, "No rights")},
        member=SimpleNamespace(status="administrator", can_post_messages=False),
    )

    with pytest.raises(ChannelAccessError):
        await service.add_channel_by_id(bot, -1001)
    assert await service.list_all() == []


@pytest.mark.asyncio
async def test_unknown_channel_is_refused(service):
    with pytest.raises(ChannelAccessError):
        await service.add_channel(TgBot({}), "-1009")
    assert await service.list_all() == []


@pytest.mark.asyncio
async def test_re_adding_reactivates_instead_of_duplicating(service):
    bot = TgBot({-1001: _chat(-1001, "Shop")})
    channel = await service.add_channel_by_id(bot, -1001)
    await service.toggle_channel(channel)
    assert await service.list_active() == []

    bot.chats[-1001] = _chat(-1001, "Shop renamed")
    again = await service.add_channel_by_id(bot, -1001)

    assert again.id == channel.id
    assert again.title == "Shop renamed"
    assert [c.chat_id for c in await service.list_active()] == [-1001]
    assert len(await service.list_all()) == 1


@pytest.mark.asyncio
async def test_inactive_channels_are_not_posted_to(service):
    bot = TgBot({-1001: _chat(-1001, "A"), -1002: _chat(-1002, "B")})
    first = await service.add_channel_by_id(bot, -1001)
    await service.add_channel_by_id(bot, -1002)

    await service.toggle_channel(first)

    assert [c.chat_id for c in await service.list_active()] == [-1002]
    assert [c.chat_id for c in await service.list_all()] == [-1001, -1002]


@pytest.mark.asyncio
async def test_carried_over_channel_gets_its_real_title(service, session):
    session.add(AdChannel(title="-1003783566987", chat_id=-1003783566987, is_active=True))
    await session.flush()
    bot = TgBot({-1003783566987: _chat(-1003783566987, "FF Hub", username="ffhub")})

    assert await service.resolve_placeholder_titles(bot) is True

    (channel,) = await service.list_all()
    assert (channel.title, channel.username, channel.title_unresolved) == (
        "FF Hub",
        "ffhub",
        False,
    )
    # Nothing left to resolve → no further Telegram calls change anything.
    assert await service.resolve_placeholder_titles(TgBot({})) is False


@pytest.mark.asyncio
async def test_unreachable_placeholder_is_kept_for_a_later_retry(service, session):
    session.add(AdChannel(title="-1001", chat_id=-1001, is_active=True))
    await session.flush()

    assert await service.resolve_placeholder_titles(TgBot({})) is False
    (channel,) = await service.list_all()
    assert channel.title_unresolved


@pytest.mark.asyncio
async def test_access_test_reports_lost_rights_and_refreshes_title(service):
    bot = TgBot({-1001: _chat(-1001, "Shop")})
    channel = await service.add_channel_by_id(bot, -1001)

    bot.chats[-1001] = _chat(-1001, "Shop v2")
    bot.member = SimpleNamespace(status="member")

    assert await service.check_and_refresh(bot, channel) is False
    assert channel.title == "Shop v2"
    assert await service.check_and_refresh(TgBot({}), channel) is False


@pytest.mark.asyncio
async def test_remove_channel(service):
    bot = TgBot({-1001: _chat(-1001, "Shop")})
    channel = await service.add_channel_by_id(bot, -1001)

    await service.remove_channel(channel)

    assert await service.list_all() == []


# ------------------------------- migration 0022 -------------------------------
MIGRATION = (
    Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0022_ad_channels.py"
)


def load_migration():
    spec = importlib.util.spec_from_file_location("migration_0022", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def migrate(tmp_path, monkeypatch):
    """Run 0022 against a throwaway SQLite db, from a dir without a ``.env``.

    ``migrate()`` upgrades and returns the ``ad_channels`` rows;
    ``migrate("downgrade")`` reverts.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LISTING_CHANNEL_ID", raising=False)
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'm.db'}")
    conn = engine.connect()
    module = load_migration()

    def run(step: str = "upgrade"):
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            getattr(module, step)()
        if step != "upgrade":
            return None
        return conn.exec_driver_sql(
            "SELECT title, chat_id, username, is_active FROM ad_channels ORDER BY id"
        ).fetchall()

    yield run
    conn.close()
    engine.dispose()


def test_chain_links_to_the_previous_revision():
    module = load_migration()
    assert module.revision == "0022_ad_channels"
    assert module.down_revision == "0021_user_verification"


def test_current_channel_is_carried_into_the_list(migrate):
    """No env override → the channel the bot already posts to (the old default)."""
    assert migrate() == [("-1003783566987", -1003783566987, None, 1)]


def test_env_override_is_carried_over(migrate, monkeypatch):
    monkeypatch.setenv("LISTING_CHANNEL_ID", "-1009998887776")
    assert migrate() == [("-1009998887776", -1009998887776, None, 1)]


def test_dotenv_value_is_carried_over(migrate, tmp_path):
    (tmp_path / ".env").write_text("LISTING_CHANNEL_ID=-1005554443332\n", encoding="utf-8")
    assert migrate() == [("-1005554443332", -1005554443332, None, 1)]


@pytest.mark.parametrize("raw", ["0", "not-a-number"])
def test_disabled_mirror_carries_nothing(migrate, monkeypatch, raw):
    monkeypatch.setenv("LISTING_CHANNEL_ID", raw)
    assert migrate() == []


def test_downgrade_drops_the_table(migrate):
    migrate()
    migrate("downgrade")
    # Re-running the upgrade only works if the table and its index are gone.
    assert migrate() == [("-1003783566987", -1003783566987, None, 1)]
