"""SQLite persistence layer: users, sessions, plans (token packs), payment
orders, usage counters, token wallets/ledger, and settings.

Single-file database (stdlib sqlite3) — the app carries everything it needs.
Schema changes are applied in-place by `_migrate()` so an existing database
keeps working after an upgrade.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB_PATH = Path(os.environ.get("DIFFEQ_DB", "data/app.db"))

# The fixed administrator account. It is created idempotently on startup and
# logs in with username + password only (no phone number, no email needed).
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "13811372")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@diffeq.local")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT,
    email         TEXT UNIQUE NOT NULL,
    name          TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'user',
    banned        INTEGER NOT NULL DEFAULT 0,
    token_balance INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token      TEXT PRIMARY KEY,
    user_id    INTEGER REFERENCES users(id) ON DELETE CASCADE,
    tokens     INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    last_seen  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS plans (
    slug           TEXT PRIMARY KEY,
    name_en        TEXT NOT NULL,
    name_fa        TEXT NOT NULL,
    price_toman    INTEGER NOT NULL,
    price_rial     INTEGER NOT NULL,
    price_usdt     REAL NOT NULL,
    duration_days  INTEGER NOT NULL,
    solves_per_day INTEGER NOT NULL DEFAULT 0,
    tokens         INTEGER NOT NULL DEFAULT 0,
    max_points     INTEGER NOT NULL,
    description    TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS payment_orders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    plan_slug   TEXT NOT NULL,
    gateway     TEXT NOT NULL,
    amount      REAL NOT NULL,
    currency    TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',
    external_id TEXT,
    authority   TEXT,
    txid        TEXT,
    meta        TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS usage (
    owner   TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    day     TEXT NOT NULL,
    solves  INTEGER NOT NULL DEFAULT 0,
    points  INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (owner, owner_id, day)
);

CREATE TABLE IF NOT EXISTS token_ledger (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    owner         TEXT NOT NULL,
    owner_id      TEXT NOT NULL,
    delta         INTEGER NOT NULL,
    reason        TEXT NOT NULL,
    balance_after INTEGER NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_token_ledger_owner ON token_ledger(owner, owner_id);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

# Token packs. Tokens never expire — time plays no role in the subscription.
_DEFAULT_PLANS: list[tuple[Any, ...]] = [
    ("free", "Free", "رایگان", 0, 0, 0.0, 0, 0, 50, 20_000,
     "۵۰ توکن هدیه هنگام ثبت‌نام — بدون نیاز به پرداخت."),
    ("pack_basic", "Basic pack", "پک پایه", 290_000, 2_900_000, 9.0, 0, 0, 500, 20_000,
     "۵۰۰ توکن برای استفادهٔ سبک و متوسط."),
    ("pack_pro", "Pro pack", "پک حرفه‌ای", 990_000, 9_900_000, 29.0, 0, 0, 2_000, 20_000,
     "۲۰۰۰ توکن؛ بهترین ارزش برای کار روزمره."),
    ("pack_mega", "Mega pack", "پک ویژه", 3_900_000, 39_000_000, 99.0, 0, 0, 10_000, 20_000,
     "۱۰٬۰۰۰ توکن برای کار سنگین و تیمی."),
]

# Time-based plans from before the token migration are retired.
_LEGACY_PLAN_SLUGS = ("pro_monthly", "pro_yearly")

# Tokens credited once to still-active time-based subscribers at migration time.
_LEGACY_SUBSCRIPTION_TOKENS = {"pro_monthly": 500, "pro_yearly": 2_000}

_DEFAULT_SETTINGS: dict[str, str] = {
    "usdt_wallet": "",
    "model_token_costs": "{}",
}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Bring an older database up to the current schema (idempotent)."""

    def columns(table: str) -> set[str]:
        return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}

    user_cols = columns("users")
    if "username" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN username TEXT")
    if "token_balance" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN token_balance INTEGER NOT NULL DEFAULT 0")
    if "tokens" not in columns("sessions"):
        conn.execute("ALTER TABLE sessions ADD COLUMN tokens INTEGER NOT NULL DEFAULT 0")
    if "tokens" not in columns("plans"):
        conn.execute("ALTER TABLE plans ADD COLUMN tokens INTEGER NOT NULL DEFAULT 0")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username "
        "ON users(username) WHERE username IS NOT NULL"
    )


