"""Admin API: dashboard stats, account management (any account is visible and
adjustable), token grants/adjustments, payment order review (including crypto
confirmation), the token ledger, and site settings.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api import db, payments, plans, tokens
from api.auth import require_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])

_ALLOWED_SETTINGS = {"usdt_wallet", "model_token_costs"}


class RoleBody(BaseModel):
    role: str


class BanBody(BaseModel):
    banned: bool


class SettingsBody(BaseModel):
    key: str
    value: str


class TokensAdjustBody(BaseModel):
    delta: int = Field(ge=-10_000_000, le=10_000_000)
    reason: str = Field(default="admin adjustment", max_length=120)


class GrantTokensBody(BaseModel):
    user_id: int
    plan_slug: str


@router.get("/stats")
def stats(_: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    today = datetime.now(timezone.utc).date().isoformat()
    users_total = db.query_one("SELECT COUNT(*) AS c FROM users")["c"]
    admins = db.query_one("SELECT COUNT(*) AS c FROM users WHERE role = 'admin'")["c"]
    banned = db.query_one("SELECT COUNT(*) AS c FROM users WHERE banned = 1")["c"]
    tokens_outstanding = db.query_one(
        "SELECT COALESCE(SUM(token_balance), 0) AS c FROM users")["c"]
    tokens_sold = db.query_one(
        "SELECT COALESCE(SUM(delta), 0) AS c FROM token_ledger WHERE delta > 0")["c"]
    tokens_spent = db.query_one(
        "SELECT COALESCE(SUM(-delta), 0) AS c FROM token_ledger WHERE delta < 0")["c"]
    orders_total = db.query_one("SELECT COUNT(*) AS c FROM payment_orders")["c"]
    paid_orders = db.query_one(
        "SELECT COUNT(*) AS c FROM payment_orders WHERE status = 'paid'")["c"]
    pending_orders = db.query_one(
        "SELECT COUNT(*) AS c FROM payment_orders WHERE status = 'pending_confirm'")["c"]
    revenue_rows = db.query(
        "SELECT currency, SUM(amount) AS total FROM payment_orders WHERE status = 'paid' GROUP BY currency")
    revenue = {r["currency"]: r["total"] for r in revenue_rows}
    solves_today = db.query_one(
        "SELECT COALESCE(SUM(solves), 0) AS c FROM usage WHERE day = ?", (today,))["c"]
    return {
        "users_total": users_total,
        "admins": admins,
        "banned": banned,
        "tokens_outstanding": tokens_outstanding,
        "tokens_sold": tokens_sold,
        "tokens_spent": tokens_spent,
        "orders_total": orders_total,
        "paid_orders": paid_orders,
        "pending_orders": pending_orders,
        "revenue": revenue,
        "solves_today": solves_today,
    }


@router.get("/users")
def list_users(_: dict[str, Any] = Depends(require_admin)) -> list[dict[str, Any]]:
    users = db.query(
        "SELECT id, username, email, name, role, banned, token_balance, created_at "
        "FROM users ORDER BY id")
    out = []
    for user in users:
        out.append({
            **user,
            "banned": bool(user["banned"]),
            "tokens": user["token_balance"],
            "tokens_spent": tokens.spent("user", str(user["id"])),
        })
    return out


@router.patch("/users/{user_id}/role")
def set_role(user_id: int, body: RoleBody,
             admin: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    if body.role not in ("user", "admin"):
        raise HTTPException(422, "Role must be 'user' or 'admin'")
    if user_id == admin["id"]:
        raise HTTPException(422, "You cannot change your own role")
    if body.role == "user":
        admins = db.query_one("SELECT COUNT(*) AS c FROM users WHERE role = 'admin'")["c"]
        target = db.query_one("SELECT role FROM users WHERE id = ?", (user_id,))
        if admins <= 1 and target and target["role"] == "admin":
            raise HTTPException(422, "Cannot demote the last admin")
    db.execute("UPDATE users SET role = ? WHERE id = ?", (body.role, user_id))
    return {"ok": True, "user_id": user_id, "role": body.role}


@router.patch("/users/{user_id}/ban")
def set_ban(user_id: int, body: BanBody,
            admin: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    if user_id == admin["id"] and body.banned:
        raise HTTPException(422, "You cannot ban your own account")
    db.execute("UPDATE users SET banned = ? WHERE id = ?", (1 if body.banned else 0, user_id))
    return {"ok": True, "user_id": user_id, "banned": body.banned}


@router.post("/users/{user_id}/tokens")
def adjust_tokens(user_id: int, body: TokensAdjustBody,
                  _: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    """Add or remove tokens on any account (negative delta = deduction)."""
    row = db.query_one("SELECT id FROM users WHERE id = ?", (user_id,))
    if row is None:
        raise HTTPException(404, "User not found")
    if body.delta == 0:
        raise HTTPException(422, "Delta must not be zero")
    if body.delta > 0:
        balance = tokens.grant("user", str(user_id), body.delta, body.reason)
    else:
        balance = tokens.charge("user", str(user_id), -body.delta, body.reason)
    return {"ok": True, "user_id": user_id, "delta": body.delta, "tokens": balance}


@router.post("/tokens/grant")
def grant_tokens(body: GrantTokensBody,
                 _: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    plan = plans.get_plan(body.plan_slug)
    if plan is None:
        raise HTTPException(422, f"Unknown plan: {body.plan_slug}")
    if int(plan["tokens"]) <= 0:
        raise HTTPException(422, "This plan does not credit any tokens")
    if db.query_one("SELECT id FROM users WHERE id = ?", (body.user_id,)) is None:
        raise HTTPException(404, "User not found")
    balance = tokens.grant(
        "user", str(body.user_id), int(plan["tokens"]), f"admin-grant:{plan['slug']}")
    return {"ok": True, "user_id": body.user_id, "credited": plan["tokens"], "tokens": balance}


@router.post("/subscriptions/grant")
def grant_tokens_legacy(body: GrantTokensBody,
                        admin: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    """Legacy route: token packs replaced time-based subscriptions."""
    return grant_tokens(body, admin)


@router.get("/tokens/ledger")
def token_ledger(_: dict[str, Any] = Depends(require_admin)) -> list[dict[str, Any]]:
    return tokens.recent(100)


@router.get("/orders")
def list_orders(_: dict[str, Any] = Depends(require_admin)) -> list[dict[str, Any]]:
    return db.query(
        "SELECT o.*, u.email, u.username FROM payment_orders o "
        "LEFT JOIN users u ON u.id = o.user_id "
        "ORDER BY o.id DESC LIMIT 200")


@router.post("/orders/{order_id}/confirm")
def confirm_order(order_id: int, _: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    try:
        order = payments.confirm_order(order_id, ref="admin-confirmed")
    except payments.PaymentError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"ok": True, "order": order}


@router.get("/settings")
def get_settings(_: dict[str, Any] = Depends(require_admin)) -> dict[str, str]:
    rows = db.query("SELECT key, value FROM settings")
    return {r["key"]: r["value"] for r in rows}


@router.post("/settings")
def set_settings(body: SettingsBody, _: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    if body.key not in _ALLOWED_SETTINGS:
        raise HTTPException(422, f"Setting '{body.key}' is not editable")
    if body.key == "model_token_costs":
        try:
            parsed = body.value.strip() or "{}"
            items = __import__("json").loads(parsed)
            if not isinstance(items, dict) or not all(
                isinstance(k, str)
                and isinstance(v, int)
                and not isinstance(v, bool)
                and v >= 0
                for k, v in items.items()
            ):
                raise ValueError
        except (ValueError, TypeError):
            raise HTTPException(
                422, "model_token_costs must be a JSON object of model name → token cost"
            ) from None
    db.set_setting(body.key, body.value)
    return {"ok": True, "key": body.key, "value": body.value}
