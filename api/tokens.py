"""Token economy: difficulty-based costs, balances, and the ledger.

Subscriptions are **token-based** — nothing expires with time. A payment
credits tokens to the buyer's wallet, and every tool call debits tokens
according to how heavy the computation is:

- each of the 42 model families has its own difficulty price,
- symbolic solves / classification cost a flat tool price,
- large output resolutions add a small surcharge on top of the base cost.

Balances live on `users.token_balance` (accounts) and `sessions.tokens`
(anonymous trial visitors, so the solver can be tried before signing up).
Every movement is appended to `token_ledger` for auditing and the user-facing
"token history".
"""
from __future__ import annotations

import json
from typing import Any

from api import db

# ---------------------------------------------------------------------------
# Difficulty pricing (tokens per operation)
# ---------------------------------------------------------------------------
MODEL_TOKEN_COSTS: dict[str, int] = {
    # 1 — direct quadratures / elementary first-order families
    "separable": 1,
    "exact": 1,
    "linear_first_order": 1,
    "bernoulli": 1,
    "autonomous": 1,
    "logistic": 1,
    "homogeneous_first_order": 1,
    "integrating_factor": 1,
    # 2 — structural nonlinear ODEs, constant coefficients, special functions
    "riccati": 2,
    "constant_coefficient_second_order": 2,
    "constant_coefficient_higher_order": 2,
    "euler_cauchy": 2,
    "undetermined_coefficients": 2,
    "variation_of_parameters": 2,
    "legendre": 2,
    "bessel": 2,
    "airy": 2,
    "hermite": 2,
    "laguerre": 2,
    "chebyshev": 2,
    # 3 — transforms, series expansions, pendulum
    "laplace_transform": 3,
    "fourier_series": 3,
    "power_series": 3,
    "frobenius": 3,
    "pendulum": 3,
    # 4 — nonlinear / coupled ODE systems
    "system_linear": 4,
    "system_nonlinear": 4,
    "van_der_pol": 4,
    "lotka_volterra": 4,
    # 5 — stiff systems and chaotic / advective problems
    "system_stiff": 5,
    "chemical_kinetics": 5,
    "lorenz": 5,
    "advection": 5,
    # 6 — parabolic / hyperbolic PDEs and BVPs
    "heat_equation": 6,
    "wave_equation": 6,
    "boundary_value": 6,
    # 7 — eigenvalues and delay equations
    "eigenvalue": 7,
    "delay_approximation": 7,
    # 8 — elliptic PDEs / reaction-diffusion
    "laplace_pde": 8,
    "poisson_pde": 8,
    "reaction_diffusion": 8,
    # 9 — inverse (optimization) problems
    "inverse_problem": 9,
}

DEFAULT_MODEL_COST = 2

# Flat prices for non-model tools.
TOOL_COSTS: dict[str, int] = {
    "symbolic": 4,
    "analyze": 1,
    "analyze_enhanced": 2,
}

SIGNUP_TOKENS = 50      # credited to every new account
ANON_TOKENS = 40        # trial balance for anonymous sessions (10 symbolic solves)

POINTS_INCLUDED = 500   # every solve includes this many output points
POINTS_PER_EXTRA_TOKEN = 1_000  # +1 token per extra 1000 points


# ---------------------------------------------------------------------------
# Costs
# ---------------------------------------------------------------------------
def model_costs() -> dict[str, int]:
    """Base costs merged with the admin override stored in site settings."""
    costs = dict(MODEL_TOKEN_COSTS)
    raw = db.get_setting("model_token_costs", "{}") or "{}"
    try:
        override = json.loads(raw)
    except ValueError:
        return costs
    if isinstance(override, dict):
        for name, value in override.items():
            if (
                isinstance(name, str)
                and isinstance(value, int)
                and not isinstance(value, bool)
                and value >= 0
            ):
                costs[name] = value
    return costs