def _seed_plans(conn: sqlite3.Connection) -> None:
    conn.executemany(
        """INSERT OR IGNORE INTO plans
           (slug, name_en, name_fa, price_toman, price_rial, price_usdt,
            duration_days, solves_per_day, tokens, max_points, description)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        _DEFAULT_PLANS,
    )
    conn.executemany(
        "DELETE FROM plans WHERE slug = ?", [(slug,) for slug in _LEGACY_PLAN_SLUGS]
    )


def _ensure_admin() -> None:
    """Create the fixed admin account if it does not exist yet.

    Login for this account needs only username + password (no phone number,
    no email confirmation). The credentials can be overridden with the
    ADMIN_USERNAME / ADMIN_PASSWORD environment variables.
    """
    from api import auth  # local import: auth imports db at module level

    username = ADMIN_USERNAME.strip().lower()
    email = ADMIN_EMAIL.strip().lower()
    existing = query_one("SELECT id FROM users WHERE username = ? OR email = ?", (username, email))
    if existing is not None:
        return
    execute(
        "INSERT OR IGNORE INTO users (username, email, name, password_hash, role, banned, "
        "token_balance, created_at) VALUES (?, ?, ?, ?, 'admin', 0, 0, ?)",
        (username, email, "Administrator", auth.hash_password(ADMIN_PASSWORD), utcnow()),
    )


def _migrate_legacy_subscriptions(conn: sqlite3.Connection) -> None:
    """Credit tokens once for time-based subscriptions left from before the
    token migration, so nobody loses access when the plans were retired."""
    tables = {row["name"] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'")}
    if "subscriptions" not in tables:
        return
    rows = conn.execute(
        "SELECT user_id, plan_slug FROM subscriptions "
        "WHERE status = 'active' AND ends_at > ?", (utcnow(),),
    ).fetchall()
    for row in rows:
        credit = _LEGACY_SUBSCRIPTION_TOKENS.get(row["plan_slug"])
        if not credit:
            continue
        reason = f"legacy-migration:{row['user_id']}"
        already = conn.execute(
            "SELECT 1 FROM token_ledger WHERE reason = ?", (reason,)).fetchone()
        if already:
            continue
        current = conn.execute(
            "SELECT token_balance FROM users WHERE id = ?", (row["user_id"],)).fetchone()
        new_balance = int(current["token_balance"] if current else 0) + credit
        conn.execute("UPDATE users SET token_balance = ? WHERE id = ?", (new_balance, row["user_id"]))
        conn.execute(
            "INSERT INTO token_ledger (owner, owner_id, delta, reason, balance_after, created_at) "
            "VALUES ('user', ?, ?, ?, ?, ?)",
            (str(row["user_id"]), credit, reason, new_balance, utcnow()),
        )


def init_db() -> None:
    """Create the schema, apply migrations, and seed defaults (idempotent)."""
    conn = connect()
    try:
        conn.executescript(_SCHEMA)
        _migrate(conn)
        _migrate_legacy_subscriptions(conn)
        _seed_plans(conn)
        for key, value in _DEFAULT_SETTINGS.items():
            conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))
        conn.commit()
    finally:
        conn.close()
    _ensure_admin()


def find_user(identifier: str) -> dict[str, Any] | None:
    """Look an account up by email or username (case-insensitive)."""
    needle = (identifier or "").strip().lower()
    if not needle:
        return None
    return query_one(
        "SELECT id, username, email, name, role, banned, token_balance "
        "FROM users WHERE lower(email) = ? OR lower(username) = ?",
        (needle, needle),
    )


def set_role(user_id: int, role: str) -> None:
    execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))


def set_password_hash(user_id: int, password_hash: str) -> None:
    execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id))


def reset_db() -> None:
    """Drop every table and re-initialize (used by tests)."""
    conn = connect()
    try:
        for table in ("token_ledger", "usage", "payment_orders", "subscriptions",
                      "sessions", "users", "settings", "plans"):
            conn.execute(f"DROP TABLE IF EXISTS {table}")
        conn.commit()
    finally:
        conn.close()
    init_db()


def query(sql: str, args: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    conn = connect()
    try:
        rows = conn.execute(sql, args).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def query_one(sql: str, args: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    rows = query(sql, args)
    return rows[0] if rows else None


def execute(sql: str, args: tuple[Any, ...] = ()) -> int:
    """Run a write statement; returns lastrowid."""
    conn = connect()
    try:
        cur = conn.execute(sql, args)
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_setting(key: str, default: str | None = None) -> str | None:
    row = query_one("SELECT value FROM settings WHERE key = ?", (key,))
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        conn.commit()
    finally:
        conn.close()

