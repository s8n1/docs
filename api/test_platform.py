"""Tests for accounts, subscriptions, payment gateways, and admin."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api import db, payments
from api.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.reset_db()
    yield


def _register(email="user@example.com", password="secret12345"):
    return client.post("/api/auth/register", json={
        "name": "Test User", "email": email, "password": password,
    })


def _solve_body(model="logistic", points=100):
    return {
        "model": model,
        "variables": ["y"],
        "t_span": [0.0, 1.0],
        "initial_values": [1.0],
        "parameters": {"rate": 1.0, "capacity": 10.0},
        "method": "RK45",
        "points": points,
    }


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
def test_register_makes_first_user_admin_and_sets_cookie():
    res = _register()
    assert res.status_code == 200
    data = res.json()
    assert data["user"]["role"] == "admin"
    assert data["entitlement"]["tier"] == "free"
    assert "de_session" in res.cookies

    me = client.get("/api/me")
    assert me.json()["user"]["email"] == "user@example.com"


def test_second_user_is_not_admin_and_login_works():
    _register("first@example.com")
    _register("second@example.com", "password22")
    second = client.post("/api/auth/login", json={
        "email": "second@example.com", "password": "password22",
    })
    assert second.status_code == 200
    assert second.json()["user"]["role"] == "user"


def test_login_rejects_bad_password_and_duplicate_email():
    _register()
    assert client.post("/api/auth/login", json={
        "email": "user@example.com", "password": "wrongpassword"}).status_code == 401
    assert _register().status_code == 409


def test_logout_clears_session():
    _register()
    res = client.post("/api/auth/logout", json={})
    assert res.status_code == 200
    assert client.get("/api/me").json()["user"] is None


# ---------------------------------------------------------------------------
# Entitlement gating on /solve
# ---------------------------------------------------------------------------
def test_guest_solve_is_counted_and_limited_daily():
    for _ in range(5):
        res = client.post("/solve", json=_solve_body())
        assert res.status_code == 200
    res = client.post("/solve", json=_solve_body())
    assert res.status_code == 402
    detail = res.json()["detail"]
    assert detail["code"] == "daily_limit"
    assert detail["upgrade"] is True


def test_points_cap_enforced_on_free_tier():
    res = client.post("/solve", json=_solve_body(points=2000))
    assert res.status_code == 402
    assert res.json()["detail"]["code"] == "points_limit"


def test_premium_model_blocked_for_free_tier():
    body = _solve_body(model="eigenvalue", points=100)
    res = client.post("/solve", json=body)
    assert res.status_code == 402
    assert res.json()["detail"]["code"] == "premium_model"


def test_expired_subscription_returns_to_free_limits():
    _register("paid@example.com", "password22")
    admin = client.post("/api/auth/login", json={
        "email": "paid@example.com", "password": "password22"})
    user_id = admin.json()["user"]["id"]
    # Grant then backdate the subscription so it is already expired.
    client.post("/api/admin/subscriptions/grant", json={
        "user_id": user_id, "plan_slug": "pro_monthly"})
    db.execute(
        "UPDATE subscriptions SET ends_at = '2020-01-01T00:00:00+00:00' WHERE user_id = ?",
        (user_id,),
    )
    me = client.get("/api/me").json()
    assert me["entitlement"]["tier"] == "free"
    res = client.post("/solve", json=_solve_body(model="eigenvalue"))
    assert res.status_code == 402
    assert res.json()["detail"]["code"] == "premium_model"


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------
def test_admin_grant_unlocks_premium_and_raises_daily_cap():
    _register()  # first user = admin (this client keeps the admin cookie)
    bob_client = TestClient(app)
    bob_client.post("/api/auth/register", json={
        "name": "Bob", "email": "bob@example.com", "password": "password22"})
    bob_id = bob_client.get("/api/me").json()["user"]["id"]

    res = client.post("/api/admin/subscriptions/grant", json={
        "user_id": bob_id, "plan_slug": "pro_monthly"})
    assert res.status_code == 200

    # Premium model now allowed for bob.
    res = bob_client.post("/solve", json=_solve_body(model="eigenvalue", points=100))
    assert res.status_code == 200

    # Daily cap raised from 5 to 100.
    for _ in range(20):
        res = bob_client.post("/solve", json=_solve_body())
        assert res.status_code == 200


def test_admin_endpoints_require_admin_role():
    _register()
    mallory = TestClient(app)
    mallory.post("/api/auth/register", json={
        "name": "Mallory", "email": "mallory@example.com", "password": "password22"})
    assert mallory.get("/api/admin/stats").status_code == 403


def test_admin_stats_users_and_settings():
    _register()
    carol = TestClient(app)
    carol.post("/api/auth/register", json={
        "name": "Carol", "email": "carol@example.com", "password": "password22"})
    stats = client.get("/api/admin/stats").json()
    assert stats["users_total"] == 2
    assert stats["admins"] == 1

    users = client.get("/api/admin/users").json()
    assert len(users) == 2

    res = client.post("/api/admin/settings", json={
        "key": "usdt_wallet", "value": "TXyz123"})
    assert res.status_code == 200
    assert db.get_setting("usdt_wallet") == "TXyz123"

    bad = client.post("/api/admin/settings", json={
        "key": "not_editable", "value": "x"})
    assert bad.status_code == 422


def test_ban_disables_login_and_solving():
    _register()
    dave = TestClient(app)
    dave.post("/api/auth/register", json={
        "name": "Dave", "email": "dave@example.com", "password": "password22"})
    users = client.get("/api/admin/users").json()
    dave_row = next(u for u in users if u["email"] == "dave@example.com")
    client.patch(f"/api/admin/users/{dave_row['id']}/ban", json={"banned": True})
    res = dave.post("/api/auth/login", json={
        "email": "dave@example.com", "password": "password22"})
    assert res.status_code == 403


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------
def test_crypto_flow_pending_then_admin_confirms():
    _register("miner@example.com", "password22")
    client.post("/api/admin/settings", json={
        "key": "usdt_wallet", "value": "TXcrypto123"})

    res = client.post("/api/payment/start", json={
        "plan_slug": "pro_monthly", "gateway": "crypto"})
    assert res.status_code == 200
    data = res.json()
    assert data["gateway"] == "crypto"
    assert data["network"] == "TRC20"
    assert data["amount_usdt"] == 20.0
    assert data["wallet"] == "TXcrypto123"

    tx = client.post("/api/payment/crypto/tx", json={
        "order_id": data["order_id"], "txid": "deadbeef1234"})
    assert tx.status_code == 200
    assert tx.json()["status"] == "pending_confirm"

    # Still restricted until confirmed.
    assert client.get("/api/me").json()["entitlement"]["tier"] == "free"

    confirm = client.post(f"/api/admin/orders/{data['order_id']}/confirm", json={})
    assert confirm.status_code == 200
    assert confirm.json()["order"]["status"] == "paid"

    me = client.get("/api/me").json()
    assert me["entitlement"]["tier"] == "pro"
    assert me["entitlement"]["plan_slug"] == "pro_monthly"


def test_crypto_payment_requires_login():
    client.post("/api/auth/logout", json={})
    res = client.post("/api/payment/start", json={
        "plan_slug": "pro_monthly", "gateway": "crypto"})
    assert res.status_code == 401


def test_zarinpal_flow_with_mocked_gateway(monkeypatch):
    _register("zp@example.com", "password22")

    def fake_request(order, callback_url):
        payments.update_order(order["id"], authority="AUTH12345")
        return "AUTH12345", "https://sandbox.zarinpal.com/pg/StartPay/AUTH12345"

    def fake_verify(order, authority):
        return True, {"ref_id": "REF777"}

    monkeypatch.setattr(payments, "zarinpal_request", fake_request)
    monkeypatch.setattr(payments, "zarinpal_verify", fake_verify)

    res = client.post("/api/payment/start", json={
        "plan_slug": "pro_monthly", "gateway": "zarinpal"})
    assert res.status_code == 200
    assert "StartPay/AUTH12345" in res.json()["redirect_url"]

    cb = client.get("/api/payment/zarinpal/callback",
                    params={"Authority": "AUTH12345", "Status": "OK"},
                    follow_redirects=False)
    assert cb.status_code == 303
    assert "result=success" in cb.headers["location"]
    assert client.get("/api/me").json()["entitlement"]["tier"] == "pro"


def test_idpay_flow_with_mocked_gateway(monkeypatch):
    _register("ip@example.com", "password22")

    def fake_request(order, callback_url):
        payments.update_order(order["id"], external_id="IDPAY-XYZ")
        return "IDPAY-XYZ", "https://idpay.ir/link"

    def fake_verify(order, payment_id):
        return True, {"track_id": "TRACK9"}

    monkeypatch.setattr(payments, "idpay_request", fake_request)
    monkeypatch.setattr(payments, "idpay_verify", fake_verify)

    res = client.post("/api/payment/start", json={
        "plan_slug": "pro_yearly", "gateway": "idpay"})
    assert res.status_code == 200
    assert res.json()["redirect_url"] == "https://idpay.ir/link"

    order_id = res.json()["order_id"]
    cb = client.get("/api/payment/idpay/callback",
                    params={"id": "IDPAY-XYZ", "order_id": str(order_id)},
                    follow_redirects=False)
    assert cb.status_code == 303
    assert "result=success" in cb.headers["location"]
    assert client.get("/api/me").json()["entitlement"]["tier"] == "pro"


def test_zarinpal_without_merchant_id_is_clean_503(monkeypatch):
    _register("nokey@example.com", "password22")
    monkeypatch.delenv("ZARINPAL_MERCHANT_ID", raising=False)
    res = client.post("/api/payment/start", json={
        "plan_slug": "pro_monthly", "gateway": "zarinpal"})
    assert res.status_code == 503
    assert "ZARINPAL_MERCHANT_ID" in res.json()["detail"]


def test_my_orders_lists_user_orders():
    _register("orders@example.com", "password22")
    client.post("/api/admin/settings", json={"key": "usdt_wallet", "value": "TXw"})
    client.post("/api/payment/start", json={
        "plan_slug": "pro_monthly", "gateway": "crypto"})
    orders = client.get("/api/my-orders").json()
    assert len(orders) == 1
    assert orders[0]["gateway"] == "crypto"
    assert orders[0]["status"] == "pending"