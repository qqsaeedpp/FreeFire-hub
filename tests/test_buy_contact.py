"""The admin behind the green «✅ خرید» button: picked by the owner in
«👮 مدیریت ادمین‌ها ← 🛒 ادمین دکمهٔ خرید», defaulting to @vasete_shah."""
from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.constants import AdminRole
from app.handlers import account_form
from app.handlers.admin import admins as admin_handlers
from app.keyboards.callbacks import AdminMgmtCB
from app.models.admin import Admin
from app.models.admin_log import AdminLog
from app.models.user import User
from app.repositories.admins import AdminRepository
from app.repositories.app_settings import AppSettingRepository
from app.repositories.users import UserRepository
from app.services.admin_service import AdminEntry, AdminService
from app.services.buy_contact_service import (
    BuyContact,
    BuyContactError,
    BuyContactService,
)
from app.services.settings_service import KEY_LISTING_BUY_ADMIN, SettingsService

OWNER_ID = settings.admin_ids[0]  # the conftest ADMIN_ID
OWNER = 900


def _buttons(markup):
    return [button for row in markup.inline_keyboard for button in row]


@pytest.fixture
def store(session):
    return SettingsService(AppSettingRepository(session))


@pytest.fixture
def service(session, store):
    users = UserRepository(session)
    # redis=None: the roster is read straight from the database in tests.
    return BuyContactService(store, AdminService(AdminRepository(session), users), users)


async def _user(session, telegram_id, username, name="Name"):
    session.add(
        User(
            telegram_id=telegram_id,
            username=username,
            full_name=name,
            referral_code=f"R{telegram_id}",
        )
    )
    await session.flush()


async def _admin(session, user_id, username, name="Admin"):
    await _user(session, user_id, username, name)
    session.add(Admin(user_id=user_id, username=username, first_name=name, role=AdminRole.ADMIN))
    await session.flush()


# --------------------------------- service ---------------------------------
@pytest.mark.asyncio
async def test_default_is_vasete_shah(service):
    contact = await service.current()

    assert contact == BuyContact("vasete_shah")
    assert contact.is_default
    assert await service.url() == "https://t.me/vasete_shah"


@pytest.mark.asyncio
async def test_picking_an_admin_points_the_button_at_them(service, session, store):
    await _admin(session, 501, "seller_admin")

    picked = await service.select(501, changed_by=OWNER_ID)

    assert picked == BuyContact("seller_admin", 501)
    assert await service.url() == "https://t.me/seller_admin"
    assert await store.get(KEY_LISTING_BUY_ADMIN) == "501"
    (log,) = (await session.execute(select(AdminLog))).scalars().all()
    assert log.actor_id == OWNER_ID
    assert json.loads(log.payload)["field"] == KEY_LISTING_BUY_ADMIN


@pytest.mark.asyncio
async def test_owner_can_be_picked_too(service, session):
    await _user(session, OWNER_ID, "the_owner")

    await service.select(OWNER_ID, changed_by=OWNER_ID)

    assert await service.url() == "https://t.me/the_owner"


@pytest.mark.asyncio
async def test_link_follows_the_admins_current_username(service, session):
    await _admin(session, 501, "old_name")
    await service.select(501, changed_by=OWNER_ID)

    user = await UserRepository(session).get_by_telegram_id(501)
    user.username = "new_name"  # refreshed by the DB middleware on their next update
    await session.flush()

    assert await service.url() == "https://t.me/new_name"


@pytest.mark.asyncio
async def test_admin_without_username_cannot_be_picked(service, session, store):
    await _admin(session, 502, None)

    with pytest.raises(BuyContactError):
        await service.select(502, changed_by=OWNER_ID)
    assert await store.get(KEY_LISTING_BUY_ADMIN) is None


@pytest.mark.asyncio
async def test_non_admin_cannot_be_picked(service, session):
    await _user(session, 777, "just_a_user")

    with pytest.raises(BuyContactError):
        await service.select(777, changed_by=OWNER_ID)
    assert (await service.current()).is_default


@pytest.mark.asyncio
async def test_removed_admin_falls_back_to_the_default(service, session):
    await _admin(session, 501, "seller_admin")
    await service.select(501, changed_by=OWNER_ID)

    await AdminService(AdminRepository(session), UserRepository(session)).remove_admin(501)

    assert await service.current() == BuyContact("vasete_shah")


@pytest.mark.asyncio
async def test_admin_who_drops_their_username_falls_back(service, session):
    await _admin(session, 501, "seller_admin")
    await service.select(501, changed_by=OWNER_ID)

    user = await UserRepository(session).get_by_telegram_id(501)
    user.username = None
    await session.flush()

    assert (await service.current()).is_default


@pytest.mark.asyncio
async def test_reset_returns_to_the_default(service, session, store):
    await _admin(session, 501, "seller_admin")
    await service.select(501, changed_by=OWNER_ID)

    assert await service.reset(changed_by=OWNER_ID) == BuyContact("vasete_shah")
    assert await service.current() == BuyContact("vasete_shah")
    assert await store.get(KEY_LISTING_BUY_ADMIN) == ""


@pytest.mark.asyncio
async def test_listing_uses_the_default_when_lookup_fails():
    class Broken:
        class buy_contact:  # noqa: N801 - mimics the Services attribute
            @staticmethod
            async def url():
                raise RuntimeError("db down")

    assert await account_form._buy_url(Broken()) == settings.listing_buy_url


# ------------------------------- admin panel -------------------------------
def test_admin_list_has_the_buy_button_picker():
    buttons = _buttons(admin_handlers._list_markup([]))

    assert ("🛒 ادمین دکمهٔ خرید", AdminMgmtCB(action="buy_menu").pack()) in [
        (b.text, b.callback_data) for b in buttons
    ]


def _entry(user_id, username, name):
    return AdminEntry(
        user_id=user_id, username=username, first_name=name, role=AdminRole.ADMIN, removable=True
    )


def test_picker_marks_the_current_admin_and_skips_ones_without_username():
    entries = [
        _entry(OWNER, "boss", "Boss"),
        _entry(501, "seller_admin", "Seller"),
        _entry(502, None, "No handle"),
    ]

    buttons = _buttons(admin_handlers._buy_menu_markup(entries, BuyContact("seller_admin", 501)))

    assert [b.text for b in buttons] == [
        "@boss — Boss",
        "✅ @seller_admin — Seller",
        "↩️ بازگشت به پیش‌فرض (@vasete_shah)",
        "🔙 بازگشت",
    ]
    assert buttons[1].callback_data == AdminMgmtCB(action="buy_set", user_id=501).pack()
    assert buttons[2].callback_data == AdminMgmtCB(action="buy_reset").pack()
    assert buttons[3].callback_data == AdminMgmtCB(action="home").pack()


def test_picker_on_the_default_has_no_reset_and_marks_a_matching_admin():
    entries = [_entry(503, "Vasete_Shah", "Vasete"), _entry(501, "seller_admin", "Seller")]

    buttons = _buttons(admin_handlers._buy_menu_markup(entries, BuyContact("vasete_shah")))

    assert [b.text for b in buttons] == [
        "✅ @Vasete_Shah — Vasete",
        "@seller_admin — Seller",
        "🔙 بازگشت",
    ]
