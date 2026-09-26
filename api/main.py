"""DiffEQ Engine — solver API + token packs, payments, and admin.

Run with:  uvicorn api.main:app --host 0.0.0.0 --port 8000   (or: npm run api)
Open http://localhost:8000/ for the bilingual interactive solver.

Accounts: email/username + password only (no phone number anywhere). The
fixed administrator is seeded by `db.init_db()` and logs in with username
`admin` (password `13811372` unless ADMIN_PASSWORD is set). Solving costs
tokens from the caller's balance according to the difficulty of the model.
"""
from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from api import admin, auth, db, payments, plans, tokens
from api.ai_provider import AIProviderError, analyze_equation
from api.local_intelligence import classify_equation
from api.solver_core import MODEL_NAMES, STIFF_MODELS, SolverRequest, adapter_metadata, solve_builtin, try_symbolic_first_order

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

db.init_db()

app = FastAPI(title="Differential Equation Intelligence API", version="0.4.1")

# The UI is served by this same app, so no cross-origin access is granted on
# purpose: a wildcard CORS policy would let any site script the API.
app.include_router(admin.router)


def _sanitize(value: Any) -> Any:
    """Make arbitrary solver output strict-JSON-safe (browsers reject Infinity/NaN)."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: _sanitize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(v) for v in value]
    return value


class SolveBody(BaseModel):
    model: str = Field(default="system_nonlinear")
    variables: list[str] = Field(min_length=1, max_length=64)
    t_span: tuple[float, float]
    initial_values: list[float]
    parameters: dict[str, float] = Field(default_factory=dict)
    method: Literal["RK45", "BDF", "Radau", "LSODA"] = "RK45"
    rtol: float = Field(default=1e-7, ge=1e-12, le=1e-2)
    atol: float = Field(default=1e-9, ge=1e-14, le=1e-2)
    points: int = Field(default=200, ge=2, le=20_000)


class SymbolicBody(BaseModel):
    equation: str = Field(min_length=1, max_length=2_000)
    variable: str = "y"
    independent: str = "t"


class AnalyzeBody(BaseModel):
    text: str = Field(min_length=1, max_length=10_000)
    language: Literal["en", "fa"] = "en"


class RegisterBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=256)
    username: str | None = Field(default=None, max_length=32)


class LoginBody(BaseModel):
    password: str = Field(min_length=1, max_length=256)
    identifier: str | None = None   # email or username
    email: str | None = None        # legacy field name
    username: str | None = None


class PaymentStartBody(BaseModel):
    plan_slug: str
    gateway: Literal["zarinpal", "idpay", "crypto"]


class CryptoTxBody(BaseModel):
    order_id: int
    txid: str = Field(min_length=4, max_length=200)


_USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{2,31}$")


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------
def _page(name: str) -> FileResponse:
    return FileResponse(WEB_DIR / name)


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return _page("index.html")


@app.get("/auth", include_in_schema=False)
def auth_page() -> FileResponse:
    return _page("auth.html")


@app.get("/pricing", include_in_schema=False)
def pricing_page() -> FileResponse:
    return _page("pricing.html")


@app.get("/account", include_in_schema=False)
def account_page() -> FileResponse:
    return _page("account.html")


@app.get("/admin", include_in_schema=False)
def admin_page() -> FileResponse:
    return _page("admin.html")


# ---------------------------------------------------------------------------
# Health / models
# ---------------------------------------------------------------------------
@app.get("/health")
def health() -> dict[str, object]:
    return {"status": "ok", "solver": "sympy-scipy", "models": len(MODEL_NAMES)}


@app.get("/models")
def models() -> dict[str, object]:
    return {
        "count": len(MODEL_NAMES),
        "models": MODEL_NAMES,
        "adapters": adapter_metadata(),
        "token_costs": tokens.model_costs(),
        "tool_costs": tokens.TOOL_COSTS,
    }


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
def _set_session_cookie(response: Response, token: str, request: Request | None = None) -> None:
    secure = bool(request is not None and request.url.scheme == "https")
    response.set_cookie(
        auth.SESSION_COOKIE, token, max_age=auth.SESSION_DAYS * 86400,
        httponly=True, samesite="lax", path="/", secure=secure,
    )


def _login_identifier(body: LoginBody) -> str:
    for value in (body.identifier, body.email, body.username):
        if value and value.strip():
            return value.strip().lower()
    raise HTTPException(422, "Email or username is required")


@app.post("/api/auth/register")
def register(body: RegisterBody, request: Request, response: Response) -> dict[str, Any]:
    email = body.email.strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(422, "Invalid email address")
    if db.query_one("SELECT id FROM users WHERE email = ?", (email,)):
        raise HTTPException(409, "An account with this email already exists")
    username = None
    if body.username and body.username.strip():
        username = body.username.strip().lower()
        if not _USERNAME_RE.match(username):
            raise HTTPException(
                422, "Username must be 3-32 characters: a-z, 0-9, dot, dash, underscore")
        if db.query_one("SELECT id FROM users WHERE username = ?", (username,)):
            raise HTTPException(409, "This username is already taken")
    user_id = db.execute(
        "INSERT INTO users (username, email, name, password_hash, role, created_at) "
        "VALUES (?, ?, ?, ?, 'user', ?)",
        (username, email, body.name.strip(), auth.hash_password(body.password), db.utcnow()),
    )
    tokens.grant("user", str(user_id), tokens.SIGNUP_TOKENS, "signup")
    token = auth.create_session(user_id)
    _set_session_cookie(response, token, request)
    user = db.query_one(
        "SELECT id, username, email, name, role, banned FROM users WHERE id = ?", (user_id,))
    return {"user": user, "entitlement": plans.get_entitlement(user, None)}


@app.post("/api/auth/login")
def login(body: LoginBody, request: Request, response: Response) -> dict[str, Any]:
    identifier = _login_identifier(body)
    throttle_key = auth.login_key(identifier, request.client.host if request.client else None)
    wait = auth.login_blocked(throttle_key)
    if wait:
        raise HTTPException(
            429, f"Too many failed sign-in attempts — retry in {wait} seconds")
    row = db.query_one(
        "SELECT * FROM users WHERE email = ? OR username = ?", (identifier, identifier))
    if row is None or not auth.verify_password(body.password, row["password_hash"]):
        auth.note_login_failure(throttle_key)
        raise HTTPException(401, "Invalid email/username or password")
    if row["banned"]:
        raise HTTPException(403, "Account is disabled")
    auth.clear_login_failures(throttle_key)
    token = auth.create_session(row["id"])
    _set_session_cookie(response, token, request)
    user = {k: row[k] for k in ("id", "username", "email", "name", "role", "banned")}
    return {"user": user, "entitlement": plans.get_entitlement(user, None)}


@app.post("/api/auth/logout")
def logout(request: Request, response: Response) -> dict[str, str]:
    token = request.cookies.get(auth.SESSION_COOKIE)
    if token:
        auth.delete_session(token)
    response.delete_cookie(auth.SESSION_COOKIE, path="/")
    return {"ok": "true"}


@app.get("/api/me")
def me(request: Request) -> dict[str, Any]:
    user, session = auth.current(request)
    return {
        "user": auth.public_user(user),
        "entitlement": plans.get_entitlement(user, session),
    }


@app.get("/api/my-tokens")
def my_tokens(request: Request) -> dict[str, Any]:
    """Current balance plus the caller's recent token movements."""
    user = auth.require_user(request)
    entitlement = plans.get_entitlement(user, None)
    return {
        "tokens": entitlement["tokens"],
        "unlimited": entitlement["unlimited"],
        "tokens_spent": entitlement["tokens_spent"],
        "entries": tokens.history("user", str(user["id"]), 50),
    }


