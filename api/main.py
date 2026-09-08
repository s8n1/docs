"""DiffEQ Engine — solver API + subscriptions, payments, and admin.

Run with:  uvicorn api.main:app --host 0.0.0.0 --port 8000   (or: npm run api)
Open http://localhost:8000/ for the bilingual interactive solver.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from api import admin, auth, db, payments, plans
from api.ai_provider import AIProviderError, analyze_equation
from api.local_intelligence import classify_equation
from api.solver_core import MODEL_NAMES, STIFF_MODELS, SolverRequest, adapter_metadata, solve_builtin, try_symbolic_first_order

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

db.init_db()

app = FastAPI(title="Differential Equation Intelligence API", version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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


class LoginBody(BaseModel):
    email: str
    password: str


class PaymentStartBody(BaseModel):
    plan_slug: str
    gateway: Literal["zarinpal", "idpay", "crypto"]


class CryptoTxBody(BaseModel):
    order_id: int
    txid: str = Field(min_length=4, max_length=200)


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
    return {"count": len(MODEL_NAMES), "models": MODEL_NAMES, "adapters": adapter_metadata()}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        auth.SESSION_COOKIE, token, max_age=auth.SESSION_DAYS * 86400,
        httponly=True, samesite="lax", path="/",
    )


@app.post("/api/auth/register")
def register(body: RegisterBody, response: Response) -> dict[str, Any]:
    email = body.email.strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(422, "Invalid email address")
    if db.query_one("SELECT id FROM users WHERE email = ?", (email,)):
        raise HTTPException(409, "An account with this email already exists")
    count = db.query_one("SELECT COUNT(*) AS c FROM users")["c"]
    role = "admin" if count == 0 else "user"
    user_id = db.execute(
        "INSERT INTO users (email, name, password_hash, role, created_at) VALUES (?, ?, ?, ?, ?)",
        (email, body.name.strip(), auth.hash_password(body.password), role, db.utcnow()),
    )
    token = auth.create_session(user_id)
    _set_session_cookie(response, token)
    user = db.query_one("SELECT id, email, name, role, banned FROM users WHERE id = ?", (user_id,))
    return {"user": user, "entitlement": plans.get_entitlement(user, None)}


@app.post("/api/auth/login")
def login(body: LoginBody, response: Response) -> dict[str, Any]:
    email = body.email.strip().lower()
    row = db.query_one("SELECT * FROM users WHERE email = ?", (email,))
    if row is None or not auth.verify_password(body.password, row["password_hash"]):
        raise HTTPException(401, "Invalid email or password")
    if row["banned"]:
        raise HTTPException(403, "Account is disabled")
    token = auth.create_session(row["id"])
    _set_session_cookie(response, token)
    user = {k: row[k] for k in ("id", "email", "name", "role", "banned")}
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


# ---------------------------------------------------------------------------
# Plans / orders
# ---------------------------------------------------------------------------
@app.get("/api/plans")
def api_plans() -> dict[str, Any]:
    return {"plans": plans.list_plans()}


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
    auth.require_user(request)
    order = payments.crypto_submit_tx(body.order_id, body.txid.strip())
    return {"ok": True, "order_id": order["id"], "status": order["status"],
            "message": "Transaction submitted — an admin will verify it."}


# ---------------------------------------------------------------------------
# Solver (gated by entitlement)
# ---------------------------------------------------------------------------
def _resolve_entitlement(request: Request, response: Response) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any] | None]:
    user, session = auth.current(request)
    if user is None and session is None:
        token = auth.create_session(None)
        _set_session_cookie(response, token)
        session = {"token": token, "user_id": None}
    entitlement = plans.get_entitlement(user, session)
    return entitlement, user, session


def _limit_response(exc: plans.LimitError) -> HTTPException:
    return HTTPException(402, detail={
        "code": exc.code, "message": exc.message, "upgrade": True,
        "upgrade_url": "/pricing",
    })


@app.post("/solve")
def solve(body: SolveBody, request: Request, response: Response) -> dict[str, object]:
    entitlement, user, session = _resolve_entitlement(request, response)
    try:
        plans.check_access(entitlement, body.model, body.points)
    except plans.LimitError as exc:
        raise _limit_response(exc) from exc

    if body.model not in MODEL_NAMES:
        raise HTTPException(400, "Unknown model adapter")
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

    owner = "user" if user else ("session" if session else "anon")
    owner_id = str(user["id"]) if user else (session["token"] if session else "anon")
    plans.record_usage(owner, owner_id, body.points)

    payload = _sanitize(result.__dict__)
    payload["entitlement"] = {
        "tier": entitlement["tier"],
        "solves_used": entitlement["solves_used"] + 1,
        "solves_per_day": entitlement["solves_per_day"],
    }
    return payload


@app.post("/analyze")
def analyze(body: AnalyzeBody) -> dict[str, object]:
    local = classify_equation(body.text)
    local["language"] = body.language
    return {"status": "classified", "data": local, "executable": False, "provider": "local"}


@app.post("/analyze/enhanced")
def enhanced_analyze(body: AnalyzeBody) -> dict[str, object]:
    """Optional remote enhancement; core behavior remains local if unavailable."""
    try:
        result = analyze_equation(body.text, body.language)
    except (AIProviderError, ValueError):
        result = classify_equation(body.text)
        result["language"] = body.language
        return {"status": "classified", "data": result, "executable": False, "provider": "local-fallback"}
    if result.get("model") not in MODEL_NAMES:
        raise HTTPException(422, "AI selected an unsupported model")
    return {"status": "classified", "data": result, "executable": False, "provider": "external-enhancement"}


@app.post("/solve/symbolic")
def symbolic(body: SymbolicBody) -> dict[str, object]:
    result = try_symbolic_first_order(body.equation, body.variable, body.independent)
    if result is None:
        raise HTTPException(422, "No verified symbolic solution was found")
    return {"status": "success", "solution": result, "verified": False,
            "message": "Symbolic result requires numerical verification for the supplied conditions."}


# Static assets for the interactive UI (must be registered after API routes).
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")