"""admins — runtime-editable admin roster with roles

Adds the ``admins`` table backing unlimited, restart-free admin management from
the panel. The privilege is mirrored onto ``users.is_admin`` by the service, so
existing access checks keep working; this table carries role + profile.

Revision ID: 0011_admins
Revises: 0010_deposit_settings
Create Date: 2026-06-09
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.core.constants import AdminRole

revision: str = "0011_admins"
down_revision: Union[str, None] = "0010_deposit_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _ts():
    return (
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )


def upgrade() -> None:
    op.create_table(
        "admins",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(64), nullable=True),
        sa.Column("first_name", sa.String(255), nullable=True),
        sa.Column(
            "role",
            sa.Enum(AdminRole),
            nullable=False,
            server_default=AdminRole.ADMIN.value,
        ),
        *_ts(),
        sa.UniqueConstraint("user_id", name="uq_admins_user_id"),
    )
    op.create_index("ix_admins_user_id", "admins", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_admins_user_id", table_name="admins")
    op.drop_table("admins")