# ---------------------------------------------------------------------------
# Plans / orders
# ---------------------------------------------------------------------------
@app.get("/api/plans")
def api_plans() -> dict[str, Any]:
    return {
        "plans": plans.list_plans(),
        "signup_tokens": tokens.SIGNUP_TOKENS,
        "anonymous_tokens": tokens.ANON_TOKENS,
    }


@app.get("/api/my-orders")
def my_orders(request: Request) -> list[dict[str, Any]]:
    user = auth.require_user(request)
    return db.query(
        "SELECT id, plan_slug, gateway, amount, currency, status, txid, created_at "
        "FROM payment_orders WHERE user_id = ? ORDER BY id DESC LIMIT 50",
        (user["id"],),
    )


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------
@app.post("/api/payment/start")
def payment_start(body: PaymentStartBody, request: Request) -> dict[str, Any]:
    user = auth.require_user(request)
    if plans.get_plan(body.plan_slug) is None:
        raise HTTPException(422, "Unknown plan")
    order = payments.create_order(user["id"], body.plan_slug, body.gateway)
    base = str(request.base_url).rstrip("/")
    try:
        if body.gateway == "zarinpal":
            _, url = payments.zarinpal_request(order, f"{base}/api/payment/zarinpal/callback")
            return {"gateway": "zarinpal", "redirect_url": url, "order_id": order["id"]}
        if body.gateway == "idpay":
            _, url = payments.idpay_request(order, f"{base}/api/payment/idpay/callback")
            return {"gateway": "idpay", "redirect_url": url, "order_id": order["id"]}
        return payments.crypto_start(order)
    except payments.PaymentError as exc:
        raise HTTPException(503, str(exc)) from exc


