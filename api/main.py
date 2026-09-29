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
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from api import admin, auth, db, payments, plans, skills, tokens
from api.ai_provider import AIProviderError, analyze_equation
from api.equation_input import DEFAULT_SPAN, EquationError, solve_equation
from api.local_intelligence import classify_equation
from api.solver_core import MODEL_NAMES, STIFF_MODELS, SolverRequest, adapter_metadata, solve_builtin

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

db.init_db()

app = FastAPI(title="Differential Equation Intelligence API", version="0.5.0")


@app.exception_handler(RequestValidationError)
def _invalid_request(_request: Request, exc: RequestValidationError) -> JSONResponse:
    """Say which field is wrong, without echoing the request back.

    FastAPI's default handler returns pydantic's raw list *and* the submitted
    body — which sent passwords straight back to the browser and gave the UI
    nothing readable to show the user. Only the field name and the message are
    kept here.
    """
    problems = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error.get("loc", ()) if part != "body")
        problems.append(f"{location or 'request'}: {error.get('msg') or 'is not valid'}")
    return JSONResponse(status_code=422, content={"detail": "; ".join(problems) or "Invalid request."})

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


class EquationBody(BaseModel):
    """Free-form ODE: any notation, with optional initial conditions."""
    equation: str = Field(min_length=1, max_length=2_000)
    variable: str = Field(default="y", max_length=16)
    independent: str = Field(default="t", max_length=16)
    t_span: tuple[float, float] = DEFAULT_SPAN
    initial_values: list[float] = Field(default_factory=list, max_length=4)
    points: int = Field(default=200, ge=2, le=2_000)


class PasswordBody(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=8, max_length=256)


class AnalyzeBody(BaseModel):
    text: str = Field(min_length=1, max_length=10_000)
    language: Literal["en", "fa"] = "en"


class SkillMatchBody(BaseModel):
    text: str = Field(min_length=1, max_length=10_000)
    limit: int = Field(default=3, ge=1, le=8)


class SkillRunBody(BaseModel):
    """One skill call. Which fields matter depends on the skill."""
    equation: str | None = Field(default=None, max_length=2_000)
    system: list[str] | None = Field(default=None, max_length=8)
    parameters: dict[str, float] | None = None
    parameter: str | None = Field(default=None, max_length=16)
    parameter_range: tuple[float, float] | None = None
    initial_values: list[float] | None = Field(default=None, max_length=8)
    t_span: tuple[float, float] | None = None
    points: int = Field(default=200, ge=2, le=20_000)
    terms: int | None = Field(default=None, ge=3, le=12)
    steps: int | None = Field(default=None, ge=2, le=400)
    language: Literal["en", "fa"] = "fa"


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


@app.post("/api/account/password")
def change_password(body: PasswordBody, request: Request) -> dict[str, Any]:
    """Rotate the signed-in account's password (used to replace the seeded
    default admin password with one only the owner knows)."""
    user = auth.require_user(request)
    row = db.query_one("SELECT password_hash FROM users WHERE id = ?", (user["id"],))
    if row is None or not auth.verify_password(body.current_password, row["password_hash"]):
        raise HTTPException(401, "The current password is not correct")
    if body.new_password == body.current_password:
        raise HTTPException(422, "The new password must be different from the current one")
    db.execute("UPDATE users SET password_hash = ? WHERE id = ?",
               (auth.hash_password(body.new_password), user["id"]))
    return {"ok": True, "message": "Password updated"}


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
        raise HTTPException(400, f"Unknown model '{body.model}'. Choose one of the 42 model "
                                 "families — GET /models lists them all.")
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
    local.update(_suggest_skill(body.text))
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
        raise HTTPException(422, f"The classifier chose '{result.get('model')}', which is not one "
                                 "of the 42 supported model families. Rephrase the request, or "
                                 "pick a model from GET /models.")
    # Only a skill id the catalog knows may come back from the provider.
    spec = skills.get_skill(str(result.get("skill") or ""))
    result["skill"] = spec.id if spec else None
    result["skill_name"] = {"en": spec.name_en, "fa": spec.name_fa} if spec else None
    owner, owner_id = _owner_keys(user, session)
    plans.record_usage(owner, owner_id, 0)
    remaining = entitlement["tokens"]
    if not entitlement.get("unlimited"):
        remaining = tokens.charge(owner, owner_id, cost, "analyze_enhanced")
    return {
        "status": "classified", "data": result, "executable": False, "provider": provider,
        "entitlement": _token_summary(entitlement, cost, remaining),
    }


# ---------------------------------------------------------------------------
# Skills: named capabilities the engine and its AI layer share
# ---------------------------------------------------------------------------
@app.get("/skills")
def list_skills() -> dict[str, object]:
    """The skills catalog: free to read, so an agent can plan before spending."""
    return {"status": "ok", "count": len(skills.SKILLS), "skills": skills.skill_catalog()}


@app.post("/skills/match")
def match_skills(body: SkillMatchBody, request: Request, response: Response) -> dict[str, object]:
    """Rank skills against a plain-language request (offline, deterministic)."""
    entitlement, user, session = _resolve_entitlement(request, response)
    cost = tokens.TOOL_COSTS["analyze"]
    try:
        plans.check_access(entitlement, cost, "Skill match")
    except plans.LimitError as exc:
        raise _limit_response(exc) from exc
    try:
        matches = skills.match_skills(body.text, body.limit)
    except EquationError as exc:
        raise HTTPException(422, str(exc)) from exc
    remaining = _record_tool(entitlement, user, session, cost, "skills:match")
    return {
        "status": "matched",
        "matches": matches,
        "entitlement": _token_summary(entitlement, cost, remaining),
    }


