"""Admin API: dashboard stats, user management, subscription grants,
payment order review (including crypto confirmation), and site settings.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api import db, payments, plans
from api.auth import require_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])

_ALLOWED_SETTINGS = {"usdt_wallet", "premium_models"}


class GrantBody(BaseModel):
    user_id: int
    plan_slug: str
    days: int | None = Field(default=None, ge=1, le=3650)


class RoleBody(BaseModel):
    role: str


class BanBody(BaseModel):
    banned: bool


class SettingsBody(BaseModel):
    key: str
    value: str


@router.get("/stats")
def stats(_: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    today = datetime.now(timezone.utc).date().isoformat()
    users_total = db.query_one("SELECT COUNT(*) AS c FROM users")["c"]
    admins = db.query_one("SELECT COUNT(*) AS c FROM users WHERE role = 'admin'")["c"]
    banned = db.query_one("SELECT COUNT(*) AS c FROM users WHERE banned = 1")["c"]
    active_subs = db.query_one(
        "SELECT COUNT(*) AS c FROM subscriptions WHERE status = 'active' AND ends_at > ?",
        (datetime.now(timezone.utc).isoformat(timespec="seconds"),),
    )["c"]
    orders_total = db.query_one("SELECT COUNT(*) AS c FROM payment_orders")["c"]
    paid_orders = db.query_one(
        "SELECT COUNT(*) AS c FROM payment_orders WHERE status = 'paid'")["c"]
    revenue_rows = db.query(
        "SELECT currency, SUM(amount) AS total FROM payment_orders WHERE status = 'paid' GROUP BY currency")
    revenue = {r["currency"]: r["total"] for r in revenue_rows}
    solves_today = db.query_one(
        "SELECT COALESCE(SUM(solves), 0) AS c FROM usage WHERE day = ?", (today,))["c"]
    return {
        "users_total": users_total,
        "admins": admins,
        "banned": banned,
        "active_subscriptions": active_subs,
        "orders_total": orders_total,
        "paid_orders": paid_orders,
        "revenue": revenue,
        "solves_today": solves_today,
    }


@router.get("/users")
def list_users(_: dict[str, Any] = Depends(require_admin)) -> list[dict[str, Any]]:
    users = db.query("SELECT id, email, name, role, banned, created_at FROM users ORDER BY id")
    out = []
    for user in users:
        sub = plans.active_subscription(user["id"])
        out.append({
            **user,
            "banned": bool(user["banned"]),
            "subscription_plan": sub["plan_slug"] if sub else None,
            "subscription_ends_at": sub["ends_at"] if sub else None,
        })
    return out


@router.patch("/users/{user_id}/role")
def set_role(user_id: int, body: RoleBody,
             _: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    if body.role not in ("user", "admin"):
        raise HTTPException(422, "Role must be 'user' or 'admin'")
    db.execute("UPDATE users SET role = ? WHERE id = ?", (body.role, user_id))
    return {"ok": True, "user_id": user_id, "role": body.role}


@router.patch("/users/{user_id}/ban")
def set_ban(user_id: int, body: BanBody,
            _: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    db.execute("UPDATE users SET banned = ? WHERE id = ?", (1 if body.banned else 0, user_id))
    return {"ok": True, "user_id": user_id, "banned": body.banned}


@router.post("/subscriptions/grant")
def grant(body: GrantBody, _: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    try:
        sub = plans.grant_subscription(body.user_id, body.plan_slug, body.days)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"ok": True, "subscription": sub}


@router.get("/orders")
def list_orders(_: dict[str, Any] = Depends(require_admin)) -> list[dict[str, Any]]:
    return db.query(
        "SELECT o.*, u.email FROM payment_orders o "
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
    if body.key == "premium_models":
        try:
            parsed = body.value.strip() or "[]"
            items = __import__("json").loads(parsed)
            if not isinstance(items, list) or not all(isinstance(i, str) for i in items):
                raise ValueError
        except (ValueError, TypeError):
            raise HTTPException(422, "premium_models must be a JSON array of model names") from None
    db.set_setting(body.key, body.value)
    return {"ok": True, "key": body.key, "value": body.value}