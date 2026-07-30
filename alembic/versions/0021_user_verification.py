"""user verification — phone + captcha onboarding stamps

Adds the three timestamps that make onboarding verification durable in MySQL
(``phone_verified_at``, ``captcha_verified_at``, ``verification_completed_at``)
and promotes ``users.phone`` to a unique, indexed E.164 column so one mobile
line can onboard exactly one Telegram account.

Existing data is treated as untrusted, not disposable: any non-NULL ``phone``
written before this feature existed is normalized to E.164 in place using the
frozen, self-contained rules below (no dependency on application code, which is
free to change later). The migration **aborts** rather than guessing when a
stored value cannot be normalized, or when two rows collapse onto the same
number — the offending user ids are named in the error so an operator can fix
the data and re-run.

No row is ever auto-verified: the new timestamps are created NULL for everyone,
so every pre-existing non-admin user re-verifies on their next interaction. No
referral, wallet or transaction data is read or written here.

Revision ID: 0021_user_verification
Revises: 0020_app_settings
Create Date: 2026-07-30
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0021_user_verification"
down_revision: Union[str, None] = "0020_app_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# --- frozen normalization rules (intentionally duplicated from app.utils.phone) ---
# A migration must produce the same result forever, so it may not import helpers
# whose behavior can be tuned later. Deliberately stricter than the runtime
# parser: it only accepts what is unambiguously an Iranian mobile number.
_DIGITS = {ord("۰") + i: str(i) for i in range(10)}
_DIGITS.update({ord("٠") + i: str(i) for i in range(10)})
_SEPARATORS = str.maketrans("", "", " \t\r\n-()./\\")


def _normalize(raw: str) -> str | None:
    """Return E.164 for an Iranian mobile number, or ``None`` if not one."""
    value = str(raw or "").strip().translate(_DIGITS).translate(_SEPARATORS)
    if not value:
        return None
    for prefix in ("+98", "0098", "98", "0"):
        if value.startswith(prefix):
            value = value[len(prefix) :]
            break
    if len(value) != 10 or not value.isdigit() or not value.startswith("9"):
        return None
    return f"+98{value}"


def _migrate_existing_phones() -> None:
    """Rewrite stored phones to E.164, aborting loudly on bad or colliding data."""
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, phone FROM users "
            "WHERE phone IS NOT NULL AND TRIM(phone) <> ''"
        )
    ).fetchall()
    if not rows:
        return

    normalized: dict[int, str] = {}
    unparsable: list[int] = []
    for user_id, phone in rows:
        canonical = _normalize(phone)
        if canonical is None:
            unparsable.append(int(user_id))
        else:
            normalized[int(user_id)] = canonical

    if unparsable:
        raise RuntimeError(
            "Cannot normalize users.phone to E.164 for user id(s): "
            f"{sorted(unparsable)}. Fix or clear these values (set them to NULL) "
            "and re-run `alembic upgrade head`."
        )

    owners: dict[str, list[int]] = {}
    for user_id, canonical in normalized.items():
        owners.setdefault(canonical, []).append(user_id)
    collisions = {p: sorted(ids) for p, ids in owners.items() if len(ids) > 1}
    if collisions:
        raise RuntimeError(
            "users.phone would violate the new unique constraint — these user "
            f"ids share a number after normalization: {collisions}. Decide which "
            "account keeps each number, clear the others, and re-run."
        )

    for user_id, canonical in normalized.items():
        bind.execute(
            sa.text("UPDATE users SET phone = :phone WHERE id = :id"),
            {"phone": canonical, "id": user_id},
        )

    # Blank strings would otherwise collide with each other under the unique index.
    bind.execute(sa.text("UPDATE users SET phone = NULL WHERE TRIM(phone) = ''"))


def upgrade() -> None:
    op.add_column("users", sa.Column("phone_verified_at", sa.DateTime(), nullable=True))
    op.add_column(
        "users", sa.Column("captcha_verified_at", sa.DateTime(), nullable=True)
    )
    op.add_column(
        "users", sa.Column("verification_completed_at", sa.DateTime(), nullable=True)
    )

    _migrate_existing_phones()
    # Unique index (not a UNIQUE constraint) to match the ORM's
    # ``unique=True, index=True`` mapping; NULLs stay unrestricted in both
    # MySQL 8 and SQLite, so unverified users are unaffected.
    op.create_index("ix_users_phone", "users", ["phone"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_phone", table_name="users")
    op.drop_column("users", "verification_completed_at")
    op.drop_column("users", "captcha_verified_at")
    op.drop_column("users", "phone_verified_at")
    # Phone values stay in their normalized E.164 form: the pre-migration text was
    # free-form and is not recoverable, and E.164 remains a valid value for the
    # old (plain, non-unique) column.
