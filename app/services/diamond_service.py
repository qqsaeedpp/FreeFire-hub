"""Diamond service — manages purchasable diamond plans and creates diamond orders.

Plans are stored in Redis so the admin can edit prices live, falling back to a
sensible default catalog on first run.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from redis.asyncio import Redis

from app.core.constants import OrderType
from app.models.order import DiamondOrder
from app.repositories.orders import OrderRepository

# Bumped to v2 to force a one-time reseed of the categorized catalog
# (older cached payloads lack the new ``category`` field).
_PLANS_KEY = "diamond:plans:v2"

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
    return [
        # ---------------- UID → جم ----------------
        DiamondPlan("d110", "110 الماس", 110, 180_000, CAT_DIAMOND),
        DiamondPlan("d230", "230 الماس", 230, 360_000, CAT_DIAMOND),
        DiamondPlan("d340", "340 الماس", 340, 540_000, CAT_DIAMOND),
        DiamondPlan("d580", "580 الماس", 580, 900_000, CAT_DIAMOND),
        DiamondPlan("d810", "810 الماس", 810, 1_255_000, CAT_DIAMOND),
        DiamondPlan("d1188", "1188 الماس", 1188, 1_790_000, CAT_DIAMOND),
        DiamondPlan("d1520", "1520 الماس", 1520, 2_320_000, CAT_DIAMOND),
        DiamondPlan("d2420", "2420 الماس", 2420, 3_580_000, CAT_DIAMOND),
        DiamondPlan("d1000", "1000 الماس", 1000, 1_650_000, CAT_DIAMOND),
        DiamondPlan("d2000", "2000 الماس", 2000, 3_300_000, CAT_DIAMOND),
        DiamondPlan("d5000", "5000 الماس", 5000, 8_250_000, CAT_DIAMOND),
        DiamondPlan("d10000", "10000 الماس", 10000, 16_500_000, CAT_DIAMOND),
        DiamondPlan("d20000", "20000 الماس", 20000, 32_000_000, CAT_DIAMOND),
        DiamondPlan("d50000", "50000 الماس", 50000, 79_999_999, CAT_DIAMOND),
        # ---------------- UID → لول اپ ----------------
        DiamondPlan("lvl6", "آفر لول 6", 0, 95_000, CAT_LEVELUP),
        DiamondPlan("lvl10", "آفر لول 10", 0, 125_000, CAT_LEVELUP),
        DiamondPlan("lvl15", "آفر لول 15", 0, 125_000, CAT_LEVELUP),
        DiamondPlan("lvl20", "آفر لول 20", 0, 125_000, CAT_LEVELUP),
        DiamondPlan("lvl25", "آفر لول 25", 0, 125_000, CAT_LEVELUP),
        DiamondPlan("lvl30", "آفر لول 30", 0, 175_000, CAT_LEVELUP),
        # ---------------- اطلاعات اکانت ----------------
        DiamondPlan("accw", "هفتگی", 0, 299_000, CAT_ACCOUNT),
        DiamondPlan("accm", "ماهانه", 0, 1_790_000, CAT_ACCOUNT),
        DiamondPlan("accwl", "هفتگی لایت", 0, 120_000, CAT_ACCOUNT),
        DiamondPlan("acco1", "آفر روزانه ۱$", 0, 185_000, CAT_ACCOUNT),
        DiamondPlan("acco2", "آفر روزانه ۲$", 0, 370_000, CAT_ACCOUNT),
    ]


class DiamondService:
    def __init__(self, redis: Redis, orders: OrderRepository) -> None:
        self.redis = redis
        self.orders = orders

    async def list_plans(self) -> list[DiamondPlan]:
        raw = await self.redis.get(_PLANS_KEY)
        if not raw:
            plans = _default_plans()
            await self._save(plans)
            return plans
        data = json.loads(raw)
        return [DiamondPlan(**p) for p in data]

    async def list_plans_by_category(self, category: str) -> list[DiamondPlan]:
        return [p for p in await self.list_plans() if p.category == category]

    async def get_plan(self, code: str) -> DiamondPlan | None:
        for plan in await self.list_plans():
            if plan.code == code:
                return plan
        return None

    async def set_plan_price(self, code: str, price: int) -> bool:
        plans = await self.list_plans()
        found = False
        for plan in plans:
            if plan.code == code:
                plan.price = price
                found = True
        if found:
            await self._save(plans)
        return found

    async def _save(self, plans: list[DiamondPlan]) -> None:
        await self.redis.set(_PLANS_KEY, json.dumps([asdict(p) for p in plans]))

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
    ) -> DiamondOrder:
        """Create a diamond order paid with account credentials.

        Only three details are collected from the user (each exactly once):
        account email, gmail password and backup code — all stored encrypted.
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
        )
        return await self.orders.add(order)