def skill_cost(skill_id: str, default: int) -> int:
    """Price of a named skill, overridable from the admin panel.

    Skills share the ``model_token_costs`` override table with the model
    families, so an operator can reprice either with the same setting.
    """
    override = model_costs().get(skill_id)
    return int(default) if override is None else int(override)


def points_surcharge(points: int) -> int:
    """Extra tokens for output resolutions above the included budget."""
    return max(0, int(points) - POINTS_INCLUDED) // POINTS_PER_EXTRA_TOKEN


def cost_for(model: str, points: int = 200) -> int:
    """Total token cost of one solve of `model` with `points` output samples."""
    base = model_costs().get(model, DEFAULT_MODEL_COST)
    return int(base) + points_surcharge(points)


# ---------------------------------------------------------------------------
# Wallets
# ---------------------------------------------------------------------------
def balance(owner: str, owner_id: str) -> int:
    if owner == "user":
        row = db.query_one("SELECT token_balance FROM users WHERE id = ?", (int(owner_id),))
        return int(row["token_balance"]) if row else 0
    if owner == "session":
        row = db.query_one("SELECT tokens FROM sessions WHERE token = ?", (owner_id,))
        return int(row["tokens"]) if row else 0
    return 0


def spent(owner: str, owner_id: str) -> int:
    row = db.query_one(
        "SELECT COALESCE(SUM(-delta), 0) AS c FROM token_ledger "
        "WHERE owner = ? AND owner_id = ? AND delta < 0",
        (owner, owner_id),
    )
    return int(row["c"]) if row else 0


def _known(owner: str) -> bool:
    return owner in ("user", "session")


def _set_balance(owner: str, owner_id: str, value: int) -> None:
    value = max(int(value), 0)
    if owner == "user":
        db.execute("UPDATE users SET token_balance = ? WHERE id = ?", (value, int(owner_id)))
    elif owner == "session":
        db.execute("UPDATE sessions SET tokens = ? WHERE token = ?", (value, owner_id))


def _entry(owner: str, owner_id: str, delta: int, reason: str, balance_after: int) -> None:
    db.execute(
        "INSERT INTO token_ledger (owner, owner_id, delta, reason, balance_after, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (owner, owner_id, int(delta), reason[:120], int(balance_after), db.utcnow()),
    )


def grant(owner: str, owner_id: str, amount: int, reason: str) -> int:
    """Credit tokens and record the ledger entry. Returns the new balance."""
    amount = int(amount)
    if amount <= 0 or not _known(owner):
        return balance(owner, owner_id)
    new_balance = balance(owner, owner_id) + amount
    _set_balance(owner, owner_id, new_balance)
    _entry(owner, owner_id, amount, reason, new_balance)
    return new_balance


def charge(owner: str, owner_id: str, amount: int, reason: str) -> int:
    """Debit tokens (never below zero) and record the ledger entry."""
    amount = max(0, int(amount))
    if amount == 0 or not _known(owner):
        return balance(owner, owner_id)
    current = balance(owner, owner_id)
    new_balance = max(0, current - amount)
    _set_balance(owner, owner_id, new_balance)
    _entry(owner, owner_id, -amount, reason, new_balance)
    return new_balance


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------
def history(owner: str, owner_id: str, limit: int = 50) -> list[dict[str, Any]]:
    return db.query(
        "SELECT id, delta, reason, balance_after, created_at FROM token_ledger "
        "WHERE owner = ? AND owner_id = ? ORDER BY id DESC LIMIT ?",
        (owner, owner_id, int(limit)),
    )


def recent(limit: int = 100) -> list[dict[str, Any]]:
    """Every recent movement across accounts (admin ledger view)."""
    return db.query(
        "SELECT l.id, l.owner, l.owner_id, l.delta, l.reason, l.balance_after, l.created_at, "
        "u.email, u.username FROM token_ledger l "
        "LEFT JOIN users u ON l.owner = 'user' AND CAST(u.id AS TEXT) = l.owner_id "
        "ORDER BY l.id DESC LIMIT ?",
        (int(limit),),
    )
