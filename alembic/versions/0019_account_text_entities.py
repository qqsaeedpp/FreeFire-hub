"""accounts += title_entities_json / description_entities_json

Adds two nullable JSON columns that store the Telegram ``MessageEntity`` list for
an account's title and description. They back premium (custom) emoji support: when
an admin types a premium emoji into a listing, its ``custom_emoji`` entities are
persisted here so the very same emoji can be replayed wherever the listing is
re-sent (public announcement, buy-account detail, management panel). Ordinary
listings leave both columns NULL and keep rendering through the existing HTML
path, so this change is purely additive. Mirrors ``bot_texts.entities_json``.

Revision ID: 0019_account_text_entities
Revises: 0018_wallet_topup_requests
Create Date: 2026-06-23
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0019_account_text_entities"
down_revision: Union[str, None] = "0018_wallet_topup_requests"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "accounts", sa.Column("title_entities_json", sa.Text(), nullable=True)
    )
    op.add_column(
        "accounts", sa.Column("description_entities_json", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("accounts", "description_entities_json")
    op.drop_column("accounts", "title_entities_json")
