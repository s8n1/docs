"""Payment gateways: ZarinPal, IDPay, and direct USDT (TRC20) wallet.

Orders are persisted in SQLite; callbacks verify with the gateway and only
then credit the pack's tokens to the buyer's wallet (tokens never expire, so
no subscription time is involved). Crypto payments are address-based: the user
sends USDT-TRC20 to the configured wallet and submits a TXID, which the admin
confirms — no third-party crypto processor required.
"""
from __future__ import annotations

import json
import os
from typing import Any

import httpx

from api import db, tokens
from api.plans import get_plan

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
    """Mark an order paid and credit the pack's tokens to the buyer.

    Only pending orders can be confirmed — confirming twice (e.g. a replayed
    callback or a manual admin click) must not credit the tokens again.
    """
    order = db.query_one("SELECT * FROM payment_orders WHERE id = ?", (order_id,))
    if order is None:
        raise PaymentError("Order not found")
    if order["status"] not in ("pending", "pending_confirm"):
        raise PaymentError(f"Order is already {order['status']}")
    plan = get_plan(order["plan_slug"])
    if plan is None:
        raise PaymentError(f"Plan '{order['plan_slug']}' no longer exists")
    credited = int(plan["tokens"])
    meta = json.loads(order["meta"] or "{}")
    if ref:
        meta["ref"] = ref
    meta["tokens"] = credited
    order = update_order(order_id, status="paid", meta=json.dumps(meta))
    if order["user_id"] is not None and credited > 0:
        tokens.grant(
            "user", str(order["user_id"]), credited,
            f"payment:{order['gateway']}:{order['plan_slug']}",
        )
    return order


# ---------------------------------------------------------------------------
# ZarinPal (v4 REST)
# ---------------------------------------------------------------------------
def _zarinpal_base() -> tuple[str, str]:
    sandbox = _sandbox("ZARINPAL_SANDBOX")
    if sandbox:
        return "https://sandbox.zarinpal.com/pg/v4", "https://sandbox.zarinpal.com/pg/StartPay/"
    return "https://payment.zarinpal.com/pg/v4", "https://payment.zarinpal.com/pg/StartPay/"


def _zarinpal_amount(amount: float) -> tuple[int, str]:
    """ZarinPal v4 amount + currency. Prices are stored in Toman (IRT).

    The default is IRR (Rial) because ZarinPal's verify endpoint documents
    Rial amounts; set ZARINPAL_CURRENCY=IRT to send Toman directly.
    """
    currency = (os.environ.get("ZARINPAL_CURRENCY", "IRR") or "IRR").strip().upper()
    if currency == "IRT":
        return int(amount), "IRT"
    return int(amount) * 10, "IRR"


def zarinpal_request(order: dict[str, Any], callback_url: str) -> tuple[str, str]:
    merchant = os.environ.get("ZARINPAL_MERCHANT_ID", "")
    if not merchant:
        raise PaymentError("ZARINPAL_MERCHANT_ID is not configured")
    base, start = _zarinpal_base()
    amount, currency = _zarinpal_amount(order["amount"])
    body = {
        "merchant_id": merchant,
        "amount": amount,
        "currency": currency,
        "callback_url": callback_url,
        "description": f"DiffEQ tokens — pack {order['plan_slug']}",
        "metadata": {"order_id": str(order["id"])},
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
    if not merchant:
        raise PaymentError("ZARINPAL_MERCHANT_ID is not configured")
    base, _ = _zarinpal_base()
    amount, _currency = _zarinpal_amount(order["amount"])
    body = {"merchant_id": merchant, "amount": amount, "authority": authority}
    with httpx.Client(timeout=25) as client:
        resp = client.post(f"{base}/payment/verify.json", json=body)
        data = resp.json()
    data_block = data.get("data", {}) or {}
    code = data_block.get("code")
    # 100 = verified now, 101 = already verified (never credits twice: the
    # order status guard inside confirm_order rejects replays).
    if code in (100, 101):
        return True, {"ref_id": data_block.get("ref_id"), "code": code, "raw": data}
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
    plan = get_plan(order["plan_slug"])
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
        "tokens": int(plan["tokens"]) if plan else 0,
        "explorer": "https://tronscan.org/#/transaction/",
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