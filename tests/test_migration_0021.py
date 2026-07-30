"""Migration 0021 — executed for real against a throwaway database.

These tests import the migration module and run its actual ``upgrade()`` /
``downgrade()`` bodies through an Alembic ``Operations`` context bound to a live
SQLite connection, so the column adds, the in-place E.164 rewrite, the abort
paths and the unique index are all genuinely exercised rather than inspected.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "0021_user_verification.py"
)

# The ``users`` shape as it exists *before* this migration (plain, non-unique
# phone). Written out so the test doesn't drift with the current ORM model.
_PRE_MIGRATION_USERS = """
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id BIGINT NOT NULL,
    username VARCHAR(64),
    full_name VARCHAR(255),
    phone VARCHAR(20),
    referral_code VARCHAR(16) NOT NULL,
    referred_by_id BIGINT,
    pending_referral_code VARCHAR(64),
    is_active BOOLEAN DEFAULT 1,
    is_banned BOOLEAN DEFAULT 0,
    is_admin BOOLEAN DEFAULT 0,
    has_purchased BOOLEAN DEFAULT 0,
    created_at DATETIME,
    updated_at DATETIME
)
"""


def load_migration():
    spec = importlib.util.spec_from_file_location("migration_0021", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def db(tmp_path):
    """A pre-0021 database; yields (connection, migration module)."""
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'm.db'}")
    with engine.begin() as conn:
        conn.exec_driver_sql(_PRE_MIGRATION_USERS)
    conn = engine.connect()
    yield conn, load_migration()
    conn.close()
    engine.dispose()


def seed(conn, rows):
    for idx, phone in enumerate(rows, start=1):
        conn.execute(
            sa.text(
                "INSERT INTO users (id, telegram_id, referral_code, phone) "
                "VALUES (:i, :t, :c, :p)"
            ),
            {"i": idx, "t": 1000 + idx, "c": f"CODE{idx}", "p": phone},
        )


def run_upgrade(conn, module):
    ctx = MigrationContext.configure(conn)
    with Operations.context(ctx):
        module.upgrade()


def run_downgrade(conn, module):
    ctx = MigrationContext.configure(conn)
    with Operations.context(ctx):
        module.downgrade()


def columns(conn) -> set[str]:
    return {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(users)").fetchall()}


def test_chain_links_to_the_previous_revision():
    module = load_migration()
    assert module.revision == "0021_user_verification"
    assert module.down_revision == "0020_app_settings"


def test_upgrade_adds_columns_and_verifies_nobody(db):
    conn, module = db
    seed(conn, [None, None])

    run_upgrade(conn, module)

    assert {
        "phone_verified_at",
        "captcha_verified_at",
        "verification_completed_at",
    } <= columns(conn)
    # Crucially: no existing user is auto-verified.
    stamped = conn.exec_driver_sql(
        "SELECT COUNT(*) FROM users WHERE verification_completed_at IS NOT NULL"
    ).scalar()
    assert stamped == 0


def test_upgrade_normalizes_existing_phones_in_place(db):
    conn, module = db
    seed(conn, ["09121234567", "+98 935 111 2233", None, "  "])

    run_upgrade(conn, module)

    stored = dict(
        conn.exec_driver_sql("SELECT id, phone FROM users ORDER BY id").fetchall()
    )
    assert stored[1] == "+989121234567"
    assert stored[2] == "+989351112233"
    assert stored[3] is None
    assert stored[4] is None  # blank string became NULL, not a duplicate key
    # Normalizing must not have granted verification to anyone.
    assert (
        conn.exec_driver_sql(
            "SELECT COUNT(*) FROM users WHERE phone_verified_at IS NOT NULL"
        ).scalar()
        == 0
    )


def test_upgrade_aborts_on_a_phone_it_cannot_normalize(db):
    conn, module = db
    seed(conn, ["09121234567", "not-a-number"])

    with pytest.raises(RuntimeError) as excinfo:
        run_upgrade(conn, module)

    message = str(excinfo.value)
    assert "Cannot normalize" in message
    assert "[2]" in message  # names the offending user id


def test_upgrade_aborts_when_two_rows_collapse_onto_one_number(db):
    conn, module = db
    seed(conn, ["09121234567", "+989121234567"])

    with pytest.raises(RuntimeError) as excinfo:
        run_upgrade(conn, module)

    message = str(excinfo.value)
    assert "unique constraint" in message
    assert "[1, 2]" in message  # names both conflicting ids


def test_unique_index_blocks_a_duplicate_after_upgrade(db):
    conn, module = db
    seed(conn, ["09121234567", None])
    run_upgrade(conn, module)

    with pytest.raises(sa.exc.IntegrityError):
        conn.execute(
            sa.text("UPDATE users SET phone = :p WHERE id = 2"),
            {"p": "+989121234567"},
        )


def test_multiple_null_phones_remain_allowed(db):
    conn, module = db
    seed(conn, [None, None, None])
    run_upgrade(conn, module)

    conn.execute(
        sa.text(
            "INSERT INTO users (id, telegram_id, referral_code, phone) "
            "VALUES (99, 9999, 'CODE99', NULL)"
        )
    )
    assert (
        conn.exec_driver_sql(
            "SELECT COUNT(*) FROM users WHERE phone IS NULL"
        ).scalar()
        == 4
    )


def test_downgrade_removes_columns_and_index(db):
    conn, module = db
    seed(conn, ["09121234567"])
    run_upgrade(conn, module)

    run_downgrade(conn, module)

    assert not {
        "phone_verified_at",
        "captcha_verified_at",
        "verification_completed_at",
    } & columns(conn)
    # Duplicates are permitted again once the unique index is gone.
    conn.execute(
        sa.text(
            "INSERT INTO users (id, telegram_id, referral_code, phone) "
            "VALUES (50, 5000, 'CODE50', '+989121234567')"
        )
    )
    assert (
        conn.exec_driver_sql(
            "SELECT COUNT(*) FROM users WHERE phone = '+989121234567'"
        ).scalar()
        == 2
    )
