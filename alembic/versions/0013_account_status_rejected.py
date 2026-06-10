"""accounts.status ENUM += REJECTED (admin can decline a user listing)

Adds the ``REJECTED`` member to the ``accounts.status`` enum so an admin can
decline a user-submitted sale listing from the new «📦 سفارشات فروش اکانت کاربران»
section / instant notification. MySQL stores native ENUMs, so a widening ALTER is
required; SQLite (tests) builds the schema via ``create_all`` and needs no change.

Revision ID: 0013_account_status_rejected
Revises: 0012_button_text_to_text
Create Date: 2026-06-10
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

from app.core.constants import AccountStatus

revision: str = "0013_account_status_rejected"
down_revision: Union[str, None] = "0012_button_text_to_text"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# SQLAlchemy's ``Enum`` persists the member *names*; mirror that here.
_ALL = ", ".join(f"'{m.name}'" for m in AccountStatus)
_WITHOUT_REJECTED = ", ".join(
    f"'{m.name}'" for m in AccountStatus if m is not AccountStatus.REJECTED
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "mysql":
        op.execute(f"ALTER TABLE accounts MODIFY status ENUM({_ALL}) NOT NULL")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "mysql":
        op.execute(f"ALTER TABLE accounts MODIFY status ENUM({_WITHOUT_REJECTED}) NOT NULL")