@app.post("/skills/{skill_id}")
def run_skill_endpoint(skill_id: str, body: SkillRunBody, request: Request,
                       response: Response) -> dict[str, object]:
    """Run one named skill. A skill that cannot answer costs nothing."""
    spec = skills.get_skill(skill_id)
    if spec is None:
        raise HTTPException(404, f"Unknown skill '{skill_id}'")
    entitlement, user, session = _resolve_entitlement(request, response)
    cost = tokens.skill_cost(spec.id, spec.cost)
    try:
        plans.check_access(entitlement, cost, f"Skill: {spec.name_en}")
    except plans.LimitError as exc:
        raise _limit_response(exc) from exc
    arguments = body.model_dump()
    arguments.pop("language", None)
    result = skills.run_skill(spec.id, arguments)
    payload = _sanitize(result)
    payload["skill"] = spec.id
    payload["skill_name"] = {"en": spec.name_en, "fa": spec.name_fa}
    if payload["status"] != "success":
        payload["entitlement"] = _token_summary(entitlement, 0, entitlement["tokens"])
        return payload
    remaining = _record_tool(entitlement, user, session, cost, f"skills:{spec.id}")
    payload["entitlement"] = _token_summary(entitlement, cost, remaining)
    payload["verified"] = payload.get("residual_max") is not None and payload.get("kind") != "series"
    return payload


def _suggest_skill(text: str) -> dict[str, Any]:
    """Best-matching skill for a request, or nulls when nothing matches."""
    try:
        matches = skills.match_skills(text, 1)
    except EquationError:
        return {"skill": None, "skill_name": None}
    if not matches:
        return {"skill": None, "skill_name": None}
    return {"skill": matches[0]["id"], "skill_name": matches[0]["name"]}


def _equation_payload(body: EquationBody) -> dict[str, Any]:
    """Run the free-form intake: exact form first, numerical curve as fallback.

    The result goes through `_sanitize` because a failed residual estimate is an
    infinity, which is not valid JSON.
    """
    try:
        result = solve_equation(
            body.equation,
            variable=body.variable or "y",
            independent=body.independent or "t",
            t_span=(float(body.t_span[0]), float(body.t_span[1])),
            initial=list(body.initial_values),
            points=body.points,
        )
    except EquationError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _sanitize(result)


def _record_tool(entitlement: dict[str, Any], user: dict[str, Any] | None,
                 session: dict[str, Any] | None, cost: int, reason: str) -> int | None:
    owner, owner_id = _owner_keys(user, session)
    plans.record_usage(owner, owner_id, 0)
    if entitlement.get("unlimited"):
        return entitlement["tokens"]
    return tokens.charge(owner, owner_id, cost, reason)


@app.post("/solve/symbolic")
def symbolic(body: SymbolicBody, request: Request, response: Response) -> dict[str, object]:
    # Symbolic solves consume tokens like any other tool — no free bypass.
    entitlement, user, session = _resolve_entitlement(request, response)
    cost = tokens.TOOL_COSTS["symbolic"]
    try:
        plans.check_access(entitlement, cost, "Symbolic solve")
    except plans.LimitError as exc:
        raise _limit_response(exc) from exc
    try:
        result = solve_equation(
            body.equation, variable=body.variable or "y",
            independent=body.independent or "t", points=64, symbolic_only=True,
        )
    except EquationError as exc:
        raise HTTPException(422, str(exc)) from exc
    if result.get("status") != "success" or not result.get("solution"):
        # Always say why an exact answer was not reached, and where to go next.
        reason = str(result.get("message") or "").strip() or "No closed form was reached."
        why = str(result.get("hint") or "").strip()
        raise HTTPException(422, " ".join(part for part in (
            reason, why,
            "The same equation can still be solved numerically through /solve/equation.",
        ) if part))
    remaining = _record_tool(entitlement, user, session, cost, "symbolic")
    return {
        "status": "success",
        "solution": result["solution"],
        "verified": False,
        "kind": result["kind"],
        "order": result["order"],
        "message": result["message"],
        "entitlement": _token_summary(entitlement, cost, remaining),
    }


@app.post("/solve/equation")
def solve_free_equation(body: EquationBody, request: Request,
                        response: Response) -> dict[str, object]:
    """The main free-form endpoint: accepts any notation, always answers.

    ``-2*y + sin(t)``, ``y' = -2*y``, ``dy/dt = -2*y``, ``y' + 2*y = 0``,
    ``y'' + 2*y' + y = 0`` and inline conditions (``y' = -2y, y(0) = 1``) all work.
    """
    entitlement, user, session = _resolve_entitlement(request, response)
    cost = tokens.TOOL_COSTS["symbolic"]
    try:
        plans.check_access(entitlement, cost, "Equation solve")
    except plans.LimitError as exc:
        raise _limit_response(exc) from exc
    payload = _equation_payload(body)
    if payload["status"] != "success":
        # Nothing was solved, so nothing is charged.
        payload["entitlement"] = _token_summary(entitlement, 0, entitlement["tokens"])
        return payload
    remaining = _record_tool(entitlement, user, session, cost, "solve:equation")
    payload["entitlement"] = _token_summary(entitlement, cost, remaining)
    payload["model_guess"] = classify_equation(body.equation)["model"]
    payload["skill_guess"] = _suggest_skill(body.equation)["skill"]
    # Exact answers are checked by construction; a numerical curve reports its
    # own residual; a Taylor series is an approximation and says so.
    payload["verified"] = payload["residual_max"] is not None and payload["kind"] != "series"
    return payload


# Static assets for the interactive UI (must be registered after API routes).
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
