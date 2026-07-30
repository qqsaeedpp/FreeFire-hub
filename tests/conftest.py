"""Pytest fixtures. Dummy env is set BEFORE importing any app module."""
from __future__ import annotations

import os

os.environ.setdefault("BOT_TOKEN", "123:TEST")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("LOG_CHAT_ID", "-100")
os.environ.setdefault("MYSQL_PASSWORD", "test")

from types import SimpleNamespace

import fakeredis.aioredis
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
import app.models  # noqa: F401  ensure all tables are registered


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


@pytest_asyncio.fixture
async def redis():
    """In-process Redis that really executes Lua.

    ``fakeredis[lua]`` runs the captcha's ``EVAL`` script through a genuine Lua
    interpreter, so the single-use/replay semantics under test are the same code
    that runs in production — only the transport is in-process.
    """
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


@pytest_asyncio.fixture
async def file_db(tmp_path):
    """A file-backed SQLite database so *several* sessions share one store.

    Needed for the conflict tests: two concurrent actors must hit the same
    unique index, which an in-memory database (private per connection) cannot
    reproduce. Yields an ``async_sessionmaker``.
    """
    url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


def build_services(session, redis) -> SimpleNamespace:
    """Wire the real repositories/services under test (only Redis is in-process).

    Nothing here is a stub: the same ``VerificationService``/``ReferralService``/
    ``WalletService`` objects the container builds are exercised, so the tests
    assert production behavior rather than a test double's.
    """
    from app.repositories.admins import AdminRepository
    from app.repositories.app_settings import AppSettingRepository
    from app.repositories.referrals import ReferralRepository
    from app.repositories.users import UserRepository
    from app.repositories.wallets import WalletRepository
    from app.services.admin_service import AdminService
    from app.services.referral_service import ReferralService
    from app.services.settings_service import SettingsService
    from app.services.verification_service import VerificationService
    from app.services.wallet_service import WalletService

    users = UserRepository(session)
    referrals = ReferralRepository(session)
    wallets_repo = WalletRepository(session)
    wallet = WalletService(wallets_repo)
    app_settings = SettingsService(AppSettingRepository(session))
    referral = ReferralService(referrals, wallet, users, app_settings)
    verification = VerificationService(users, referral, redis)
    return SimpleNamespace(
        session=session,
        users=users,
        referrals=referrals,
        wallets_repo=wallets_repo,
        wallet=wallet,
        referral=referral,
        verification=verification,
        admin=AdminService(AdminRepository(session), users, redis),
        commit=session.commit,
    )
