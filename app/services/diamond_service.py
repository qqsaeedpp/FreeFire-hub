"""Diamond service — manages purchasable diamond plans and creates diamond orders.

Plan prices and the level-up bundle price are stored durably in MySQL via
:class:`~app.services.settings_service.SettingsService`, so an admin can edit them
live and the values survive restarts/deploys (they used to live only in Redis and
reverted to the defaults below on any Redis loss or key bump). The default catalog
here is used only until the first edit — nothing ever overwrites a stored value.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from app.core.constants import LoginMethod, OrderType
from app.models.order import DiamondOrder
from app.repositories.orders import OrderRepository
from app.services.settings_service import (
    KEY_DIAMOND_PLANS,
    KEY_LEVELUP_ALL_PRICE,
    SettingsService,
)

# Default "buy all Level-Up offers at once" price (Toman) — used only until set.
DEFAULT_LEVELUP_ALL_PRICE = 750_000

# Plan categories.
CAT_DIAMOND = "diamond"   # خرید با UID → جم
CAT_LEVELUP = "levelup"   # خرید با UID → لول اپ
CAT_ACCOUNT = "account"   # خرید با اطلاعات اکانت

DEFAULT_PLANS: list["DiamondPlan"] = []


@dataclass
class DiamondPlan:
    code: str
    name: str
    diamonds: int
    price: int  # Toman
    category: str = CAT_DIAMOND


def _default_plans() -> list[DiamondPlan]:
    # NOTE: plan order is significant — the user-facing menus render plans in
    # this order (especially the account category's 2-column layout).
    return [
        # ---------------- UID → جم ----------------
        DiamondPlan("d110", "110 جم", 110, 180_000, CAT_DIAMOND),
        DiamondPlan("d230", "230 جم", 230, 360_000, CAT_DIAMOND),
        DiamondPlan("d340", "340 جم", 340, 540_000, CAT_DIAMOND),
        DiamondPlan("d580", "580 جم", 580, 900_000, CAT_DIAMOND),
        DiamondPlan("d810", "810 جم", 810, 1_255_000, CAT_DIAMOND),
        DiamondPlan("d1188", "1188 جم", 1188, 1_790_000, CAT_DIAMOND),
        DiamondPlan("d1520", "1520 جم", 1520, 2_320_000, CAT_DIAMOND),
        DiamondPlan("d2420", "2420 جم", 2420, 3_580_000, CAT_DIAMOND),
        DiamondPlan("uweekly", "هفتگی", 0, 460_000, CAT_DIAMOND),
        DiamondPlan("umonthly", "ماهانه", 0, 2_180_000, CAT_DIAMOND),
        DiamondPlan("ubooyah", "Booyah Pass", 0, 250_000, CAT_DIAMOND),
        # ---------------- UID → لول اپ ----------------
        DiamondPlan("lvl6", "آفر لول 6", 0, 95_000, CAT_LEVELUP),
        DiamondPlan("lvl10", "آفر لول 10", 0, 125_000, CAT_LEVELUP),
        DiamondPlan("lvl15", "آفر لول 15", 0, 125_000, CAT_LEVELUP),
        DiamondPlan("lvl20", "آفر لول 20", 0, 125_000, CAT_LEVELUP),
        DiamondPlan("lvl25", "آفر لول 25", 0, 125_000, CAT_LEVELUP),
        DiamondPlan("lvl30", "آفر لول 30", 0, 175_000, CAT_LEVELUP),
        # ---------------- اطلاعات اکانت ----------------
        # Order matters: drives the [هفتگی][ماهانه] / [هفتگی لایت] / ... layout.
        DiamondPlan("accw", "هفتگی", 0, 299_000, CAT_ACCOUNT),
        DiamondPlan("accm", "ماهانه", 0, 1_790_000, CAT_ACCOUNT),
        DiamondPlan("accwl", "هفتگی لایت", 0, 120_000, CAT_ACCOUNT),
        DiamondPlan("acco1", "آفر روزانه ۱ دلاری", 0, 185_000, CAT_ACCOUNT),
        DiamondPlan("acco2", "آفر روزانه ۲ دلاری", 0, 370_000, CAT_ACCOUNT),
        DiamondPlan("acc520", "520 جم", 520, 850_000, CAT_ACCOUNT),
        DiamondPlan("acc2180", "2k جم", 2180, 3_200_000, CAT_ACCOUNT),
        DiamondPlan("acc1060", "1060 جم", 1060, 1_650_000, CAT_ACCOUNT),
        DiamondPlan("acc5600", "5600 جم", 5600, 7_250_000, CAT_ACCOUNT),
    ]


class DiamondService:
    def __init__(self, app_settings: SettingsService, orders: OrderRepository) -> None:
        self.app_settings = app_settings
        self.orders = orders

    async def list_plans(self) -> list[DiamondPlan]:
        raw = await self.app_settings.get(KEY_DIAMOND_PLANS)
        if raw is None:
            # Not seeded yet (fresh install) → the default catalog. It is persisted
            # the first time an admin edits a price; this never overwrites a stored
            # value, so admin-edited prices are kept.
            return _default_plans()
        return [DiamondPlan(**p) for p in json.loads(raw)]

    async def list_plans_by_category(self, category: str) -> list[DiamondPlan]:
        return [p for p in await self.list_plans() if p.category == category]

    async def get_plan(self, code: str) -> DiamondPlan | None:
        for plan in await self.list_plans():
            if plan.code == code:
                return plan
        return None

    async def set_plan_price(
        self, code: str, price: int, *, changed_by: int | None = None
    ) -> bool:
        """Persist a new price for one plan (admin action). Caller must commit."""
        plans = await self.list_plans()
        found = False
        for plan in plans:
            if plan.code == code:
                plan.price = price
                found = True
        if found:
            await self.app_settings.set(
                KEY_DIAMOND_PLANS,
                json.dumps([asdict(p) for p in plans]),
                changed_by=changed_by,
            )
        return found

    async def get_levelup_all_price(self) -> int:
        """Price for the "buy all Level-Up offers at once" bundle (admin-editable)."""
        return await self.app_settings.get_int(
            KEY_LEVELUP_ALL_PRICE, DEFAULT_LEVELUP_ALL_PRICE
        )

    async def set_levelup_all_price(
        self, price: int, *, changed_by: int | None = None
    ) -> str | None:
        """Persist the level-up bundle price (admin action). Caller must commit."""
        return await self.app_settings.set_int(
            KEY_LEVELUP_ALL_PRICE, price, changed_by=changed_by
        )

    async def create_uid_order(
        self, user_id: int, plan: DiamondPlan, uid: str
    ) -> DiamondOrder:
        order = DiamondOrder(
            user_id=user_id,
            order_type=OrderType.DIAMOND_UID,
            amount=plan.price,
            plan_name=plan.name,
            diamonds=plan.diamonds,
            uid=uid,
        )
        return await self.orders.add(order)

    async def create_account_order(
        self,
        user_id: int,
        plan: DiamondPlan,
        *,
        email: str,
        gmail_password: str | None = None,
        backup_code: str | None = None,
        login_method: LoginMethod | None = None,
    ) -> DiamondOrder:
        """Create a diamond order paid with account credentials.

        Collected from the user: the game save type (login service), account
        email/login id, password and backup code — credentials stored encrypted.
        """
        from app.core.security import encrypt

        def enc(value: str | None) -> str | None:
            return encrypt(value) if value else None

        order = DiamondOrder(
            user_id=user_id,
            order_type=OrderType.DIAMOND_ACCOUNT,
            amount=plan.price,
            plan_name=plan.name,
            diamonds=plan.diamonds,
            account_email=enc(email),
            gmail_password=enc(gmail_password),
            backup_code=enc(backup_code),
            login_method=login_method,
        )
        return await self.orders.add(order)
