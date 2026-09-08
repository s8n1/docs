"""Payment gateways: ZarinPal, IDPay, and direct USDT (TRC20) wallet.

Orders are persisted in SQLite; callbacks verify with the gateway and only
then activate the subscription. Crypto payments are address-based: the user
sends USDT-TRC20 to the configured wallet and submits a TXID, which the admin
confirms — no third-party crypto processor required.
"""
from __future__ import annotations

import json
import os
from typing import Any

import httpx

from api import db
from api.plans import get_plan, grant_subscription

GATEWAYS = ("zarinpal", "idpay", "crypto")


class PaymentError(RuntimeError):
    pass


def _sandbox(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes")


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------
def create_order(user_id: int, plan_slug: str, gateway: str) -> dict[str, Any]:
    if gateway not in GATEWAYS:
        raise ValueError(f"Unknown gateway: {gateway}")
    plan = get_plan(plan_slug)
    if plan is None:
        raise ValueError(f"Unknown plan: {plan_slug}")
    if gateway == "zarinpal":
        amount, currency = plan["price_toman"], "toman"
    elif gateway == "idpay":
        amount, currency = plan["price_rial"], "rial"
    else:
        amount, currency = plan["price_usdt"], "usdt"
    now = db.utcnow()
    order_id = db.execute(
        "INSERT INTO payment_orders (user_id, plan_slug, gateway, amount, currency, status, meta, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, 'pending', '{}', ?, ?)",
        (user_id, plan_slug, gateway, amount, currency, now, now),
    )
    return db.query_one("SELECT * FROM payment_orders WHERE id = ?", (order_id,))  # type: ignore[return-value]


def update_order(order_id: int, **fields: Any) -> dict[str, Any]:
    sets = ", ".join(f"{k} = ?" for k in fields)
    db.execute(
        f"UPDATE payment_orders SET {sets}, updated_at = ? WHERE id = ?",
        tuple(fields.values()) + (db.utcnow(), order_id),
    )
    return db.query_one("SELECT * FROM payment_orders WHERE id = ?", (order_id,))  # type: ignore[return-value]


def confirm_order(order_id: int, ref: str | None = None) -> dict[str, Any]:
    """Mark an order paid and activate/extend the subscription.

    Only pending orders can be confirmed — confirming twice (e.g. a replayed
    callback or a manual admin click) must not grant the plan again.
    """
    order = db.query_one("SELECT * FROM payment_orders WHERE id = ?", (order_id,))
    if order is None:
        raise PaymentError("Order not found")
    if order["status"] not in ("pending", "pending_confirm"):
        raise PaymentError(f"Order is already {order['status']}")
    meta = json.loads(order["meta"] or "{}")
    if ref:
        meta["ref"] = ref
    order = update_order(order_id, status="paid", meta=json.dumps(meta))
    if order["user_id"] is not None:
        grant_subscription(order["user_id"], order["plan_slug"],
                           source=f"payment:{order['gateway']}", order_id=order_id)
    return order


# ---------------------------------------------------------------------------
# ZarinPal (v4 REST)
# ---------------------------------------------------------------------------
def _zarinpal_base() -> tuple[str, str]:
    sandbox = _sandbox("ZARINPAL_SANDBOX")
    if sandbox:
        return "https://sandbox.zarinpal.com/pg/v4", "https://sandbox.zarinpal.com/pg/StartPay/"
    return "https://payment.zarinpal.com/pg/v4", "https://payment.zarinpal.com/pg/StartPay/"


def zarinpal_request(order: dict[str, Any], callback_url: str) -> tuple[str, str]:
    merchant = os.environ.get("ZARINPAL_MERCHANT_ID", "")
    if not merchant:
        raise PaymentError("ZARINPAL_MERCHANT_ID is not configured")
    base, start = _zarinpal_base()
    body = {
        "merchant_id": merchant,
        "amount": int(order["amount"]),
        "callback_url": callback_url,
        "description": f"DiffEQ subscription — plan {order['plan_slug']}",
    }
    with httpx.Client(timeout=25) as client:
        resp = client.post(f"{base}/payment/request.json", json=body)
        data = resp.json()
    data_block = data.get("data", {}) or {}
    if data_block.get("code") != 100 or not data_block.get("authority"):
        raise PaymentError(f"ZarinPal request failed: {data}")
    authority = data_block["authority"]
    update_order(order["id"], authority=authority)
    return authority, f"{start}{authority}"


def zarinpal_verify(order: dict[str, Any], authority: str) -> tuple[bool, dict[str, Any]]:
    merchant = os.environ.get("ZARINPAL_MERCHANT_ID", "")
    base, _ = _zarinpal_base()
    body = {"merchant_id": merchant, "amount": int(order["amount"]), "authority": authority}
    with httpx.Client(timeout=25) as client:
        resp = client.post(f"{base}/payment/verify.json", json=body)
        data = resp.json()
    data_block = data.get("data", {}) or {}
    if data_block.get("code") == 100:
        return True, {"ref_id": data_block.get("ref_id"), "raw": data}
    return False, data_block


# ---------------------------------------------------------------------------
# IDPay (v1.1 REST)
# ---------------------------------------------------------------------------
def _idpay_headers() -> dict[str, str]:
    key = os.environ.get("IDPAY_API_KEY", "")
    if not key:
        raise PaymentError("IDPAY_API_KEY is not configured")
    headers = {"X-API-KEY": key, "Content-Type": "application/json"}
    if _sandbox("IDPAY_SANDBOX"):
        headers["X-SANDBOX"] = "1"
    return headers


def idpay_request(order: dict[str, Any], callback_url: str) -> tuple[str, str]:
    headers = _idpay_headers()
    body = {
        "order_id": str(order["id"]),
        "amount": int(order["amount"]),
        "callback": callback_url,
        "name": f"DiffEQ subscription — plan {order['plan_slug']}",
    }
    with httpx.Client(timeout=25) as client:
        resp = client.post("https://api.idpay.ir/v1.1/payment", json=body, headers=headers)
        data = resp.json()
    if data.get("error_code"):
        raise PaymentError(f"IDPay request failed: {data}")
    payment_id = str(data.get("id", ""))
    link = str(data.get("link", ""))
    if not payment_id or not link:
        raise PaymentError(f"IDPay returned an incomplete response: {data}")
    update_order(order["id"], external_id=payment_id)
    return payment_id, link


def idpay_verify(order: dict[str, Any], payment_id: str) -> tuple[bool, dict[str, Any]]:
    headers = _idpay_headers()
    body = {"id": payment_id, "order_id": str(order["id"])}
    with httpx.Client(timeout=25) as client:
        resp = client.post("https://api.idpay.ir/v1.1/payment/verify", json=body, headers=headers)
        data = resp.json()
    if data.get("status") == 100:
        return True, {"track_id": data.get("track_id"), "payment_no": data.get("payment_no"), "raw": data}
    return False, data


# ---------------------------------------------------------------------------
# Crypto — direct USDT (TRC20) wallet
# ---------------------------------------------------------------------------
def crypto_start(order: dict[str, Any]) -> dict[str, Any]:
    wallet = db.get_setting("usdt_wallet", "") or os.environ.get("USDT_TRC20_WALLET", "")
    if not wallet:
        raise PaymentError("USDT wallet is not configured")
    meta = json.loads(order["meta"] or "{}")
    meta["wallet"] = wallet
    meta["network"] = "TRC20"
    update_order(order["id"], meta=json.dumps(meta))
    return {
        "gateway": "crypto",
        "order_id": order["id"],
        "amount_usdt": order["amount"],
        "wallet": wallet,
        "network": "TRC20",
    }


def crypto_submit_tx(order_id: int, txid: str, user_id: int) -> dict[str, Any]:
    order = db.query_one("SELECT * FROM payment_orders WHERE id = ?", (order_id,))
    if order is None:
        raise PaymentError("Order not found")
    if order["gateway"] != "crypto":
        raise PaymentError("Not a crypto order")
    if order["user_id"] != user_id:
        raise PaymentError("Order does not belong to this account")
    if order["status"] not in ("pending", "pending_confirm"):
        raise PaymentError("Order is not awaiting payment")
    return update_order(order_id, status="pending_confirm", txid=txid)