@app.get("/api/payment/zarinpal/callback")
def zarinpal_callback(request: Request) -> RedirectResponse:
    q = request.query_params
    authority = q.get("Authority") or q.get("authority")
    status = q.get("Status") or q.get("status")
    result = "failed"
    if authority and status == "OK":
        order = db.query_one(
            "SELECT * FROM payment_orders WHERE gateway = 'zarinpal' "
            "AND authority = ? AND status = 'pending' ORDER BY id DESC LIMIT 1",
            (authority,),
        )
        if order is not None:
            try:
                ok, info = payments.zarinpal_verify(order, authority)
                if ok:
                    payments.confirm_order(order["id"], ref=str(info.get("ref_id", "")))
                    result = "success"
            except payments.PaymentError:
                pass
    return RedirectResponse(f"/account?result={result}", status_code=303)


@app.get("/api/payment/idpay/callback")
def idpay_callback(id: str, order_id: str, request: Request) -> RedirectResponse:
    result = "failed"
    order = db.query_one(
        "SELECT * FROM payment_orders WHERE gateway = 'idpay' AND id = ? AND status = 'pending'",
        (order_id,),
    )
    if order is not None:
        try:
            ok, info = payments.idpay_verify(order, id)
            if ok:
                payments.confirm_order(order["id"], ref=str(info.get("track_id", "")))
                result = "success"
        except payments.PaymentError:
            pass
    return RedirectResponse(f"/account?result={result}", status_code=303)


@app.post("/api/payment/crypto/tx")
def crypto_tx(body: CryptoTxBody, request: Request) -> dict[str, Any]:
    user = auth.require_user(request)
    try:
        order = payments.crypto_submit_tx(body.order_id, body.txid.strip(), user["id"])
    except payments.PaymentError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"ok": True, "order_id": order["id"], "status": order["status"],
            "message": "Transaction submitted — an admin will verify it."}


# ---------------------------------------------------------------------------
# Solver (gated by the token balance)
# ---------------------------------------------------------------------------
def _resolve_entitlement(request: Request, response: Response) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any] | None]:
    user, session = auth.current(request)
    if user is None and session is None:
        token = auth.create_session(None, tokens.ANON_TOKENS)
        _set_session_cookie(response, token)
        session = {"token": token, "user_id": None}
    entitlement = plans.get_entitlement(user, session)
    return entitlement, user, session


def _owner_keys(user: dict[str, Any] | None,
                session: dict[str, Any] | None) -> tuple[str, str]:
    return plans.owner_keys(user, session)


def _limit_response(exc: plans.LimitError) -> HTTPException:
    return HTTPException(402, detail={
        "code": exc.code, "message": exc.message, "upgrade": True,
        "upgrade_url": "/pricing",
    })


def _token_summary(entitlement: dict[str, Any], charged: int,
                   remaining: int | None) -> dict[str, Any]:
    return {
        "tier": entitlement["tier"],
        "unlimited": bool(entitlement.get("unlimited")),
        "tokens": remaining,
        "tokens_charged": charged,
        "solves_used": entitlement["solves_used"] + 1,
    }


