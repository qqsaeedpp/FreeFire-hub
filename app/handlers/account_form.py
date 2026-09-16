"""Unified account-listing form, shared by the admin 'add account' entry and the
user 'sell account' entry.

Both paths walk the exact same FSM (``AccountFormFlow``) and create the exact same
``Account`` model. The only difference is the resulting status and who is notified:

* admin → account is published straight to the shop (``AVAILABLE``).
* user  → account is parked as ``PENDING_REVIEW`` and the admin is offered two
  actions: buy it directly, or push it into the public shop.
"""
from __future__ import annotations

import asyncio
from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.container import Services
from app.core.config import settings
from app.core.constants import AccountStatus
from app.core.database import get_sessionmaker
from app.core.logger import get_logger
from app.filters.admin import IsAdmin
from app.keyboards.callbacks import AdminCB
from app.keyboards.inline import admin_sale_review, cancel_only, new_listing_announce_menu
from app.keyboards.reply import build_main_menu
from app.filters.buttons import MainBtn
from app.services.account_service import is_account_visible_for_users
from app.services.button_service import BTN_KEY_SELL_ACCOUNT
from app.models.user import User
from app.services.notification_service import NotificationService
from app.states.user_states import AccountFormFlow
from app.utils.entities import (
    EntityCard,
    caption_entity_kwargs,
    dump_entities,
    entities_for_storage,
    entity_kwargs,
    has_custom_emoji,
    load_entities,
    normalize_with_entities,
)
from app.utils.helpers import (
    edit_or_answer,
    format_toman,
    is_admin_user,
    parse_images,
    safe_answer,
    sale_request_caption,
    send_album,
    send_listing_card,
    user_ref,
)
from app.utils.validators import parse_price

router = Router(name="account_form")
log = get_logger("account.broadcast")

_SKIP = {"-", "ندارم", "خالی"}

# ---- Public new-listing broadcast (additive notification layer) ----------
# Pause between sends to stay within Telegram's flood limits (matches the admin
# broadcast cadence).
_SEND_DELAY = 0.05
# Telegram caption limit for a photo / album's first item. A longer body rides in
# a separate follow-up text message (which allows up to 4096 characters).
_CAPTION_LIMIT = 1024
_TEXT_LIMIT = 4096
# Prompt that carries the glass CTA when the announcement went out as an album
# (media groups can't hold an inline keyboard).
_VIEW_PROMPT = "🛒 برای مشاهده و خرید این اکانت روی دکمه زیر بزنید:"

# Detached broadcast tasks are kept referenced so the event loop can't garbage-
# collect them mid-send (same pattern as the admin broadcast / backup handlers).
_BG_TASKS: set[asyncio.Task] = set()


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _BG_TASKS.add(task)
    task.add_done_callback(_BG_TASKS.discard)


def _opt(text: str) -> str | None:
    text = text.strip()
    return None if text in _SKIP else text


# ============================ ENTRY POINTS ============================
@router.callback_query(AdminCB.filter(F.action == "add_account"), IsAdmin())
async def admin_entry(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AccountFormFlow.title)
    await state.update_data(mode="admin")
    await edit_or_answer(
        callback.message, "➕ <b>افزودن اکانت</b>\nعنوان اکانت را وارد کنید:",
        reply_markup=cancel_only(),
    )
    await callback.answer()


@router.message(MainBtn(BTN_KEY_SELL_ACCOUNT))
async def user_entry(message: Message, state: FSMContext) -> None:
    await state.set_state(AccountFormFlow.title)
    await state.update_data(mode="user")
    await message.answer(
        "💰 <b>فروش اکانت</b>\nاطلاعات اکانت را مرحله‌به‌مرحله وارد کنید.\n\n"
        "عنوان اکانت را وارد کنید:",
        reply_markup=cancel_only(),
    )


