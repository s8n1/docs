"""SQLite persistence layer: users, sessions, plans, subscriptions,
payment orders, usage counters, and settings.

Single-file database (stdlib sqlite3) — the app carries everything it needs.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB_PATH = Path(os.environ.get("DIFFEQ_DB", "data/app.db"))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT UNIQUE NOT NULL,
    name          TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'user',
    banned        INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token      TEXT PRIMARY KEY,
    user_id    INTEGER REFERENCES users(id) ON DELETE CASCADE,
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
    solves_per_day INTEGER NOT NULL,
    max_points     INTEGER NOT NULL,
    description    TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS subscriptions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    plan_slug  TEXT NOT NULL,
    starts_at  TEXT NOT NULL,
    ends_at    TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'active',
    source     TEXT NOT NULL DEFAULT 'manual',
    order_id   INTEGER,
    created_at TEXT NOT NULL
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

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

_DEFAULT_PLANS: list[tuple[Any, ...]] = [
    ("free", "Free", "رایگان", 0, 0, 0.0, 0, 5, 500,
     "Limited daily solves for trying the engine."),
    ("pro_monthly", "Pro Monthly", "حرفه‌ای ماهانه", 590_000, 5_900_000, 20.0, 30, 100, 5_000,
     "Full access for one month."),
    ("pro_yearly", "Pro Yearly", "حرفه‌ای سالانه", 5_900_000, 59_000_000, 200.0, 365, 1_000, 20_000,
     "Full access for one year."),
]

_DEFAULT_SETTINGS: dict[str, str] = {
    "premium_models": json.dumps([
        "inverse_problem", "eigenvalue", "reaction_diffusion",
        "laplace_pde", "poisson_pde",
    ]),
    "usdt_wallet": "",
}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Create the schema and seed defaults (idempotent)."""
    conn = connect()
    try:
        conn.executescript(_SCHEMA)
        conn.executemany(
            """INSERT OR IGNORE INTO plans
               (slug, name_en, name_fa, price_toman, price_rial, price_usdt,
                duration_days, solves_per_day, max_points, description)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            _DEFAULT_PLANS,
        )
        for key, value in _DEFAULT_SETTINGS.items():
            conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))
        conn.commit()
    finally:
        conn.close()


def reset_db() -> None:
    """Drop every table and re-initialize (used by tests)."""
    conn = connect()
    try:
        for table in ("usage", "subscriptions", "payment_orders", "sessions",
                      "users", "settings", "plans"):
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