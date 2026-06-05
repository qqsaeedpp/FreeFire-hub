"""Admin: add account listings and edit diamond plan prices."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.container import Services
from app.filters.admin import IsAdmin
from app.keyboards.callbacks import AdminCB
from app.keyboards.inline import cancel_only
from app.states.admin_states import AddAccountFlow, EditDiamondPrice
from app.utils.helpers import edit_or_answer, format_toman
from app.utils.validators import parse_price

router = Router(name="admin_accounts")


# ============================ ADD ACCOUNT ============================
@router.callback_query(AdminCB.filter(F.action == "add_account"), IsAdmin())
async def add_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddAccountFlow.title)
    await edit_or_answer(
        callback.message, "➕ عنوان اکانت را وارد کنید:", reply_markup=cancel_only()
    )
    await callback.answer()


@router.message(AddAccountFlow.title, F.text, IsAdmin())
async def add_title(message: Message, state: FSMContext) -> None:
    await state.update_data(title=message.text.strip())
    await state.set_state(AddAccountFlow.price)
    await message.answer("💵 قیمت (تومان):", reply_markup=cancel_only())


@router.message(AddAccountFlow.price, F.text, IsAdmin())
async def add_price(message: Message, state: FSMContext) -> None:
    price = parse_price(message.text)
    if price is None or price <= 0:
        await message.answer("قیمت نامعتبر.")
        return
    await state.update_data(price=price)
    await state.set_state(AddAccountFlow.level)
    await message.answer("🎚 لول اکانت:", reply_markup=cancel_only())


@router.message(AddAccountFlow.level, F.text, IsAdmin())
async def add_level(message: Message, state: FSMContext) -> None:
    await state.update_data(level=parse_price(message.text) or 0)
    await state.set_state(AddAccountFlow.skins)
    await message.answer("🎽 تعداد اسکین:", reply_markup=cancel_only())


@router.message(AddAccountFlow.skins, F.text, IsAdmin())
async def add_skins(message: Message, state: FSMContext) -> None:
    await state.update_data(skins=parse_price(message.text) or 0)
    await state.set_state(AddAccountFlow.elite)
    await message.answer("⭐️ تعداد الیت پس:", reply_markup=cancel_only())


@router.message(AddAccountFlow.elite, F.text, IsAdmin())
async def add_elite(message: Message, state: FSMContext) -> None:
    await state.update_data(elite=parse_price(message.text) or 0)
    await state.set_state(AddAccountFlow.gun_skins)
    await message.answer("🔫 تعداد اسکین اسلحه:", reply_markup=cancel_only())


@router.message(AddAccountFlow.gun_skins, F.text, IsAdmin())
async def add_gun_skins(message: Message, state: FSMContext) -> None:
    await state.update_data(gun_skins=parse_price(message.text) or 0)
    await state.set_state(AddAccountFlow.description)
    await message.answer("📝 توضیحات:", reply_markup=cancel_only())


@router.message(AddAccountFlow.description, F.text, IsAdmin())
async def add_description(message: Message, state: FSMContext) -> None:
    await state.update_data(description=message.text.strip(), images=[])
    await state.set_state(AddAccountFlow.images)
    await message.answer(
        "📸 تصاویر اکانت را ارسال کنید. پس از اتمام /done را بزنید.",
        reply_markup=cancel_only(),
    )


@router.message(AddAccountFlow.images, F.photo, IsAdmin())
async def add_image(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    images = data.get("images", [])
    images.append(message.photo[-1].file_id)
    await state.update_data(images=images)
    await message.answer(f"تصویر {len(images)} ذخیره شد. /done برای ادامه.")


@router.message(AddAccountFlow.images, F.text == "/done", IsAdmin())
async def add_images_done(message: Message, state: FSMContext) -> None:
    await state.set_state(AddAccountFlow.credentials)
    await message.answer(
        "🔐 اطلاعات ورود اکانت را وارد کنید (ایمیل/رمز/...).\n"
        "این اطلاعات رمزنگاری شده ذخیره و فقط پس از خرید تحویل می‌شود.\n"
        "اگر فعلاً ندارید «-» بفرستید.",
        reply_markup=cancel_only(),
    )


@router.message(AddAccountFlow.credentials, F.text, IsAdmin())
async def add_credentials(
    message: Message, services: Services, state: FSMContext
) -> None:
    data = await state.get_data()
    creds = message.text.strip()
    creds = None if creds == "-" else creds
    account = await services.account.create_listing(
        title=data["title"],
        price=data["price"],
        level=data["level"],
        skins_count=data["skins"],
        elite_count=data["elite"],
        gun_skins_count=data["gun_skins"],
        description=data["description"],
        images=",".join(data.get("images", [])),
        credentials=creds,
    )
    await services.commit()
    await message.answer(f"✅ اکانت #{account.id} با موفقیت ثبت و منتشر شد.")
    await state.clear()


# ============================ DIAMOND PRICES ============================
@router.callback_query(AdminCB.filter(F.action == "diamond_prices"), IsAdmin())
async def diamond_prices(callback: CallbackQuery, services: Services) -> None:
    plans = await services.diamond.list_plans()
    kb = InlineKeyboardBuilder()
    for p in plans:
        kb.button(
            text=f"{p.name} — {format_toman(p.price)}",
            callback_data=AdminCB(action="edit_plan", value=p.code),
        )
    kb.adjust(1)
    await edit_or_answer(
        callback.message,
        "💎 برای تغییر قیمت، پلن موردنظر را انتخاب کنید:",
        reply_markup=kb.as_markup(),
    )
    await callback.answer()


@router.callback_query(AdminCB.filter(F.action == "edit_plan"), IsAdmin())
async def edit_plan(
    callback: CallbackQuery, callback_data: AdminCB, state: FSMContext
) -> None:
    await state.set_state(EditDiamondPrice.entering_price)
    await state.update_data(plan_code=callback_data.value)
    await edit_or_answer(
        callback.message,
        f"قیمت جدید برای پلن <code>{callback_data.value}</code> را وارد کنید (تومان):",
        reply_markup=cancel_only(),
    )
    await callback.answer()


@router.message(EditDiamondPrice.entering_price, F.text, IsAdmin())
async def save_plan_price(
    message: Message, services: Services, state: FSMContext
) -> None:
    price = parse_price(message.text)
    if price is None or price <= 0:
        await message.answer("قیمت نامعتبر.")
        return
    data = await state.get_data()
    ok = await services.diamond.set_plan_price(data["plan_code"], price)
    await message.answer("✅ قیمت به‌روزرسانی شد." if ok else "پلن یافت نشد.")
    await state.clear()
