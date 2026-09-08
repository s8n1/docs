"""Plans, subscriptions, usage tracking, and the entitlement gate.

The gate is enforced server-side on every solve: anonymous visitors and
expired subscriptions get the free tier (daily solve cap, points cap, and a
premium-model block list). When a subscription lapses the site automatically
restricts the account again.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from api import db


class LimitError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def list_plans() -> list[dict[str, Any]]:
    rows = db.query("SELECT * FROM plans ORDER BY price_toman")
    out = []
    for r in rows:
        out.append({
            "slug": r["slug"], "name_en": r["name_en"], "name_fa": r["name_fa"],
            "price_toman": r["price_toman"], "price_rial": r["price_rial"],
            "price_usdt": r["price_usdt"], "duration_days": r["duration_days"],
            "solves_per_day": r["solves_per_day"], "max_points": r["max_points"],
            "description": r["description"],
        })
    return out


def get_plan(slug: str) -> dict[str, Any] | None:
    for plan in list_plans():
        if plan["slug"] == slug:
            return plan
    return None


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def get_usage(owner: str, owner_id: str) -> dict[str, int]:
    row = db.query_one(
        "SELECT solves, points FROM usage WHERE owner = ? AND owner_id = ? AND day = ?",
        (owner, owner_id, _today()),
    )
    if not row:
        return {"solves": 0, "points": 0}
    return {"solves": row["solves"], "points": row["points"]}


def record_usage(owner: str, owner_id: str, points: int) -> None:
    conn = db.connect()
    try:
        conn.execute(
            """INSERT INTO usage (owner, owner_id, day, solves, points)
               VALUES (?, ?, ?, 1, ?)
               ON CONFLICT(owner, owner_id, day)
               DO UPDATE SET solves = solves + 1, points = points + excluded.points""",
            (owner, owner_id, _today(), max(points, 0)),
        )
        conn.commit()
    finally:
        conn.close()


def active_subscription(user_id: int) -> dict[str, Any] | None:
    """Return the user's active subscription, lazily expiring overdue rows."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn = db.connect()
    try:
        conn.execute(
            "UPDATE subscriptions SET status = 'expired' "
            "WHERE user_id = ? AND status = 'active' AND ends_at <= ?",
            (user_id, now),
        )
        conn.commit()
        row = conn.execute(
            """SELECT * FROM subscriptions
               WHERE user_id = ? AND status = 'active' AND ends_at > ?
               ORDER BY ends_at DESC LIMIT 1""",
            (user_id, now),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def premium_models() -> list[str]:
    raw = db.get_setting("premium_models", "[]") or "[]"
    try:
        parsed = json.loads(raw)
        return [m for m in parsed if isinstance(m, str)] if isinstance(parsed, list) else []
    except ValueError:
        return []


def get_entitlement(user: dict[str, Any] | None,
                    session: dict[str, Any] | None) -> dict[str, Any]:
    """Compute the current entitlement for a user/session."""
    if user is not None:
        owner, owner_id = "user", str(user["id"])
    elif session is not None:
        owner, owner_id = "session", session["token"]
    else:
        owner, owner_id = "anon", "anon"

    usage = get_usage(owner, owner_id)
    tier = "free"
    plan_slug = "free"
    ends_at = None
    plan = get_plan("free")
    assert plan is not None

    if user is not None:
        sub = active_subscription(user["id"])
        if sub is not None:
            active_plan = get_plan(sub["plan_slug"])
            if active_plan is not None and active_plan["duration_days"] > 0:
                plan = active_plan
                tier = "pro"
                plan_slug = sub["plan_slug"]
                ends_at = sub["ends_at"]

    return {
        "tier": tier,
        "plan_slug": plan_slug,
        "plan_name_en": plan["name_en"],
        "plan_name_fa": plan["name_fa"],
        "ends_at": ends_at,
        "solves_per_day": plan["solves_per_day"],
        "max_points": plan["max_points"],
        "solves_used": usage["solves"],
        "points_used": usage["points"],
        "solves_remaining": max(plan["solves_per_day"] - usage["solves"], 0),
        "premium_models": premium_models(),
    }


def check_access(entitlement: dict[str, Any], model: str, points: int) -> None:
    """Raise LimitError when the current tier cannot run this solve."""
    if entitlement["tier"] == "free" and model in entitlement["premium_models"]:
        raise LimitError(
            "premium_model",
            f"Model '{model}' requires an active Pro subscription",
        )
    if points > entitlement["max_points"]:
        raise LimitError(
            "points_limit",
            f"Points ({points}) exceed your tier limit ({entitlement['max_points']}). "
            "Upgrade for higher resolution.",
        )
    if entitlement["solves_used"] >= entitlement["solves_per_day"]:
        raise LimitError(
            "daily_limit",
            f"Daily solve limit reached ({entitlement['solves_per_day']}/day). "
            "Upgrade to Pro for more.",
        )


def grant_subscription(user_id: int, plan_slug: str, days: int | None = None,
                       source: str = "manual", order_id: int | None = None) -> dict[str, Any]:
    """Grant a plan. If an active subscription exists it is extended."""
    plan = get_plan(plan_slug)
    if plan is None:
        raise ValueError(f"Unknown plan: {plan_slug}")
    duration = days if days and days > 0 else plan["duration_days"]
    if duration <= 0:
        raise ValueError("Plan duration must be positive")
    now = datetime.now(timezone.utc)
    existing = active_subscription(user_id)
    conn = db.connect()
    try:
        if existing:
            ends = datetime.fromisoformat(existing["ends_at"])
            new_end = max(ends, now) + timedelta(days=duration)
            conn.execute(
                "UPDATE subscriptions SET ends_at = ?, status = 'active', "
                "plan_slug = ?, source = ?, order_id = COALESCE(?, order_id) WHERE id = ?",
                (new_end.isoformat(timespec="seconds"), plan_slug, source, order_id, existing["id"]),
            )
            sub_id = existing["id"]
        else:
            starts = now.isoformat(timespec="seconds")
            ends = (now + timedelta(days=duration)).isoformat(timespec="seconds")
            cur = conn.execute(
                "INSERT INTO subscriptions (user_id, plan_slug, starts_at, ends_at, status, source, order_id, created_at) "
                "VALUES (?, ?, ?, ?, 'active', ?, ?, ?)",
                (user_id, plan_slug, starts, ends, source, order_id, starts),
            )
            sub_id = cur.lastrowid
        conn.commit()
        row = conn.execute("SELECT * FROM subscriptions WHERE id = ?", (sub_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()