@app.post("/solve")
def solve(body: SolveBody, request: Request, response: Response) -> dict[str, object]:
    if body.model not in MODEL_NAMES:
        raise HTTPException(400, "Unknown model adapter")
    entitlement, user, session = _resolve_entitlement(request, response)
    cost = tokens.cost_for(body.model, body.points)
    try:
        plans.check_access(entitlement, cost, f"Model '{body.model}'")
    except plans.LimitError as exc:
        raise _limit_response(exc) from exc

    if body.model in STIFF_MODELS and body.method == "RK45":
        method = "BDF"
    else:
        method = body.method
    solver_request = SolverRequest(
        body.model, tuple(body.variables), body.t_span, tuple(body.initial_values),
        body.parameters, method, body.rtol, body.atol, body.points,
    )
    try:
        result = solve_builtin(solver_request)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    owner, owner_id = _owner_keys(user, session)
    plans.record_usage(owner, owner_id, body.points)
    remaining = entitlement["tokens"]
    if not entitlement.get("unlimited"):
        remaining = tokens.charge(owner, owner_id, cost, f"solve:{body.model}")

    payload = _sanitize(result.__dict__)
    payload["entitlement"] = _token_summary(entitlement, cost, remaining)
    return payload


@app.post("/analyze")
def analyze(body: AnalyzeBody, request: Request, response: Response) -> dict[str, object]:
    entitlement, user, session = _resolve_entitlement(request, response)
    cost = tokens.TOOL_COSTS["analyze"]
    try:
        plans.check_access(entitlement, cost, "Equation classification")
    except plans.LimitError as exc:
        raise _limit_response(exc) from exc
    local = classify_equation(body.text)
    local["language"] = body.language
    owner, owner_id = _owner_keys(user, session)
    plans.record_usage(owner, owner_id, 0)
    remaining = entitlement["tokens"]
    if not entitlement.get("unlimited"):
        remaining = tokens.charge(owner, owner_id, cost, "analyze")
    return {
        "status": "classified", "data": local, "executable": False, "provider": "local",
        "entitlement": _token_summary(entitlement, cost, remaining),
    }


@app.post("/analyze/enhanced")
def enhanced_analyze(body: AnalyzeBody, request: Request,
                     response: Response) -> dict[str, object]:
    """Optional remote enhancement; core behavior remains local if unavailable."""
    entitlement, user, session = _resolve_entitlement(request, response)
    cost = tokens.TOOL_COSTS["analyze_enhanced"]
    try:
        plans.check_access(entitlement, cost, "Enhanced analysis")
    except plans.LimitError as exc:
        raise _limit_response(exc) from exc
    try:
        result = analyze_equation(body.text, body.language)
        provider = "external-enhancement"
    except (AIProviderError, ValueError):
        result = classify_equation(body.text)
        result["language"] = body.language
        provider = "local-fallback"
    if result.get("model") not in MODEL_NAMES:
        raise HTTPException(422, "AI selected an unsupported model")
    owner, owner_id = _owner_keys(user, session)
    plans.record_usage(owner, owner_id, 0)
    remaining = entitlement["tokens"]
    if not entitlement.get("unlimited"):
        remaining = tokens.charge(owner, owner_id, cost, "analyze_enhanced")
    return {
        "status": "classified", "data": result, "executable": False, "provider": provider,
        "entitlement": _token_summary(entitlement, cost, remaining),
    }


@app.post("/solve/symbolic")
def symbolic(body: SymbolicBody, request: Request, response: Response) -> dict[str, object]:
    # Symbolic solves consume tokens like any other tool — no free bypass.
    entitlement, user, session = _resolve_entitlement(request, response)
    cost = tokens.TOOL_COSTS["symbolic"]
    try:
        plans.check_access(entitlement, cost, "Symbolic solve")
    except plans.LimitError as exc:
        raise _limit_response(exc) from exc
    result = try_symbolic_first_order(body.equation, body.variable, body.independent)
    if result is None:
        raise HTTPException(422, "No verified symbolic solution was found")
    owner, owner_id = _owner_keys(user, session)
    plans.record_usage(owner, owner_id, 0)
    remaining = entitlement["tokens"]
    if not entitlement.get("unlimited"):
        remaining = tokens.charge(owner, owner_id, cost, "symbolic")
    payload = {"status": "success", "solution": result, "verified": False,
               "message": "Symbolic result requires numerical verification for the supplied conditions."}
    payload["entitlement"] = _token_summary(entitlement, cost, remaining)
    return payload


# Static assets for the interactive UI (must be registered after API routes).
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
