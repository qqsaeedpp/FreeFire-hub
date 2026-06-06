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

_PLANS_KEY = "diamond:plans"

DEFAULT_PLANS: list["DiamondPlan"] = []


@dataclass
class DiamondPlan:
    code: str
    name: str
    diamonds: int
    price: int  # Toman


def _default_plans() -> list[DiamondPlan]:
    return [
        DiamondPlan("d100", "۱۰۰ الماس", 100, 95_000),
        DiamondPlan("d310", "۳۱۰ الماس", 310, 270_000),
        DiamondPlan("d520", "۵۲۰ الماس", 520, 440_000),
        DiamondPlan("d1060", "۱۰۶۰ الماس", 1060, 850_000),
        DiamondPlan("d2180", "۲۱۸۰ الماس", 2180, 1_700_000),
        DiamondPlan("d5600", "۵۶۰۰ الماس", 5600, 4_200_000),
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
