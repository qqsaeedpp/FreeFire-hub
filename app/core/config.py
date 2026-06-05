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
    admin_id: int = Field(..., alias="ADMIN_ID")
    log_chat_id: int = Field(..., alias="LOG_CHAT_ID")

    # --- MySQL ---
    mysql_host: str = Field("localhost", alias="MYSQL_HOST")
    mysql_port: int = Field(3306, alias="MYSQL_PORT")
    mysql_user: str = Field("freefire", alias="MYSQL_USER")
    mysql_password: str = Field("", alias="MYSQL_PASSWORD")
    mysql_database: str = Field("freefire_hub", alias="MYSQL_DATABASE")

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