# ============================ SHARED STEPS ============================
@router.message(AccountFormFlow.title, F.text)
async def step_title(message: Message, state: FSMContext) -> None:
    # Capture any premium (custom) emoji the admin typed alongside the title so it
    # can be replayed everywhere the listing is shown. normalize_with_entities
    # reproduces the old ``.strip()[:255]`` while keeping the entity offsets aligned;
    # entities_for_storage keeps them only when a custom_emoji is actually present
    # (so ordinary titles stay entity-free and render exactly as before).
    title, entities = normalize_with_entities(
        message.text, message.entities, max_len=255
    )
    await state.update_data(
        title=title,
        title_entities_json=dump_entities(entities_for_storage(entities)),
    )
    await state.set_state(AccountFormFlow.price)
    await message.answer("💵 قیمت (تومان):", reply_markup=cancel_only())


@router.message(AccountFormFlow.price, F.text)
async def step_price(message: Message, state: FSMContext) -> None:
    price = parse_price(message.text)
    if price is None or price <= 0:
        await message.answer("❌ قیمت نامعتبر است. یک عدد وارد کنید.")
        return
    await state.update_data(price=price)
    await state.set_state(AccountFormFlow.description)
    await message.answer(
        "📝 <b>توضیحات اکانت</b>\n"
        "تمام مشخصات اکانت (لول، تعداد الیت، اسکین‌ها، گان‌ها، آیتم‌های خاص و …) "
        "را در همین یک پیام بنویسید:",
        reply_markup=cancel_only(),
    )


@router.message(AccountFormFlow.description, F.text)
async def step_description(message: Message, state: FSMContext) -> None:
    # Same premium-emoji capture as the title (no length cap — descriptions aren't
    # truncated). Stored only when a custom_emoji is present, else NULL/unchanged.
    description, entities = normalize_with_entities(message.text, message.entities)
    await state.update_data(
        description=description,
        description_entities_json=dump_entities(entities_for_storage(entities)),
        images=[],
    )
    await state.set_state(AccountFormFlow.images)
    await message.answer(
        "📸 تصاویر اکانت را ارسال کنید (هر تعداد، حتی به‌صورت آلبوم).\n"
        "پس از اتمام دستور /done را بزنید.",
        reply_markup=cancel_only(),
    )


