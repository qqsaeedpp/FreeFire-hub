"""Durable settings store — MySQL is the single source of truth.

Admin-editable values (referral reward, diamond plan prices, the level-up bundle
price) are read from and written to the ``app_settings`` table. A hardcoded/env
default is used by callers ONLY when a key has no row yet (first run); once a
value is written it is never changed except by another admin write.

Every admin write also records an ``AdminLog`` row in the **same transaction**, so
the change audit (field, old → new, who) is durable and atomic with the change.

Deliberately not Redis-backed: Redis is not durable in this deployment, and the
whole "settings revert after a restart/deploy" class of bugs came from trusting
Redis as the store. A single indexed-row read is negligible for a bot this size.
"""
from __future__ import annotations

import json

from app.models.admin_log import AdminLog
from app.models.app_setting import AppSetting
from app.repositories.app_settings import AppSettingRepository

# Stable keys — intentionally NOT version-stamped, so a value can never be
# abandoned/reseeded by bumping a key name (that was a root cause of the bug).
KEY_REFERRAL_REWARD = "referral_reward"
KEY_DIAMOND_PLANS = "diamond_plans"
KEY_LEVELUP_ALL_PRICE = "diamond_levelup_all_price"


class SettingsService:
    def __init__(self, repo: AppSettingRepository) -> None:
        self.repo = repo

    async def get(self, key: str) -> str | None:
        """Current stored value for ``key`` (``None`` if never set)."""
        row = await self.repo.get_by_key(key)
        return row.value if row is not None else None

    async def set(self, key: str, value: str, *, changed_by: int | None) -> str | None:
        """Upsert a setting, audit the change, and return the previous value.

        This is the only path that mutates a setting. ``changed_by`` is the admin's
        Telegram id (the audit's actor). The write is not committed here — the
        handler commits, keeping the value row and its ``AdminLog`` audit atomic.
        """
        row = await self.repo.get_by_key(key)
        old = row.value if row is not None else None
        if row is None:
            await self.repo.add(AppSetting(key=key, value=value, updated_by=changed_by))
        else:
            row.value = value
            row.updated_by = changed_by
        self.repo.session.add(
            AdminLog(
                event="setting_changed",
                actor_id=changed_by,
                payload=json.dumps(
                    {"field": key, "old": old, "new": value}, ensure_ascii=False
                ),
            )
        )
        return old

    async def init_if_absent(self, key: str, value: str) -> bool:
        """Create a row only when ``key`` is absent — never touch an existing one.

        Used solely by the one-time legacy import at startup to migrate values that
        currently live in Redis. Returns ``True`` if a row was created. This is the
        only thing startup is permitted to do to settings.
        """
        if await self.repo.get_by_key(key) is not None:
            return False
        await self.repo.add(AppSetting(key=key, value=value, updated_by=None))
        return True

    # ---- typed convenience accessors ----
    async def get_int(self, key: str, default: int) -> int:
        raw = await self.get(key)
        if raw is None:
            return default
        try:
            return int(raw)
        except (TypeError, ValueError):
            return default

    async def set_int(self, key: str, value: int, *, changed_by: int | None) -> str | None:
        return await self.set(key, str(int(value)), changed_by=changed_by)
