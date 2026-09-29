"""Tests for accounts, the token economy, payment gateways, and admin."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api import auth, db, payments, plans, tokens
from api.main import app
from api.solver_core import MODEL_NAMES

ADMIN_LOGIN = {"identifier": "admin", "password": "13811372"}


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.reset_db()
    auth.reset_login_throttle()
    yield
    auth.reset_login_throttle()


def _client() -> TestClient:
    return TestClient(app)


def _admin() -> TestClient:
    c = _client()
    res = c.post("/api/auth/login", json=ADMIN_LOGIN)
    assert res.status_code == 200, res.text
    return c


def _grant(client: TestClient, delta: int) -> None:
    """Credit tokens for a test that needs more than the signup gift.

    Goes through the admin endpoint so the test does not silently depend on how
    large the gift happens to be, and uses its own client so the caller's
    session cookies are untouched.
    """
    uid = client.get("/api/me").json()["user"]["id"]
    res = _admin().post(f"/api/admin/users/{uid}/tokens", json={"delta": delta, "reason": "test"})
    assert res.status_code == 200, res.text


def test_seeded_admin_exists_and_can_sign_in():
    c = _client()
    res = c.post("/api/auth/login", json=ADMIN_LOGIN)
    assert res.status_code == 200, res.text
    user = res.json()["user"]
    assert user["username"] == "admin"
    assert user["role"] == "admin"
    assert res.json()["entitlement"]["unlimited"] is True


def test_admin_account_is_discoverable_in_the_account_list():
    admin = _admin()
    users = admin.get("/api/admin/users").json()
    assert any(u["username"] == "admin" and u["role"] == "admin" for u in users)


def test_find_user_and_set_role_helpers_promote_an_account():
    _, res = _register(email="owner@example.com", username="owner")
    assert res.status_code == 200
    found = db.find_user("owner@example.com")
    assert found is not None and found["role"] == "user"
    db.set_role(found["id"], "admin")
    assert db.find_user("OWNER").get("role") == "admin"


def test_password_change_requires_the_current_password():
    c, res = _register(email="pw@example.com", password="secret12345")
    assert res.status_code == 200
    wrong = c.post("/api/account/password", json={
        "current_password": "nope-nope", "new_password": "brandnew123"})
    assert wrong.status_code == 401
    short = c.post("/api/account/password", json={
        "current_password": "secret12345", "new_password": "short"})
    assert short.status_code == 422
    ok = c.post("/api/account/password", json={
        "current_password": "secret12345", "new_password": "brandnew123"})
    assert ok.status_code == 200
    fresh = _client()
    assert fresh.post("/api/auth/login", json={
        "identifier": "pw@example.com", "password": "secret12345"}).status_code == 401
    assert fresh.post("/api/auth/login", json={
        "identifier": "pw@example.com", "password": "brandnew123"}).status_code == 200


def test_anonymous_visitor_cannot_change_a_password():
    c = _client()
    c.post("/api/auth/logout", json={})
    res = c.post("/api/account/password", json={
        "current_password": "whatever", "new_password": "brandnew123"})
    assert res.status_code == 401


def _register(email="user@example.com", password="secret12345",
              name="Test User", username=None) -> tuple[TestClient, object]:
    c = _client()
    res = c.post("/api/auth/register", json={
        "name": name, "email": email, "password": password, "username": username,
    })
    return c, res


def _solve_body(model="logistic", points=100, **overrides):
    body = {
        "model": model,
        "variables": ["y"],
        "t_span": [0.0, 1.0],
        "initial_values": [1.0],
        "parameters": {"rate": 1.0, "capacity": 10.0},
        "method": "RK45",
        "points": points,
    }
    body.update(overrides)
    return body


def _balance(client: TestClient) -> int:
    return client.get("/api/me").json()["entitlement"]["tokens"]


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _FakeHttpxClient:
    """Minimal stand-in for httpx.Client so ZarinPal parsing can be tested."""

    payload: dict = {"data": {"code": 100, "authority": "AUTH1"}, "errors": []}
    calls: list = []

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, url, json=None, headers=None):
        type(self).calls.append({"url": url, "json": json})
        return _FakeResponse(type(self).payload)


# ---------------------------------------------------------------------------
# Fixed admin + accounts (no phone number anywhere)
# ---------------------------------------------------------------------------
def test_seeded_admin_logs_in_with_username_only_and_no_phone():
    res = _client().post("/api/auth/login", json=ADMIN_LOGIN)
    assert res.status_code == 200
    user = res.json()["user"]
    assert user["username"] == "admin"
    assert user["role"] == "admin"
    assert "phone" not in user and "phone" not in res.text
    ent = res.json()["entitlement"]
    assert ent["tier"] == "admin" and ent["unlimited"] is True and ent["tokens"] is None


def test_admin_can_also_log_in_with_email_and_bad_password_is_rejected():
    c = _client()
    assert c.post("/api/auth/login", json={
        "identifier": "admin@diffeq.local", "password": "13811372"}).status_code == 200
    assert c.post("/api/auth/login", json={
        "identifier": "admin", "password": "wrong-password"}).status_code == 401
    assert c.post("/api/auth/login", json={"password": "13811372"}).status_code == 422


def test_register_grants_signup_tokens_and_username_login_works():
    c, res = _register(username="neo")
    assert res.status_code == 200
    data = res.json()
    assert data["user"]["role"] == "user"
    assert data["entitlement"]["tokens"] == tokens.SIGNUP_TOKENS
    login = c.post("/api/auth/login", json={"identifier": "neo", "password": "secret12345"})
    assert login.status_code == 200
    assert login.json()["user"]["username"] == "neo"


def test_register_rejects_duplicate_email_and_username():
    _register(username="neo")
    _, again = _register()
    assert again.status_code == 409
    _, dup_user = _register(email="other@example.com", username="neo")
    assert dup_user.status_code == 409
    _, bad_user = _register(email="third@example.com", username="a")
    assert bad_user.status_code == 422


def test_logout_clears_session():
    c, _ = _register()
    c.post("/api/auth/logout", json={})
    assert c.get("/api/me").json()["user"] is None


# ---------------------------------------------------------------------------
# Token economy
# ---------------------------------------------------------------------------
def test_every_model_has_a_positive_token_cost():
    costs = tokens.model_costs()
    missing = [m for m in MODEL_NAMES if m not in costs]
    assert missing == []
    assert all(costs[m] > 0 for m in MODEL_NAMES)


def test_points_add_surcharge_to_the_base_cost():
    assert tokens.cost_for("logistic", 200) == tokens.MODEL_TOKEN_COSTS["logistic"]
    assert tokens.cost_for("logistic", 1_500) == tokens.MODEL_TOKEN_COSTS["logistic"] + 1
    assert tokens.cost_for("logistic", 5_000) == tokens.MODEL_TOKEN_COSTS["logistic"] + 4


def test_anonymous_visitors_get_trial_tokens_and_are_charged():
    c = _client()
    res = c.post("/solve", json=_solve_body())
    assert res.status_code == 200
    charged = res.json()["entitlement"]
    assert charged["tokens_charged"] == tokens.model_costs()["logistic"]
    assert charged["tokens"] == tokens.ANON_TOKENS - charged["tokens_charged"]


def test_solve_debits_tokens_by_model_difficulty():
    c, _ = _register()
    assert _balance(c) == tokens.SIGNUP_TOKENS

    res = c.post("/solve", json=_solve_body(model="separable"))
    assert res.status_code == 200
    assert _balance(c) == tokens.SIGNUP_TOKENS - tokens.model_costs()["separable"]

    # The signup gift is deliberately small, so fund the account rather than
    # assuming it covers a chaotic system.
    _grant(c, 20)

    lorenz = _solve_body(model="lorenz", variables=["x", "y", "z"],
                         initial_values=[1.0, 1.0, 1.0],
                         parameters={"sigma": 10.0, "rho": 28.0, "beta": 2.6666666666666665},
                         t_span=[0.0, 1.0])
    res = c.post("/solve", json=lorenz)
    assert res.status_code == 200
    assert _balance(c) == tokens.SIGNUP_TOKENS - 1 + 20 - tokens.model_costs()["lorenz"]


def test_empty_balance_returns_402_insufficient_tokens():
    c, _ = _register()
    db.execute("UPDATE users SET token_balance = 0")
    res = c.post("/solve", json=_solve_body())
    assert res.status_code == 402
    detail = res.json()["detail"]
    assert detail["code"] == "insufficient_tokens"
    assert detail["upgrade"] is True and detail["upgrade_url"] == "/pricing"


def test_symbolic_analyze_and_enhanced_consume_tool_tokens(monkeypatch):
    def _offline(*_args, **_kwargs):
        from api.ai_provider import AIProviderError
        raise AIProviderError("offline in tests")

    monkeypatch.setattr("api.main.analyze_equation", _offline)
    c, _ = _register()
    _grant(c, 20)   # this test measures costs, not the size of the signup gift
    start = _balance(c)

    res = c.post("/solve/symbolic", json={"equation": "-y", "variable": "y", "independent": "t"})
    assert res.status_code == 200
    assert res.json()["entitlement"]["tokens_charged"] == tokens.TOOL_COSTS["symbolic"]

    res = c.post("/analyze", json={"text": "van der pol oscillator", "language": "en"})
    assert res.status_code == 200
    assert res.json()["entitlement"]["tokens_charged"] == tokens.TOOL_COSTS["analyze"]

    res = c.post("/analyze/enhanced", json={"text": "heat equation", "language": "en"})
    assert res.status_code == 200
    assert res.json()["entitlement"]["tokens_charged"] == tokens.TOOL_COSTS["analyze_enhanced"]

    expected = start - (tokens.TOOL_COSTS["symbolic"] + tokens.TOOL_COSTS["analyze"]
                        + tokens.TOOL_COSTS["analyze_enhanced"])
    assert _balance(c) == expected


def test_admin_solves_are_unlimited_and_free():
    admin = _admin()
    body = _solve_body(model="inverse_problem", variables=["obs"], t_span=[0.0, 5.0],
                       initial_values=[0.0], parameters={}, points=100)
    for _ in range(3):
        res = admin.post("/solve", json=body)
        assert res.status_code == 200
        ent = res.json()["entitlement"]
        assert ent["unlimited"] is True and ent["tokens"] is None
    assert admin.get("/api/me").json()["entitlement"]["tokens"] is None


def test_token_cost_override_from_settings():
    admin = _admin()
    assert admin.post("/api/admin/settings", json={
        "key": "model_token_costs", "value": '{"logistic": 7}'}).status_code == 200
    assert tokens.cost_for("logistic") == 7

    c, _ = _register()
    _grant(c, 20)   # the signup gift alone would not cover a 7-token override
    res = c.post("/solve", json=_solve_body())
    assert res.status_code == 200
    assert _balance(c) == tokens.SIGNUP_TOKENS + 20 - 7

    bad = admin.post("/api/admin/settings", json={
        "key": "model_token_costs", "value": '{"logistic": "many"}'})
    assert bad.status_code == 422


# ---------------------------------------------------------------------------
# Admin: every account is visible and adjustable
# ---------------------------------------------------------------------------
def test_admin_lists_all_accounts_with_token_balances():
    c, _ = _register(username="neo")
    admin = _admin()
    users = admin.get("/api/admin/users").json()
    assert len(users) == 2
    row = next(u for u in users if u["username"] == "neo")
    assert row["tokens"] == tokens.SIGNUP_TOKENS
    assert row["tokens_spent"] == 0
    assert "phone" not in row

    res = admin.post(f"/api/admin/users/{row['id']}/tokens", json={"delta": 100, "reason": "gift"})
    assert res.status_code == 200 and res.json()["tokens"] == tokens.SIGNUP_TOKENS + 100
    assert _balance(c) == tokens.SIGNUP_TOKENS + 100

    res = admin.post(f"/api/admin/users/{row['id']}/tokens", json={"delta": -200})
    assert res.status_code == 200
    assert res.json()["tokens"] == max(0, tokens.SIGNUP_TOKENS + 100 - 200)


def test_token_adjustment_cannot_go_below_zero():
    _, _res = _register()
    admin = _admin()
    users = admin.get("/api/admin/users").json()
    uid = next(u["id"] for u in users if u["email"] == "user@example.com")
    res = admin.post(f"/api/admin/users/{uid}/tokens", json={"delta": -10_000})
    assert res.status_code == 200 and res.json()["tokens"] == 0


def test_admin_can_grant_a_pack_to_any_account():
    c, _ = _register()
    admin = _admin()
    uid = c.get("/api/me").json()["user"]["id"]
    res = admin.post("/api/admin/tokens/grant", json={"user_id": uid, "plan_slug": "pack_basic"})
    assert res.status_code == 200
    assert res.json()["credited"] == 500
    assert _balance(c) == tokens.SIGNUP_TOKENS + 500

    legacy = admin.post("/api/admin/subscriptions/grant", json={
        "user_id": uid, "plan_slug": "pack_pro"})
    assert legacy.status_code == 200
    assert _balance(c) == tokens.SIGNUP_TOKENS + 500 + 2_000


def test_token_ledger_and_stats_are_admin_only():
    c, _ = _register()
    uid = c.get("/api/me").json()["user"]["id"]
    c.post("/solve", json=_solve_body())

    assert c.get("/api/admin/tokens/ledger").status_code == 403
    assert c.post(f"/api/admin/users/{uid}/tokens", json={"delta": 10}).status_code == 403
    assert c.get("/api/admin/stats").status_code == 403

    admin = _admin()
    entries = admin.get("/api/admin/tokens/ledger").json()
    reasons = [e["reason"] for e in entries]
    assert "signup" in reasons and "solve:logistic" in reasons

    stats = admin.get("/api/admin/stats").json()
    assert stats["users_total"] == 2
    assert stats["tokens_spent"] >= 1
    assert stats["tokens_outstanding"] >= 0
    assert stats["solves_today"] == 1


def test_my_tokens_lists_balance_and_history():
    c, _ = _register()
    c.post("/solve", json=_solve_body())
    data = c.get("/api/my-tokens").json()
    assert data["tokens"] == tokens.SIGNUP_TOKENS - 1
    assert data["entries"][0]["reason"] == "solve:logistic"
    assert data["entries"][0]["delta"] == -1
    assert c.get("/api/my-tokens").status_code == 200


def test_ban_blocks_login_and_admin_role_guards_still_hold():
    c, _ = _register(username="neo")
    uid = c.get("/api/me").json()["user"]["id"]
    admin = _admin()
    assert admin.patch(f"/api/admin/users/{uid}/ban", json={"banned": True}).status_code == 200
    assert c.post("/api/auth/login", json={
        "identifier": "neo", "password": "secret12345"}).status_code == 403
    admin.patch(f"/api/admin/users/{uid}/ban", json={"banned": False})
    assert c.post("/api/auth/login", json={
        "identifier": "neo", "password": "secret12345"}).status_code == 200

    me = admin.get("/api/me").json()["user"]
    assert admin.patch(f"/api/admin/users/{me['id']}/role", json={"role": "user"}).status_code == 422
    assert admin.patch(f"/api/admin/users/{me['id']}/ban", json={"banned": True}).status_code == 422

    assert admin.patch(f"/api/admin/users/{uid}/role", json={"role": "admin"}).status_code == 200
    assert admin.patch(f"/api/admin/users/{uid}/role", json={"role": "user"}).status_code == 200


# ---------------------------------------------------------------------------
# Plans
# ---------------------------------------------------------------------------
def test_plans_are_token_packs_without_expiry():
    res = _client().get("/api/plans")
    assert res.status_code == 200
    data = res.json()
    plans_by_slug = {p["slug"]: p for p in data["plans"]}
    assert "pro_monthly" not in plans_by_slug and "pro_yearly" not in plans_by_slug
    assert {"free", "pack_basic", "pack_pro", "pack_mega"} <= set(plans_by_slug)
    for slug, plan in plans_by_slug.items():
        assert plan["tokens"] > 0, slug
        assert "duration_days" not in plan
    assert data["signup_tokens"] == tokens.SIGNUP_TOKENS


# ---------------------------------------------------------------------------
# Payments → tokens
# ---------------------------------------------------------------------------
def test_crypto_purchase_credits_tokens_only_after_admin_confirms():
    c, _ = _register()
    admin = _admin()
    admin.post("/api/admin/settings", json={"key": "usdt_wallet", "value": "TXcrypto123"})

    res = c.post("/api/payment/start", json={"plan_slug": "pack_basic", "gateway": "crypto"})
    assert res.status_code == 200
    data = res.json()
    assert data["network"] == "TRC20" and data["wallet"] == "TXcrypto123"
    assert data["tokens"] == 500

    tx = c.post("/api/payment/crypto/tx", json={
        "order_id": data["order_id"], "txid": "deadbeef1234"})
    assert tx.status_code == 200 and tx.json()["status"] == "pending_confirm"
    assert _balance(c) == tokens.SIGNUP_TOKENS  # nothing credited yet

    confirm = admin.post(f"/api/admin/orders/{data['order_id']}/confirm", json={})
    assert confirm.status_code == 200
    assert confirm.json()["order"]["status"] == "paid"
    assert _balance(c) == tokens.SIGNUP_TOKENS + 500

    # Confirming twice must not credit twice.
    again = admin.post(f"/api/admin/orders/{data['order_id']}/confirm", json={})
    assert again.status_code == 422
    assert _balance(c) == tokens.SIGNUP_TOKENS + 500


def test_crypto_payment_requires_login_and_order_ownership():
    c = _client()
    assert c.post("/api/payment/start", json={
        "plan_slug": "pack_basic", "gateway": "crypto"}).status_code == 401

    owner, _ = _register("owner@example.com")
    admin = _admin()
    admin.post("/api/admin/settings", json={"key": "usdt_wallet", "value": "TXw"})
    order = owner.post("/api/payment/start", json={
        "plan_slug": "pack_basic", "gateway": "crypto"}).json()

    mallory, _ = _register("mallory@example.com")
    res = mallory.post("/api/payment/crypto/tx", json={
        "order_id": order["order_id"], "txid": "evilbeef1234"})
    assert res.status_code == 422 and "not belong" in res.json()["detail"]

    assert owner.post("/api/payment/crypto/tx", json={
        "order_id": order["order_id"], "txid": "deadbeef1234"}).status_code == 200


def test_order_with_deleted_plan_cannot_be_confirmed():
    c, _ = _register()
    admin = _admin()
    uid = c.get("/api/me").json()["user"]["id"]
    order_id = db.execute(
        "INSERT INTO payment_orders (user_id, plan_slug, gateway, amount, currency, status, meta, created_at, updated_at) "
        "VALUES (?, 'ghost_pack', 'crypto', 1, 'usdt', 'pending', '{}', ?, ?)",
        (uid, db.utcnow(), db.utcnow()),
    )
    res = admin.post(f"/api/admin/orders/{order_id}/confirm", json={})
    assert res.status_code == 422
    assert db.query_one("SELECT status FROM payment_orders WHERE id = ?", (order_id,))["status"] == "pending"


def test_zarinpal_flow_with_mocked_gateway(monkeypatch):
    c, _ = _register("zp@example.com")

    def fake_request(order, callback_url):
        payments.update_order(order["id"], authority="AUTH12345")
        return "AUTH12345", "https://sandbox.zarinpal.com/pg/StartPay/AUTH12345"

    def fake_verify(order, authority):
        return True, {"ref_id": "REF777", "code": 100}

    monkeypatch.setattr(payments, "zarinpal_request", fake_request)
    monkeypatch.setattr(payments, "zarinpal_verify", fake_verify)

    res = c.post("/api/payment/start", json={"plan_slug": "pack_pro", "gateway": "zarinpal"})
    assert res.status_code == 200
    assert "StartPay/AUTH12345" in res.json()["redirect_url"]

    cb = c.get("/api/payment/zarinpal/callback",
               params={"Authority": "AUTH12345", "Status": "OK"}, follow_redirects=False)
    assert cb.status_code == 303 and "result=success" in cb.headers["location"]
    assert _balance(c) == tokens.SIGNUP_TOKENS + 2_000


def test_zarinpal_request_sends_rial_amount_and_currency(monkeypatch):
    monkeypatch.setenv("ZARINPAL_MERCHANT_ID", "merchant-1")
    monkeypatch.delenv("ZARINPAL_CURRENCY", raising=False)
    _FakeHttpxClient.payload = {"data": {"code": 100, "authority": "AUTH9"}, "errors": []}
    _FakeHttpxClient.calls = []
    monkeypatch.setattr(payments.httpx, "Client", _FakeHttpxClient)

    order = payments.create_order(None, "pack_basic", "zarinpal")
    authority, url = payments.zarinpal_request(order, "http://localhost/cb")
    assert authority == "AUTH9" and url.endswith("AUTH9")
    body = _FakeHttpxClient.calls[-1]["json"]
    assert body["amount"] == 290_000 * 10  # Toman → Rial by default
    assert body["currency"] == "IRR"
    assert body["callback_url"] == "http://localhost/cb"


def test_zarinpal_verify_accepts_replay_code_101(monkeypatch):
    monkeypatch.setenv("ZARINPAL_MERCHANT_ID", "merchant-1")
    monkeypatch.setattr(payments.httpx, "Client", _FakeHttpxClient)
    _FakeHttpxClient.payload = {"data": {"code": 101, "ref_id": 42}, "errors": []}
    _FakeHttpxClient.calls = []
    ok, info = payments.zarinpal_verify({"id": 1, "amount": 290_000}, "AUTH1")
    assert ok is True and info["code"] == 101
    assert _FakeHttpxClient.calls[-1]["json"]["amount"] == 2_900_000

    _FakeHttpxClient.payload = {"data": {"code": -51, "message": "failed"}, "errors": []}
    ok, _info = payments.zarinpal_verify({"id": 1, "amount": 290_000}, "AUTH2")
    assert ok is False


def test_zarinpal_without_merchant_id_is_a_clean_503(monkeypatch):
    c, _ = _register("nokey@example.com")
    monkeypatch.delenv("ZARINPAL_MERCHANT_ID", raising=False)
    res = c.post("/api/payment/start", json={"plan_slug": "pack_basic", "gateway": "zarinpal"})
    assert res.status_code == 503
    assert "ZARINPAL_MERCHANT_ID" in res.json()["detail"]


def test_idpay_flow_with_mocked_gateway(monkeypatch):
    c, _ = _register("ip@example.com")

    def fake_request(order, callback_url):
        payments.update_order(order["id"], external_id="IDPAY-XYZ")
        return "IDPAY-XYZ", "https://idpay.ir/link"

    monkeypatch.setattr(payments, "idpay_request", fake_request)
    monkeypatch.setattr(payments, "idpay_verify", lambda order, payment_id: (True, {"track_id": "TRACK9"}))

    res = c.post("/api/payment/start", json={"plan_slug": "pack_basic", "gateway": "idpay"})
    assert res.status_code == 200
    order_id = res.json()["order_id"]
    cb = c.get("/api/payment/idpay/callback",
               params={"id": "IDPAY-XYZ", "order_id": str(order_id)}, follow_redirects=False)
    assert cb.status_code == 303 and "result=success" in cb.headers["location"]
    assert _balance(c) == tokens.SIGNUP_TOKENS + 500


def test_my_orders_lists_the_caller_orders_only():
    c, _ = _register("orders@example.com")
    admin = _admin()
    admin.post("/api/admin/settings", json={"key": "usdt_wallet", "value": "TXw"})
    c.post("/api/payment/start", json={"plan_slug": "pack_basic", "gateway": "crypto"})

    other, _ = _register("other@example.com")
    assert other.get("/api/my-orders").json() == []

    orders = c.get("/api/my-orders").json()
    assert len(orders) == 1 and orders[0]["gateway"] == "crypto" and orders[0]["status"] == "pending"


# ---------------------------------------------------------------------------
# Entitlement payload plumbing
# ---------------------------------------------------------------------------
def test_entitlement_exposes_costs_for_the_ui():
    c, _ = _register()
    ent = c.get("/api/me").json()["entitlement"]
    assert ent["model_costs"]["logistic"] == tokens.MODEL_TOKEN_COSTS["logistic"]
    assert ent["tool_costs"]["symbolic"] == tokens.TOOL_COSTS["symbolic"]
    assert ent["included_points"] == tokens.POINTS_INCLUDED

    models = c.get("/models").json()
    assert set(MODEL_NAMES) <= set(models["token_costs"])


def test_check_access_uses_plans_module_for_admins():
    admin = _admin()
    ent = plans.get_entitlement(admin.get("/api/me").json()["user"], None)
    plans.check_access(ent, 10_000, "Expensive model")  # must not raise


# ---------------------------------------------------------------------------
# Migration from the old time-based database
# ---------------------------------------------------------------------------
_LEGACY_SCHEMA = """
CREATE TABLE users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT UNIQUE NOT NULL,
    name          TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'user',
    banned        INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL
);
CREATE TABLE sessions (
    token      TEXT PRIMARY KEY,
    user_id    INTEGER REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    last_seen  TEXT NOT NULL
);
CREATE TABLE plans (
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
CREATE TABLE subscriptions (
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
CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def _seed_legacy_database() -> None:
    """Recreate the pre-token (v0.3.0) schema with one active subscriber."""
    conn = db.connect()
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        for table in ("token_ledger", "usage", "payment_orders", "subscriptions",
                      "sessions", "users", "plans", "settings"):
            conn.execute(f"DROP TABLE IF EXISTS {table}")
        conn.executescript(_LEGACY_SCHEMA)
        conn.execute(
            "INSERT INTO users (email, name, password_hash, role, banned, created_at) "
            "VALUES ('legacy@example.com', 'Legacy', 'x', 'user', 0, ?)", (db.utcnow(),))
        conn.execute(
            "INSERT INTO subscriptions (user_id, plan_slug, starts_at, ends_at, status, created_at) "
            "VALUES (1, 'pro_monthly', ?, '2999-01-01T00:00:00+00:00', 'active', ?)",
            (db.utcnow(), db.utcnow()))
        conn.commit()
    finally:
        conn.close()


def test_legacy_database_migrates_and_credits_time_based_subscribers():
    _seed_legacy_database()
    db.init_db()

    legacy = db.query_one("SELECT * FROM users WHERE email = 'legacy@example.com'")
    assert legacy["token_balance"] == 500
    assert legacy["username"] is None  # column added, old accounts keep working by email
    ledger = db.query("SELECT reason FROM token_ledger WHERE owner_id = '1'")
    assert [row["reason"] for row in ledger] == ["legacy-migration:1"]

    # the retired time-based plan is gone while the token packs are seeded
    remaining = {row["slug"] for row in db.query("SELECT slug FROM plans")}
    assert "pro_monthly" not in remaining and "pack_pro" in remaining

    # the fixed admin exists on the migrated database and logs in without a phone
    client = TestClient(app)
    assert client.post("/api/auth/login", json=ADMIN_LOGIN).status_code == 200

    # re-running init on the migrated database must not credit anyone twice
    db.init_db()
    again = db.query_one("SELECT token_balance FROM users WHERE email = 'legacy@example.com'")
    assert again["token_balance"] == 500


# ---------------------------------------------------------------------------
# Privacy & access hardening
# ---------------------------------------------------------------------------
def test_login_throttle_stops_password_guessing():
    c = _client()
    for _ in range(auth.LOGIN_MAX_FAILURES):
        res = c.post("/api/auth/login", json={"identifier": "admin", "password": "wrong"})
        assert res.status_code == 401
    # while the window is open even the correct password is refused
    assert c.post("/api/auth/login", json=ADMIN_LOGIN).status_code == 429
    auth.reset_login_throttle()
    assert c.post("/api/auth/login", json=ADMIN_LOGIN).status_code == 200


def test_every_admin_route_is_invisible_to_regular_users():
    c, _ = _register()
    for path in ("/api/admin/stats", "/api/admin/users", "/api/admin/orders",
                 "/api/admin/tokens/ledger", "/api/admin/settings"):
        assert c.get(path).status_code == 403, path
    assert c.post("/api/admin/users/1/tokens", json={"delta": 5}).status_code == 403
    assert c.post("/api/admin/settings",
                  json={"key": "usdt_wallet", "value": "x"}).status_code == 403


def test_accounts_only_ever_see_their_own_data():
    a, ra = _register("a@example.com", username="alice")
    b, rb = _register("b@example.com", username="bob")
    assert ra.status_code == 200 and rb.status_code == 200
    a.post("/solve", json=_solve_body())

    a_reasons = [e["reason"] for e in a.get("/api/my-tokens").json()["entries"]]
    b_reasons = [e["reason"] for e in b.get("/api/my-tokens").json()["entries"]]
    assert "solve:logistic" in a_reasons
    assert b_reasons == ["signup"]
    assert b.get("/api/my-orders").json() == []


def test_no_wildcard_cors_for_third_party_sites():
    c, _ = _register()
    res = c.get("/api/me", headers={"Origin": "https://evil.example"})
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") is None


def test_session_cookie_flags():
    c = _client()
    cookie = c.post("/api/auth/login", json=ADMIN_LOGIN).headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert "secure" not in cookie  # plain-http test client stays usable

    https = TestClient(app, base_url="https://testserver")
    secure_cookie = https.post("/api/auth/login", json=ADMIN_LOGIN).headers["set-cookie"].lower()
    assert "secure" in secure_cookie
