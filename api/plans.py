"""Plans (token packs), usage analytics, and the token entitlement gate.

Subscriptions are **token-based**: buying a pack credits tokens that never
expire, so time plays no role. Every solve or tool call costs tokens
according to the difficulty of the computation (`api.tokens`), and the gate
below blocks the request whenever the balance cannot cover it.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from api import db, tokens


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
            "price_usdt": r["price_usdt"], "tokens": r["tokens"],
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
    """Analytics counters only — tokens are debited separately."""
    conn = db.connect()
    try:
        conn.execute(
            """INSERT INTO usage (owner, owner_id, day, solves, points)
               VALUES (?, ?, ?, 1, ?)
               ON CONFLICT(owner, owner_id, day)
               DO UPDATE SET solves = solves + 1, points = points + excluded.points""",
            (owner, owner_id, _today(), max(int(points), 0)),
        )
        conn.commit()
    finally:
        conn.close()


def owner_keys(user: dict[str, Any] | None,
               session: dict[str, Any] | None) -> tuple[str, str]:
    """Wallet keys for the caller: account first, then anonymous session."""
    if user is not None:
        return "user", str(user["id"])
    if session is not None:
        return "session", session["token"]
    return "anon", "anon"


def get_entitlement(user: dict[str, Any] | None,
                    session: dict[str, Any] | None) -> dict[str, Any]:
    """Current token balance, prices, and today's usage for the caller."""
    owner, owner_id = owner_keys(user, session)
    usage = get_usage(owner, owner_id)
    is_admin = bool(user is not None and user.get("role") == "admin")
    balance = None if is_admin else tokens.balance(owner, owner_id)
    if is_admin:
        tier = "admin"
    else:
        tier = "pro" if int(balance or 0) > 0 else "free"
    return {
        "tier": tier,
        "unlimited": is_admin,
        "tokens": balance,
        "tokens_spent": tokens.spent(owner, owner_id),
        "solves_used": usage["solves"],
        "points_used": usage["points"],
        "model_costs": tokens.model_costs(),
        "tool_costs": tokens.TOOL_COSTS,
        "included_points": tokens.POINTS_INCLUDED,
        "points_per_extra_token": tokens.POINTS_PER_EXTRA_TOKEN,
    }


def check_access(entitlement: dict[str, Any], cost: int, label: str = "This operation") -> None:
    """Raise LimitError when the balance cannot cover the operation's cost."""
    if entitlement.get("unlimited"):
        return
    balance = int(entitlement.get("tokens") or 0)
    if int(cost) > balance:
        raise LimitError(
            "insufficient_tokens",
            f"{label} costs {cost} token(s) and your balance is {balance}.",
        )