@router.message(AccountFormFlow.images, F.photo)
async def step_image(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    images = data.get("images", [])
    images.append(message.photo[-1].file_id)
    await state.update_data(images=images)
    # In an album each photo arrives separately; acknowledge only the first so the
    # user isn't spammed with one reply per image.
    if message.media_group_id is None or len(images) == 1:
        await message.answer(f"✅ تصویر {len(images)} ذخیره شد. برای پایان /done را بزنید.")


@router.message(AccountFormFlow.images, F.text == "/done")
async def step_images_done(
    message: Message, services: Services, state: FSMContext, db_user: User, bot
) -> None:
    data = await state.get_data()
    # Only the admin path collects the (encrypted) save/login credentials the shop
    # will deliver after a sale. A user selling their own account is never asked
    # for a password or login info here — that's arranged with the admin outside
    # this flow after agreement — so the user listing is finalized right away.
    if data.get("mode") == "admin":
        await state.set_state(AccountFormFlow.save_info)
        await message.answer(
            "💾 اطلاعات سیو اکانت را وارد کنید (رمزنگاری‌شده ذخیره می‌شود).\n"
            "اگر ندارید «-» بفرستید.",
            reply_markup=cancel_only(),
        )
        return
    await _finalize_listing(message, services, state, db_user, bot)


@router.message(AccountFormFlow.save_info, F.text)
async def step_save_info(message: Message, state: FSMContext) -> None:
    await state.update_data(save_info=_opt(message.text))
    await state.set_state(AccountFormFlow.login_info)
    await message.answer(
        "🔐 اطلاعات ورود اکانت را وارد کنید (ایمیل/رمز/روش ورود).\n"
        "رمزنگاری‌شده ذخیره و فقط پس از فروش تحویل می‌شود. اگر ندارید «-» بفرستید.",
        reply_markup=cancel_only(),
    )


@router.message(AccountFormFlow.login_info, F.text)
async def step_login_info(
    message: Message, services: Services, state: FSMContext, db_user: User, bot
) -> None:
    await state.update_data(login_info=_opt(message.text))
    await _finalize_listing(message, services, state, db_user, bot)


async def _finalize_listing(
    message: Message, services: Services, state: FSMContext, db_user: User, bot
) -> None:
    """Create the ``Account`` row and notify/ack, shared by both finish points.

    Admin finishes after the credential steps (``credentials``/``save_info`` set);
    the user finishes right after the images step (both stay ``None``). The status
    differs — admin listings go live (``AVAILABLE``), user listings wait for review
    (``PENDING_REVIEW``).
    """
    data = await state.get_data()
    is_admin = data.get("mode") == "admin"

    account = await services.account.create_listing(
        title=data["title"],
        price=data["price"],
        description=data["description"],
        images=",".join(data.get("images", [])),
        credentials=data.get("login_info"),
        save_info=data.get("save_info"),
        title_entities_json=data.get("title_entities_json"),
        description_entities_json=data.get("description_entities_json"),
        status=AccountStatus.AVAILABLE if is_admin else AccountStatus.PENDING_REVIEW,
        seller_user_id=None if is_admin else db_user.id,
    )
    await services.commit()
    await state.clear()

    if is_admin:
        # Confirm exactly whether the new listing is buyer-visible, using the same
        # predicate the shop query honors — so the admin is never left guessing why
        # an account did or didn't reach the buy-account list.
        if is_account_visible_for_users(account):
            await message.answer(
                f"✅ اکانت #{account.id} با موفقیت ثبت شد و در لیست خرید کاربران قابل مشاهده است."
            )
            # Additive notification layer: announce the new (buyer-visible) listing
            # to every active user and mirror it into the public sales channel.
            # Fire-and-forget so the admin's flow returns instantly; the account
            # row, the shop list and the admin notification system are untouched.
            # Only buyer-visible accounts are announced — the CTA opens the shop
            # list, where a price-invalid account wouldn't show.
            _broadcast_new_listing(bot, account, message.chat.id)
        else:
            await message.answer(
                f"⚠️ اکانت #{account.id} ثبت شد اما به دلیل نداشتن قیمت معتبر "
                "در لیست کاربران نمایش داده نمی‌شود."
            )
        return

    await safe_answer(
        message,
        f"✅ اکانت شما با شماره #{account.id} ثبت شد و برای بررسی به پشتیبانی ارسال شد.",
        reply_markup=await build_main_menu(services, is_admin_user(message, db_user)),
    )
    await _notify_admin_new_listing(bot, services, account, db_user)


async def _notify_admin_new_listing(bot, services: Services, account, seller: User) -> None:
    """Broadcast the new listing to every authorized admin (instant notification).

    Mirrors the diamond-order notification: each admin gets the «🔔 درخواست جدید
    فروش اکانت» card with images (album when multiple) plus the shared decision
    buttons. The buttons reuse :func:`admin_sale_review` so acting here is
    identical to acting from the «📦 سفارشات فروش اکانت کاربران» list. One admin
    failing (e.g. blocked the bot) must never break the others or the user flow.
    """
    notifier = NotificationService(bot)
    caption = sale_request_caption(account, seller)
    images = parse_images(account.images)
    keyboard = admin_sale_review(account.id)
    admin_ids = await services.admin.all_admin_ids()
    for admin_id in admin_ids:
        try:
            await send_listing_card(
                bot, admin_id, caption=caption, images=images, keyboard=keyboard
            )
        except Exception:  # noqa: BLE001 - one admin's failure must not affect others
            continue
    await notifier.log_event(
        "فروش اکانت",
        {"اکانت": f"#{account.id}", "فروشنده": user_ref(seller)},
    )


# ===================== PUBLIC NEW-LISTING BROADCAST =====================
def _new_listing_caption(account) -> str:
    """Public «اکانت جدید برای فروش اضافه شد» announcement body (HTML-safe).

    Title and description are user/admin-supplied free text, so they're escaped
    because messages go out with HTML parse mode. The whole body is capped at the
    text-message limit so an over-long description can never make the send fail.
    """
    title = escape(account.title or "-")
    description = escape(account.description or "-")
    caption = (
        "👤 <b>اکانت جدید برای فروش اضافه شد</b>\n\n"
        f"🆔 نام اکانت: {title}\n"
        f"💰 قیمت: {format_toman(account.price)}\n"
        f"📝 توضیحات: {description}"
    )
    return caption[:_TEXT_LIMIT]


def _new_listing_content(account) -> tuple[str, list | None]:
    """Announcement body as ``(text, entities)``.

    With no premium emoji the listing renders through the existing HTML caption
    (``entities is None`` → default HTML parse mode). When the title/description
    carry custom emoji, the same layout is rebuilt as plain text + entities (bold
    header included) so the premium emoji round-trip — sent with ``parse_mode=None``.
    """
    title_ents = load_entities(account.title_entities_json)
    desc_ents = load_entities(account.description_entities_json)
    if not has_custom_emoji(title_ents) and not has_custom_emoji(desc_ents):
        return _new_listing_caption(account), None
    return (
        EntityCard()
        .bold("👤 اکانت جدید برای فروش اضافه شد")
        .text("\n\n🆔 نام اکانت: ")
        .text(account.title or "-", title_ents)
        .text("\n💰 قیمت: ")
        .text(format_toman(account.price))
        .text("\n📝 توضیحات: ")
        .text(account.description or "-", desc_ents)
        .build()
    )


async def _active_recipient_ids() -> list[int]:
    """Snapshot every active, non-banned user's telegram id, then release the DB.

    Pulled in a short-lived session so the (possibly long) send loop afterwards
    never holds a database connection open — it touches Telegram only. Mirrors the
    audience the lottery already uses (``is_active`` and not banned).
    """
    async with get_sessionmaker()() as session:
        users = await Services(session).users.list_active()
        return [u.telegram_id for u in users]


async def _deliver_announcement(
    bot, chat_id: int, caption: str, caption_entities, images: list[str], keyboard
) -> None:
    """Send one recipient the announcement; raise on Telegram errors so the caller
    can count the failure.

    Image ``file_id``s are reused verbatim (never re-downloaded) and their order is
    preserved. One image rides as a captioned photo carrying the CTA; several go as
    an ordered media group (which can't hold a keyboard) followed by the CTA in its
    own message. A body longer than a photo caption is sent as text after the
    gallery, and a missing/stale image falls back to a text-only card — so the
    button always reaches the user.

    ``caption_entities`` (premium emoji) ride with the caption/text wherever it
    goes; the static CTA follow-up never needs them. They're ``None`` for ordinary
    listings, which then keep the default HTML parse mode.
    """
    if images and len(caption) <= _CAPTION_LIMIT:
        if len(images) == 1:
            await bot.send_photo(
                chat_id, images[0], caption=caption, reply_markup=keyboard,
                **caption_entity_kwargs(caption_entities),
            )
            return
        if await send_album(
            bot, chat_id, images, caption=caption, caption_entities=caption_entities
        ):
            await bot.send_message(chat_id, _VIEW_PROMPT, reply_markup=keyboard)
            return
        # Album rejected (stale file_id) → fall through to a text-only card.
    elif images:
        # Caption too long for a photo caption → gallery alone, full text follows.
        await send_album(bot, chat_id, images, caption=None)
    await bot.send_message(
        chat_id, caption, reply_markup=keyboard, **entity_kwargs(caption_entities)
    )


async def _run_new_listing_broadcast(
    bot, account_id: int, caption: str, caption_entities, images: list[str]
) -> None:
    """Deliver the new-listing announcement to every active user.

    Runs detached so the admin's listing flow returns instantly. A per-user failure
    (blocked bot, deactivated account, stale id) is logged and skipped so one bad
    recipient never halts the run, and a small pause between sends respects
    Telegram's flood limits.
    """
    try:
        recipient_ids = await _active_recipient_ids()
    except Exception as exc:  # noqa: BLE001 - a DB hiccup must not crash the task
        log.error("new_listing_broadcast_fetch_failed", account=account_id, error=str(exc))
        return

    keyboard = new_listing_announce_menu(settings.listing_buy_url)
    sent = 0
    failed = 0
    for tg_id in recipient_ids:
        try:
            await _deliver_announcement(
                bot, tg_id, caption, caption_entities, images, keyboard
            )
            sent += 1
        except Exception as exc:  # noqa: BLE001 - skip & log, keep broadcasting
            failed += 1
            log.warning(
                "new_listing_broadcast_user_failed", user=tg_id, error=str(exc)
            )
        await asyncio.sleep(_SEND_DELAY)
    log.info(
        "new_listing_broadcast_done",
        account=account_id,
        sent=sent,
        failed=failed,
        total=sent + failed,
    )


async def _post_new_listing_to_channel(
    bot,
    account_id: int,
    caption: str,
    caption_entities,
    images: list[str],
    admin_chat_id: int,
) -> None:
    """Mirror the new-listing announcement into the public sales channel.

    Goes through the same :func:`_deliver_announcement` as each user's copy, so the
    channel gets the identical body, ordered album and CTAs — except that
    «مشاهده اکانت‌ها» links into the bot, because a callback button is dead in a
    channel. Runs as its own detached task, so the post goes out right away instead
    of queueing behind the user broadcast. A failure (bot not an admin of the
    channel, wrong id) is logged and reported to the posting admin: it never touches
    the user broadcast, and never goes unnoticed.
    """
    channel_id = settings.listing_channel_id
    if not channel_id:
        return
    try:
        me = await bot.me()
        keyboard = new_listing_announce_menu(
            settings.listing_buy_url, view_url=f"https://t.me/{me.username}"
        )
        await _deliver_announcement(
            bot, channel_id, caption, caption_entities, images, keyboard
        )
    except Exception as exc:  # noqa: BLE001 - the listing is saved; report and stop
        log.error(
            "new_listing_channel_post_failed",
            account=account_id,
            channel=channel_id,
            error=str(exc),
        )
        await NotificationService(bot).notify_user(
            admin_chat_id,
            f"⚠️ اکانت #{account_id} در کانال منتشر نشد.\n"
            "مطمئن شوید ربات ادمین کانال است و اجازهٔ ارسال پیام دارد.\n"
            f"<code>{escape(str(exc))}</code>",
        )
        return
    log.info("new_listing_channel_posted", account=account_id, channel=channel_id)


def _broadcast_new_listing(bot, account, admin_chat_id: int) -> None:
    """Fire-and-forget public announcement of a freshly listed account.

    Reads the account's fields synchronously into a plain caption (+ its premium-
    emoji entities) and ``file_id`` list (so the detached tasks never touch the ORM
    object or its session), then spawns the channel mirror and the user send loop
    side by side. Purely additive: it never mutates the account, the shop list, or
    the existing admin notification system. ``admin_chat_id`` hears about a failed
    channel post.
    """
    caption, caption_entities = _new_listing_content(account)
    images = parse_images(account.images)
    _spawn(
        _post_new_listing_to_channel(
            bot, account.id, caption, caption_entities, images, admin_chat_id
        )
    )
    _spawn(
        _run_new_listing_broadcast(
            bot, account.id, caption, caption_entities, images
        )
    )
