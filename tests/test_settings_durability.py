"""Settings must be durable: an admin-set value survives a restart and never
auto-reverts to a default. Regression guard for the Redis-only-storage bug.
"""
import json

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import settings as cfg
from app.core.database import Base
import app.models  # noqa: F401  register tables
from app.container import Services
from app.models.admin_log import AdminLog


async def _fresh_db():
    """A SQLite engine whose in-memory DB is shared across sessions (StaticPool),
    so a *new* ``Services`` session reads what a previous one committed — exactly
    the 'value persists across a restart' property we need to assert."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.mark.asyncio
async def test_referral_reward_zero_survives_restart():
    engine, Session = await _fresh_db()
    try:
        async with Session() as s:  # default until set
            assert await Services(s).referral.get_reward() == cfg.referral_reward
        async with Session() as s:  # admin sets it to 0 (the bug scenario)
            await Services(s).referral.set_reward(0, changed_by=707967792)
            await s.commit()
        async with Session() as s:  # "restart": fresh session, no Redis
            assert await Services(s).referral.get_reward() == 0  # must NOT revert to 10000
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_diamond_price_survives_restart():
    engine, Session = await _fresh_db()
    try:
        async with Session() as s:
            svc = Services(s)
            assert await svc.diamond.set_plan_price("d110", 999_000, changed_by=1)
            await svc.commit()
        async with Session() as s:  # "restart"
            plan = await Services(s).diamond.get_plan("d110")
            assert plan.price == 999_000  # stored price, not the hardcoded default
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_levelup_all_price_survives_restart():
    engine, Session = await _fresh_db()
    try:
        async with Session() as s:
            await Services(s).diamond.set_levelup_all_price(123_000, changed_by=1)
            await s.commit()
        async with Session() as s:
            assert await Services(s).diamond.get_levelup_all_price() == 123_000
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_set_returns_old_value_and_audits_the_change():
    engine, Session = await _fresh_db()
    try:
        async with Session() as s:
            await Services(s).referral.set_reward(7_000, changed_by=10)
            await s.commit()
        async with Session() as s:
            svc = Services(s)
            old = await svc.referral.set_reward(9_000, changed_by=20)
            await svc.commit()
            assert old == "7000"  # previous stored value returned for the change-log
        async with Session() as s:
            rows = (
                await s.execute(
                    select(AdminLog).where(AdminLog.event == "setting_changed")
                )
            ).scalars().all()
            payloads = [json.loads(r.payload) for r in rows]
            transition = next(p for p in payloads if p["new"] == "9000")
            assert transition["field"] == "referral_reward"
            assert transition["old"] == "7000"  # audit captured old → new
            assert any(r.actor_id == 20 for r in rows)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_init_if_absent_never_overwrites_existing():
    """The startup legacy import must never clobber a value an admin already set."""
    engine, Session = await _fresh_db()
    try:
        async with Session() as s:
            await Services(s).referral.set_reward(5_000, changed_by=1)
            await s.commit()
        async with Session() as s:
            svc = Services(s)
            created = await svc.settings.init_if_absent("referral_reward", "10000")
            await svc.commit()
            assert created is False  # row exists → import is a no-op
            assert await svc.referral.get_reward() == 5_000  # admin value preserved
    finally:
        await engine.dispose()
