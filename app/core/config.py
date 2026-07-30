"""Application settings loaded from environment variables via Pydantic Settings."""
from __future__ import annotations

from functools import cached_property

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Telegram ---
    bot_token: str = Field(..., alias="BOT_TOKEN")
    # One id, or several comma-separated ids ("123" or "123,456").
    admin_id_raw: str = Field(..., alias="ADMIN_ID")
    log_chat_id: int = Field(..., alias="LOG_CHAT_ID")
    # Channel where lottery results are announced; defaults to the log channel.
    lottery_channel_id_raw: int | None = Field(None, alias="LOTTERY_CHANNEL_ID")

    @property
    def lottery_channel_id(self) -> int:
        return self.lottery_channel_id_raw or self.log_chat_id

    @cached_property
    def admin_ids(self) -> list[int]:
        return [int(p.strip()) for p in self.admin_id_raw.split(",") if p.strip()]

    @property
    def admin_id(self) -> int:
        """Primary admin (first configured id) — recipient for admin notifications."""
        return self.admin_ids[0]

    # --- MySQL ---
    mysql_host: str = Field("localhost", alias="MYSQL_HOST")
    mysql_port: int = Field(3306, alias="MYSQL_PORT")
    mysql_user: str = Field("freefire", alias="MYSQL_USER")
    mysql_password: str = Field("", alias="MYSQL_PASSWORD")
    mysql_database: str = Field("freefire_hub", alias="MYSQL_DATABASE")
    # SSL handshake mode passed to the mysqldump/mysql CLIs. Defaults to DISABLED
    # because the bot talks to MySQL over the internal Docker network (no TLS),
    # and an MySQL-8 server with a self-signed cert otherwise rejects the client
    # with error 2026. Accepts any MySQL ``--ssl-mode`` value (DISABLED/PREFERRED/
    # REQUIRED/…); the BackupService transparently falls back to the MariaDB-client
    # ``--ssl=0/1`` syntax when the installed client doesn't understand --ssl-mode.
    mysql_ssl_mode: str = Field("DISABLED", alias="MYSQL_SSL_MODE")

    # --- Redis ---
    redis_host: str = Field("localhost", alias="REDIS_HOST")
    redis_port: int = Field(6379, alias="REDIS_PORT")
    redis_db: int = Field(0, alias="REDIS_DB")
    redis_password: str = Field("", alias="REDIS_PASSWORD")

    # --- Business rules ---
    referral_reward: int = Field(10_000, alias="REFERRAL_REWARD")
    requested_account_deposit: int = Field(300_000, alias="REQUESTED_ACCOUNT_DEPOSIT")
    card_number: str = Field("0000-0000-0000-0000", alias="CARD_NUMBER")
    card_holder: str = Field("Store Owner", alias="CARD_HOLDER")

    # --- Onboarding verification ---
    # Lifetime of one math-captcha challenge, and how many wrong answers a user
    # may give before a short cooldown. Both are tunable without a code change.
    captcha_ttl_seconds: int = Field(300, alias="CAPTCHA_TTL_SECONDS")
    captcha_max_attempts: int = Field(3, alias="CAPTCHA_MAX_ATTEMPTS")
    captcha_cooldown_seconds: int = Field(60, alias="CAPTCHA_COOLDOWN_SECONDS")

    # --- Runtime ---
    debug: bool = Field(False, alias="DEBUG")
    timezone: str = Field("Asia/Tehran", alias="TIMEZONE")
    rate_limit_per_second: float = Field(1.0, alias="RATE_LIMIT_PER_SECOND")

    @cached_property
    def database_url(self) -> str:
        return (
            f"mysql+asyncmy://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}?charset=utf8mb4"
        )

    @cached_property
    def redis_url(self) -> str:
        auth = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"


settings = Settings()  # type: ignore[call-arg]
