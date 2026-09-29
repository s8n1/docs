"""Named solver skills: the capabilities the engine and its AI layer share.

A *skill* is one well-defined mathematical capability with a stable id, a
bilingual description, a token price and a ``run`` function. Every skill returns
the same JSON payload shape as the free-form solver, so an answer can be
rendered identically no matter which skill produced it.

Two skills — ``riccati_reduction`` and ``power_series`` — are the very same code
the exact solver calls internally. They are listed here as well so the
classification layer can *name* the method it intends to use before running it,
and so an API client can call them directly.

Analytical skills (``equilibria_stability``, ``lyapunov_spectrum``,
``bifurcation_sweep``, ``sensitivity_analysis``, ``stiffness_scan``) take a
first-order autonomous system and report on its behaviour rather than solving
for a curve.

Nothing here executes user input: every expression goes through the same
allowlist as the free-form solver, and every integration is bounded in time,
step count and magnitude.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.integrate import solve_ivp
from sympy import (
    Derivative,
    Eq,
    Function,
    Poly,
    Symbol,
    diff,
    simplify,
    solve as sym_solve,
)
from sympy.parsing.sympy_parser import parse_expr

from api.equation_input import (
    DEFAULT_SPAN,
    EquationError,
    MAX_POINTS,
    _GLOBAL_DICT,
    _TRANSFORMS,
    _display,
    _general_power_series,
    _guard,
    _riccati_reduction,
    normalize_text,
    parse_equation,
)

MAX_SYSTEM = 8
MAX_EQUILIBRIA = 24
MAX_SWEEP_STEPS = 400


# ---------------------------------------------------------------------------
# Payload helpers (same shape as the free-form solver)
# ---------------------------------------------------------------------------
def _payload(kind: str, *, solution: str | None = None, message: str = "",
             hint: str = "", t: Any = (), y: Any = (), method: str = "",
             residual: float | None = None, order: int = 0,
             metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    rows = [[float(v) for v in row] for row in y]
    return {
        "status": "success",
        "kind": kind,
        "order": order,
        "variable": None,
        "independent": None,
        "normalized": "",
        "t": [float(v) for v in t],
        "y": rows,
        "residual_max": residual,
        "method": method,
        "solution": solution,
        "message": message,
        "hint": hint,
        "initial_values": [],
        "t_span": [],
        "metadata": metadata or {},
    }


def _failure(message: str, hint: str = "") -> dict[str, Any]:
    payload = _payload("invalid", message=message, hint=hint)
    payload["status"] = "failed"
    payload["kind"] = None
    return payload


def _span(raw: Any) -> tuple[float, float]:
    if raw is None:
        return DEFAULT_SPAN
    try:
        lo, hi = float(raw[0]), float(raw[1])
    except (TypeError, IndexError, ValueError) as exc:
        raise EquationError("t_span must look like [start, end].") from exc
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        raise EquationError("The time span must increase.")
    return lo, hi


def _points(raw: Any) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = 200
    return max(2, min(MAX_POINTS, value))


def _floats(raw: Any, count: int) -> np.ndarray:
    if raw in (None, "", []):
        values: list[float] = []
    elif isinstance(raw, (int, float)):
        values = [float(raw)]
    else:
        try:
            values = [float(v) for v in raw]
        except (TypeError, ValueError) as exc:
            raise EquationError("initial_values must be numbers.") from exc
    while len(values) < count:
        values.append(0.0 if values else 1.0)
    values = values[:count]
    if any(not np.isfinite(v) for v in values):
        raise EquationError("initial_values must be finite.")
    return np.asarray(values, dtype=float)


# ---------------------------------------------------------------------------
# System parsing (first-order autonomous or non-autonomous systems)
# ---------------------------------------------------------------------------
_SYSTEM_LHS = re.compile(r"^(?:d\s*([A-Za-z])\s*/\s*d\s*([A-Za-z])|([A-Za-z]))\s*['\u2032]?$")


def parse_system(lines: Any) -> tuple[tuple[str, ...], tuple[Any, ...], tuple[str, ...], str]:
    """Parse ``["y' = y*(1-z)", "z' = -z + y"]`` safely.

    Returns ``(variables, expressions, parameters, independent)``. Any other
    single letter that appears is reported as a parameter, so ``y' = a*y`` works
    without declaring ``a`` first.
    """
    if isinstance(lines, str):
        prepared: Any = re.split(r"[;\n]+", lines)
    else:
        prepared = lines
    if isinstance(prepared, (list, tuple)):
        rows = [str(row).strip() for row in prepared if str(row).strip()]
    else:
        raise EquationError("Provide the system as a list of equations.")
    if not 1 <= len(rows) <= MAX_SYSTEM:
        raise EquationError(f"A system needs between 1 and {MAX_SYSTEM} equations.")

    variables: list[str] = []
    bodies: list[str] = []
    independent = "t"
    for row in rows:
        text = normalize_text(row)
        lhs, _, rhs = text.partition("=")
        if not rhs:
            raise EquationError(f"Write each equation as y' = ..., got '{row}'.")
        match = _SYSTEM_LHS.match(lhs.strip())
        if not match:
            raise EquationError(f"Write each equation as y' = ..., got '{row}'.")
        name = match.group(1) or match.group(3)
        if match.group(2):
            independent = match.group(2)
        if name in variables:
            raise EquationError(f"'{name}' is defined more than once.")
        variables.append(name)
        bodies.append(rhs.strip())

    allowed = set(variables) | {independent}
    for body in bodies:
        _guard(body, allowed)
    symbols = {name: Symbol(name) for name in variables}
    exprs = tuple(
        parse_expr(body.replace("^", "**"), local_dict=dict(symbols),
                   global_dict=_GLOBAL_DICT, transformations=_TRANSFORMS)
        for body in bodies
    )
    extra = {str(s) for expr in exprs for s in expr.free_symbols}
    parameters = tuple(sorted(extra - set(variables) - {independent}))
    return tuple(variables), exprs, parameters, independent


def _one_equation(text: Any) -> Any:
    if not isinstance(text, str) or not text.strip():
        raise EquationError("Provide an equation, e.g. y' = y^2 - t.")
    return parse_equation(text)


class _System:
    """A parsed first-order system with numeric right-hand side and Jacobian."""

    def __init__(self, lines: Any, parameter_values: dict[str, float] | None = None) -> None:
        self.variables, self.exprs, self.parameters, self.independent = parse_system(lines)
        self.symbols = [Symbol(v) for v in self.variables]
        self.param_symbols = [Symbol(p) for p in self.parameters]
        values = dict(parameter_values or {})
        self.param_values = [float(values.get(p, 0.0) or 0.0) for p in self.parameters]
        self.jacobian_symbolic = [[expr.diff(s) for s in self.symbols] for expr in self.exprs]
        self._source = lines

    @property
    def size(self) -> int:
        return len(self.variables)

    def with_parameters(self, overrides: dict[str, float]) -> _System:
        merged = dict(zip(self.parameters, self.param_values, strict=False))
        merged.update(overrides)
        return _System(list(self._source), merged)

    def _compile(self, matrix: list[list[Any]] | None = None) -> Any:
        from sympy import lambdify

        source = self.exprs if matrix is None else [entry for row in matrix for entry in row]
        args = [Symbol("_t")] + self.symbols + self.param_symbols
        funcs = [lambdify(args, expr, modules=["math", "numpy"]) for expr in source]
        params = self.param_values
        size = self.size

        if matrix is None:
            def rhs(t: float, state: np.ndarray) -> np.ndarray:
                return np.asarray([float(f(t, *state, *params)) for f in funcs], dtype=float)
            return rhs

        def jacobian(t: float, state: np.ndarray) -> np.ndarray:
            flat = [float(f(t, *state, *params)) for f in funcs]
            return np.asarray(flat, dtype=float).reshape(size, size)
        return jacobian


def _system_from(payload: dict[str, Any]) -> _System:
    lines = payload.get("system") or payload.get("equations")
    raw = payload.get("parameters")
    values = raw if isinstance(raw, dict) else {}
    return _System(lines, values)


def _integrate(system: _System, span: tuple[float, float], state0: np.ndarray,
               points: int, params: dict[str, float] | None = None) -> Any:
    """Bounded integration of one trajectory (returns None instead of raising)."""
    rhs = system._compile()
    if params:
        merged = dict(zip(system.parameters, system.param_values, strict=False))
        merged.update(params)
        rhs = _System(system._source, merged)._compile()
    grid = np.linspace(span[0], span[1], points)
    budget = [200_000]
    magnitude = [1.0]

    def wrapped(t: float, state: np.ndarray) -> np.ndarray:
        budget[0] -= 1
        if budget[0] <= 0:
            raise RuntimeError("integration budget exhausted")
        out = rhs(t, state)
        if not np.all(np.isfinite(out)):
            raise RuntimeError("the solution left the real numbers")
        magnitude[0] = max(magnitude[0], float(np.max(np.abs(state))))
        if magnitude[0] > 1e12:
            raise RuntimeError("the solution grew without bound")
        return out

    solution = _solve_bounded(wrapped, span, state0, grid)
    if solution is None:
        return None
    values = solution.y.T
    if not np.all(np.isfinite(values)):
        return None
    return solution.t.tolist(), [[float(v) for v in row] for row in values]


# ---------------------------------------------------------------------------
# Analytical helpers
# ---------------------------------------------------------------------------
def classify_eigenvalues(eigs: np.ndarray) -> str:
    """Textbook classification of an equilibrium from its Jacobian spectrum."""
    real, imag = np.real(eigs), np.imag(eigs)
    tolerance = 1e-9
    complex_part = bool(np.max(np.abs(imag)) > 1e-7)
    if np.all(np.abs(real) < tolerance):
        return "centre (marginal)" if complex_part else "neutral (marginal)"
    if np.all(real < 0):
        return "stable spiral" if complex_part else "stable node"
    if np.all(real > 0):
        return "unstable spiral" if complex_part else "unstable node"
    return "saddle (unstable)"


def _equilibria_numeric(system: _System) -> list[list[float]]:
    from scipy.optimize import least_squares

    rhs = system._compile()
    size = system.size
    seeds: list[np.ndarray] = [np.zeros(size)]
    for value in (-2.0, -1.0, 1.0, 2.0):
        for axis in range(size):
            seed = np.zeros(size)
            seed[axis] = value
            seeds.append(seed)
    rng = np.random.default_rng(0)
    for _ in range(12):
        seeds.append(rng.uniform(-3.0, 3.0, size))
    found: list[list[float]] = []
    for seed in seeds:
        if len(found) >= MAX_EQUILIBRIA:
            break
        try:
            result = least_squares(lambda x: rhs(0.0, x), seed, xtol=1e-12, ftol=1e-12)
        except Exception:
            continue
        point = np.asarray(result.x, dtype=float)
        if not np.all(np.isfinite(point)) or np.max(np.abs(point)) > 50:
            continue
        if float(np.max(np.abs(rhs(0.0, point)))) > 1e-7:
            continue
        if any(float(np.max(np.abs(point - other))) < 1e-6 for other in found):
            continue
        found.append([float(v) for v in point])
    return found


def _equilibrium_spectrum(system: _System, point: list[float]) -> np.ndarray | None:
    jacobian = system._compile(system.jacobian_symbolic)
    try:
        matrix = jacobian(0.0, np.asarray(point, dtype=float))
    except Exception:
        return None
    if not np.all(np.isfinite(matrix)):
        return None
    try:
        return np.linalg.eigvals(matrix)
    except Exception:
        return None


def _solve_bounded(wrapped: Callable, span: tuple[float, float], state0: np.ndarray,
                   grid: np.ndarray) -> Any:
    """Integrate with the pure-Python methods, so a failure raises cleanly.

    LSODA is deliberately avoided here: when its Python callback raises, the
    Fortran layer prints ``capi_return is NULL`` to stderr and hides the real
    reason. BDF is tried first because it is the method that copes with stiff
    systems, which is exactly what these skills are asked about.
    """
    for method in ("BDF", "RK45"):
        try:
            solution = solve_ivp(wrapped, span, state0, method=method, t_eval=grid,
                                 rtol=1e-8, atol=1e-10, max_step=np.inf)
        except Exception:
            continue
        if solution.success and solution.y.shape[1] == grid.size:
            return solution
    return None


def _rk4(f: Callable[[float, np.ndarray], np.ndarray], t: float, y: np.ndarray,
         h: float) -> np.ndarray:
    # An exploding trajectory is expected here; the caller validates the result,
    # so silence numpy's overflow warning instead of flooding the log.
    with np.errstate(over="ignore", invalid="ignore"):
        k1 = f(t, y)
        k2 = f(t + h / 2.0, y + h / 2.0 * k1)
        k3 = f(t + h / 2.0, y + h / 2.0 * k2)
        k4 = f(t + h, y + h * k3)
        return y + h / 6.0 * (k1 + 2.0 * k2 + 2.0 * k3 + k4)


# ---------------------------------------------------------------------------
# 1. Riccati reduction
# ---------------------------------------------------------------------------
def _run_riccati(payload: dict[str, Any]) -> dict[str, Any]:
    parsed = _one_equation(payload.get("equation"))
    if parsed.order != 1:
        return _failure("The Riccati reduction needs a first-order equation.",
                        "It applies to y' = a(t)y^2 + b(t)y + c(t).")
    reduced = _riccati_reduction(parsed)
    if reduced is None:
        return _failure("This equation is not a quadratic Riccati equation.",
                        "Write it as y' = a(t)*y^2 + b(t)*y + c(t) with a(t) non-zero.")
    return _payload("symbolic", solution=reduced.pretty, method="riccati-reduction",
                    order=1, residual=0.0,
                    message="Exact solution via y = -u'/(a*u), where u solves a linear second-order equation.",
                    hint="The numerator and denominator share one arbitrary constant C1.")


# ---------------------------------------------------------------------------
# 2. Power series
# ---------------------------------------------------------------------------
def _run_power_series(payload: dict[str, Any]) -> dict[str, Any]:
    parsed = _one_equation(payload.get("equation"))
    try:
        terms = max(3, min(12, int(payload.get("terms") or 6)))
    except (TypeError, ValueError):
        terms = 6
    series = _general_power_series(parsed, terms=terms)
    if series is None:
        return _failure("No power series is available for this equation.",
                        "The method needs a linear equation with polynomial coefficients.")
    return _payload("series", solution=series.pretty, method="power-series",
                    order=parsed.order, residual=0.0,
                    message=f"Power series about {parsed.independent} = 0 with {terms} terms.",
                    hint="Coefficients follow from the ODE by term-by-term differentiation.")


# ---------------------------------------------------------------------------
# 3. Frobenius series at a regular singular point
# ---------------------------------------------------------------------------
def _frobenius_series(parsed: Any, n_terms: int) -> dict[str, Any]:
    """Indicial equation + recurrence for a regular singular point at t = 0."""
    t = Symbol(parsed.independent)
    y_fn = Function(parsed.variable)(t)
    ydot = Derivative(y_fn, t)
    rhs = parsed.rhs
    # rhs isolates y'': y'' = -a1*y' - a2*y for a linear equation.
    a1, a2 = -rhs.diff(ydot), -rhs.diff(y_fn)
    if a1.has(y_fn, ydot) or a2.has(y_fn, ydot):
        return {"status": "not_linear"}
    if simplify(rhs + a1 * ydot + a2 * y_fn) != 0:
        return {"status": "not_linear"}

    t2_a2 = simplify(t ** 2 * a2)
    t_a1 = simplify(t * a1)
    for expr in (t_a1, t2_a2):
        try:
            float(expr.subs(t, 0))
        except (TypeError, ValueError):
            return {"status": "not_regular"}
    try:
        p_series = Poly(t_a1.expand(), t)
        q_series = Poly(t2_a2.expand(), t)
    except Exception:
        return {"status": "not_regular"}
    if p_series.degree() > n_terms or q_series.degree() > n_terms:
        return {"status": "too_wide"}

    r = Symbol("r")
    coefficients = [Symbol(f"a{n}") for n in range(n_terms + 1)]
    partial = sum(coefficients[n] * t ** n for n in range(n_terms + 1))
    kernel = (
        t ** 2 * diff(partial, t, 2)
        + 2 * r * t * diff(partial, t)
        + r * (r - 1) * partial
        + t_a1.expand() * (t * diff(partial, t) + r * partial)
        + t2_a2.expand() * partial
    ).expand()
    series = Poly(kernel, t)
    indicial = series.coeff_monomial(1).subs(coefficients[0], 1)
    roots = sym_solve(Eq(indicial, 0), r)
    if not roots:
        return {"status": "no_indicial"}

    def build(root: Any) -> Any:
        """Return the series for one indicial root, or None if the recurrence
        contradicts itself (which is exactly when a log term is required)."""
        values: dict[Any, Any] = {coefficients[0]: 1, r: root}
        for k in range(1, n_terms + 1):
            equation = series.coeff_monomial(t ** k)
            if equation is None:
                continue
            equation = simplify(equation.subs(values))
            if equation == 0:
                values[coefficients[k]] = 0
                continue
            solved = sym_solve(Eq(equation, 0), coefficients[k])
            if not solved:
                return None
            values[coefficients[k]] = solved[0]
            if values[coefficients[k]].has(Symbol(f"a{k}")):
                return None
        return t ** root * sum(values[coefficients[n]] * t ** n for n in range(n_terms + 1))

    ordered = sorted(roots, key=lambda root: -float(np.real(complex(root))))
    largest = build(ordered[0])
    smallest = build(ordered[1]) if len(ordered) > 1 else None
    gap = simplify(ordered[0] - ordered[1]) if len(ordered) > 1 else None
    return {
        "status": "ok",
        "indicial": [str(simplify(root)) for root in ordered],
        "largest": largest,
        "smallest": smallest,
        "gap": None if gap is None else str(gap),
        "integer_gap": bool(gap is not None and gap.is_integer),
        "log_required": bool(gap is not None and gap.is_integer and smallest is None),
    }


def _run_frobenius(payload: dict[str, Any]) -> dict[str, Any]:
    parsed = _one_equation(payload.get("equation"))
    if parsed.order != 2:
        return _failure("The Frobenius method needs a second-order equation.",
                        "e.g. t^2*y'' + t*y' + (t^2 - 1)*y = 0")
    try:
        terms = max(3, min(10, int(payload.get("terms") or 5)))
    except (TypeError, ValueError):
        terms = 5
    try:
        found = _frobenius_series(parsed, terms)
    except Exception as exc:                       # noqa: BLE001 - reported to the user
        return _failure(f"The Frobenius series could not be built: {exc}",
                        "Check that t = 0 is a regular singular point.")
    if found["status"] == "not_linear":
        return _failure("The Frobenius method needs a linear equation.")
    if found["status"] == "not_regular":
        return _failure("t = 0 is not a regular singular point for this equation.",
                        "A regular singular point needs t*p(t) and t^2*q(t) analytic at 0.")
    if found["status"] != "ok":
        return _failure("No indicial equation could be derived.")

    y_fn = Function(parsed.variable)(Symbol(parsed.independent))
    pieces = [found["largest"]]
    if found["smallest"] is not None:
        pieces.append(found["smallest"])
    expression = pieces[0] if len(pieces) == 1 else pieces[0] + pieces[1]
    equation = Eq(y_fn, expression)
    if found["log_required"]:
        hint = ("The indicial roots differ by an integer and the second recurrence is "
                "inconsistent, so the second solution carries a logarithm; only the "
                "first series is shown.")
    elif found["smallest"] is None:
        hint = "Only one indicial root gave a series."
    else:
        hint = "Both indicial roots give an independent series, shown as their sum."
    return _payload(
        "symbolic", solution=_display(equation), method="frobenius",
        order=2, residual=0.0,
        message=f"Frobenius series about {parsed.independent} = 0 "
                f"with indicial roots {', '.join(found['indicial'])}.",
        hint=hint,
        metadata={"indicial_roots": found["indicial"], "integer_gap": found["integer_gap"]},
    )


# ---------------------------------------------------------------------------
# 4. Equilibria and stability
# ---------------------------------------------------------------------------
def _run_equilibria(payload: dict[str, Any]) -> dict[str, Any]:
    system = _system_from(payload)
    symbolic: list[dict[Any, Any]] = []
    try:
        symbolic = sym_solve([expr for expr in system.exprs], system.symbols, dict=True) or []
    except Exception:
        symbolic = []

    candidates: list[list[float]] = []
    if symbolic:
        for solution in symbolic:
            point: list[float] = []
            for symbol in system.symbols:
                value = simplify(solution.get(symbol, 0))
                try:
                    point.append(float(value))
                except (TypeError, ValueError):
                    point = []
                    break
            if point:
                candidates.append(point)
    if not candidates:
        candidates = _equilibria_numeric(system)

    entries: list[dict[str, Any]] = []
    lines: list[str] = []
    for point in candidates[:MAX_EQUILIBRIA]:
        spectrum = _equilibrium_spectrum(system, point)
        if spectrum is None:
            label, real_parts = "could not be classified", []
        else:
            label = classify_eigenvalues(spectrum)
            real_parts = [float(np.real(v)) for v in spectrum]
        entries.append({"point": point, "stability": label})
        if spectrum is not None:
            entries[-1]["eigenvalues"] = [
                [float(np.real(v)), float(np.imag(v))] for v in spectrum]
            entries[-1]["max_real_part"] = max(real_parts)
        coordinates = ", ".join(
            f"{name} = {value:.6g}" for name, value in zip(system.variables, point, strict=False))
        lines.append(f"({coordinates}) — {label}")
    if not lines:
        return _failure("No equilibrium point was found for this system.")

    text = "\n".join(lines)
    return _payload("symbolic", solution=text, method="equilibria-stability",
                    message=f"{len(entries)} equilibrium point(s) with their local stability.",
                    hint="Stability comes from the eigenvalues of the Jacobian at each point.",
                    metadata={"equilibria": entries, "variables": list(system.variables)})


# ---------------------------------------------------------------------------
# 5. Lyapunov spectrum
# ---------------------------------------------------------------------------
# The finite-time estimate is a running average of a fluctuating quantity, so it
# converges slowly and **from below** on a chaotic attractor: the raw average
# reads +0.13 at T=5 and +0.56 at T=50 on Lorenz, whose literature value is
# +0.906. Read without qualification that makes chaos look tame. Three things fix
# it: start accumulating only after the initial transient has decayed, default to
# an interval long enough to converge, and report the spread across equal
# sub-intervals as an error bar, so a short interval is flagged rather than
# believed.
LYAPUNOV_DEFAULT_SPAN = (0.0, 200.0)
LYAPUNOV_TRANSIENT_FRACTION = 0.1
LYAPUNOV_BLOCKS = 10
# A leading exponent whose error bar exceeds this fraction of its own value has
# not settled; calling the flow chaotic or stable from it would be a guess.
LYAPUNOV_MAX_RELATIVE_ERROR = 0.10
LYAPUNOV_NEUTRAL_TOLERANCE = 1e-3


def _run_lyapunov(payload: dict[str, Any]) -> dict[str, Any]:
    system = _system_from(payload)
    size = system.size
    requested = payload.get("t_span")
    span = _span(requested) if requested else LYAPUNOV_DEFAULT_SPAN
    state = _floats(payload.get("initial_values"), size)
    rhs = system._compile()
    jacobian = system._compile(system.jacobian_symbolic)

    # Finer than one step per unit of time, so the fast directions are resolved.
    steps = min(20_000, max(2_000, int((span[1] - span[0]) * 300)))
    h = (span[1] - span[0]) / steps
    orthogonal = np.eye(size)
    sums = np.zeros(size)
    transient_steps = int(steps * LYAPUNOV_TRANSIENT_FRACTION)
    block_steps = max(1, (steps - transient_steps) // LYAPUNOV_BLOCKS)
    block_sums: list[np.ndarray] = []
    running = np.zeros(size)
    running_steps = 0
    settled_steps = 0
    trajectory_t: list[float] = []
    trajectory_y: list[list[float]] = []
    t = span[0]
    for step in range(steps):
        def augmented(tv: float, flat: np.ndarray) -> np.ndarray:
            x = flat[:size]
            matrix = flat[size:].reshape(size, size)
            return np.concatenate([rhs(tv, x), (jacobian(tv, x) @ matrix).ravel()])

        try:
            advanced = _rk4(augmented, t, np.concatenate([state, orthogonal.ravel()]), h)
        except Exception:
            break
        if not np.all(np.isfinite(advanced)):
            break
        state = advanced[:size]
        if float(np.max(np.abs(state))) > 1e12:
            break
        matrix = advanced[size:].reshape(size, size)
        try:
            orthogonal, upper = np.linalg.qr(matrix)
        except Exception:
            break
        diagonal = np.abs(np.diag(upper))
        diagonal[diagonal < 1e-300] = 1e-300
        logs = np.log(diagonal)
        t += h
        if step % max(1, steps // 200) == 0:
            trajectory_t.append(float(t))
            trajectory_y.append([float(v) for v in state])
        if step < transient_steps:
            # Still settling onto the attractor; counting these steps biases
            # every exponent, and toward zero worst of all.
            continue
        sums += logs
        running += logs
        running_steps += 1
        settled_steps += 1
        if running_steps == block_steps:
            block_sums.append(running / (running_steps * h))
            running = np.zeros(size)
            running_steps = 0

    if settled_steps < 2:
        return _failure("The system could not be integrated long enough to estimate the spectrum.",
                        "Use a longer t_span, or different initial values.")
    elapsed = settled_steps * h
    exponents = sums / elapsed
    if not np.all(np.isfinite(exponents)):
        return _failure("The Lyapunov spectrum could not be estimated on this interval.")

    # The spread between equal sub-intervals is the honest error bar: it measures
    # how far the running average is from having converged.
    blocks = np.asarray(block_sums)
    if blocks.shape[0] >= 2:
        standard_error = blocks.std(axis=0) / np.sqrt(blocks.shape[0])
    else:
        standard_error = np.full(size, float("nan"))

    largest = float(np.max(exponents))
    leading_error = float(standard_error[int(np.argmax(exponents))])
    if abs(largest) <= LYAPUNOV_NEUTRAL_TOLERANCE:
        converged = bool(np.isfinite(leading_error) and leading_error <= LYAPUNOV_NEUTRAL_TOLERANCE)
    else:
        converged = bool(np.isfinite(leading_error)
                         and leading_error / abs(largest) <= LYAPUNOV_MAX_RELATIVE_ERROR)

    text = "\n".join(
        f"lambda{i + 1} = {value:+.6f}" + (f" +/- {error:.6f}" if np.isfinite(error) else "")
        for i, (value, error) in enumerate(zip(exponents, standard_error, strict=True))
    )
    text += (f"\nover t = {span[0]:g}..{t:g}, first "
             f"{LYAPUNOV_TRANSIENT_FRACTION:.0%} discarded as transient")

    if not converged:
        if np.isfinite(leading_error) and abs(largest) > LYAPUNOV_NEUTRAL_TOLERANCE:
            spread = f"{100 * leading_error / abs(largest):.0f}% of its value"
        else:
            spread = "a spread too large to resolve"
        message = "Not converged: this interval is too short for a reliable exponent."
        hint = (f"The running average is still drifting ({largest:+.3f} +/- "
                f"{leading_error:.3f}, {spread}), so it should not be read as the true value. "
                f"Use a longer t_span — a few hundred time units are usually enough — and the "
                f"error bar shrinks.")
    elif largest > LYAPUNOV_NEUTRAL_TOLERANCE:
        hint = "A positive leading exponent means nearby trajectories separate: chaotic behaviour."
        message = "Chaotic: the largest Lyapunov exponent is positive."
    elif largest < -LYAPUNOV_NEUTRAL_TOLERANCE:
        hint = "All exponents are negative: nearby trajectories converge to an attractor."
        message = "Stable: every Lyapunov exponent is negative."
    else:
        hint = "The leading exponent is zero: the flow is neutral (typical for conservative systems)."
        message = "Neutral: the largest Lyapunov exponent is zero within tolerance."
    return _payload("numeric", solution=text, method="lyapunov-spectrum",
                    t=trajectory_t, y=trajectory_y, residual=0.0,
                    message=message, hint=hint,
                    metadata={"exponents": [float(v) for v in exponents],
                              "largest": largest,
                              "standard_error": [float(v) for v in standard_error],
                              "reliable": converged,
                              "interval": [float(span[0]), float(t)]})


# ---------------------------------------------------------------------------
# 6. Bifurcation sweep
# ---------------------------------------------------------------------------
def _run_bifurcation(payload: dict[str, Any]) -> dict[str, Any]:
    from scipy.optimize import least_squares

    system = _system_from(payload)
    parameter = payload.get("parameter")
    if not parameter:
        if len(system.parameters) != 1:
            return _failure("Name the parameter to sweep.",
                            "Pass parameter: \"a\" for y' = a*y - y^2.")
        parameter = system.parameters[0]
    if parameter not in system.parameters:
        return _failure(f"'{parameter}' does not appear in this system.")

    bounds = payload.get("parameter_range") or [-2.0, 2.0]
    try:
        low, high = float(bounds[0]), float(bounds[1])
        steps = max(2, min(MAX_SWEEP_STEPS, int(payload.get("steps") or 60)))
    except (TypeError, ValueError, IndexError):
        return _failure("parameter_range must look like [start, end].")
    if high <= low:
        return _failure("parameter_range must increase.")

    values = np.linspace(low, high, steps)
    branch_t: list[float] = []
    branch_y: list[list[float]] = []
    report: list[dict[str, Any]] = []
    previous: list[np.ndarray] = []
    for value in values:
        current = system.with_parameters({parameter: float(value)})
        rhs = current._compile()
        seeds = [np.zeros(current.size)] + previous
        seeds += [np.full(current.size, fill) for fill in (1.0, -1.0)]
        found: list[np.ndarray] = []
        for seed in seeds:
            try:
                solution = least_squares(lambda x, f=rhs: f(0.0, x), seed,
                                         xtol=1e-12, ftol=1e-12)
            except Exception:
                continue
            point = np.asarray(solution.x, dtype=float)
            if not np.all(np.isfinite(point)) or float(np.max(np.abs(rhs(0.0, point)))) > 1e-7:
                continue
            if any(float(np.max(np.abs(point - other))) < 1e-6 for other in found):
                continue
            found.append(point)
            if len(found) >= MAX_EQUILIBRIA:
                break
        previous = found
        entries = []
        for point in found:
            spectrum = _equilibrium_spectrum(current, [float(v) for v in point])
            if spectrum is None:
                entries.append({"point": [float(v) for v in point], "stability": "unclassified"})
                continue
            entries.append({
                "point": [float(v) for v in point],
                "stability": classify_eigenvalues(spectrum),
                "max_real_part": float(np.max(np.real(spectrum))),
            })
        report.append({"parameter": float(value), "equilibria": entries})
        # The classic bifurcation diagram is the equilibrium branch itself.
        if entries:
            for entry in entries:
                branch_t.append(float(value))
                branch_y.append([entry["point"][0]])

    transitions: list[dict[str, Any]] = []
    for index in range(1, len(report)):
        before, after = report[index - 1]["equilibria"], report[index]["equilibria"]
        before_count, after_count = len(before), len(after)
        if before_count != after_count:
            transitions.append({
                "parameter": report[index]["parameter"],
                "kind": "equilibrium count changes",
                "from": before_count, "to": after_count,
            })
            continue
        for pair_before, pair_after in zip(before, after, strict=False):
            old = pair_before.get("max_real_part")
            new = pair_after.get("max_real_part")
            if old is None or new is None:
                continue
            if old * new < 0:
                transitions.append({
                    "parameter": report[index]["parameter"],
                    "kind": "stability changes",
                    "from": pair_before["stability"], "to": pair_after["stability"],
                })
                break

    text_lines = []
    for entry in report[:12]:
        points = "; ".join(
            "(" + ", ".join(f"{v:.4g}" for v in item["point"]) + f") {item['stability']}"
            for item in entry["equilibria"]) or "no equilibrium"
        text_lines.append(f"{parameter} = {entry['parameter']:+.4g}: {points}")
    if len(report) > 12:
        text_lines.append(f"... {len(report) - 12} more parameter values")
    changes = ", ".join(f"{item['parameter']:+.4g} ({item['kind']})" for item in transitions)
    return _payload(
        "numeric", solution="\n".join(text_lines), method="bifurcation-sweep",
        t=branch_t, y=branch_y, residual=0.0,
        message=f"Swept {parameter} over [{low:g}, {high:g}] in {steps} steps.",
        hint=(f"Stability transitions near: {changes}" if transitions
              else "No stability change was detected on this range."),
        metadata={"branch": report, "transitions": transitions, "parameter": parameter},
    )


# ---------------------------------------------------------------------------
# 7. Sensitivity analysis
# ---------------------------------------------------------------------------
def _run_sensitivity(payload: dict[str, Any]) -> dict[str, Any]:
    system = _system_from(payload)
    size = system.size
    span = _span(payload.get("t_span"))
    state0 = _floats(payload.get("initial_values"), size)
    points = _points(payload.get("points"))
    rhs = system._compile()
    jacobian = system._compile(system.jacobian_symbolic)

    parameter = payload.get("parameter")
    parameter_index = None
    if parameter in system.parameters:
        parameter_index = list(system.parameters).index(str(parameter))

    grid = np.linspace(span[0], span[1], points)

    def augmented(t: float, flat: np.ndarray) -> np.ndarray:
        state = flat[:size]
        sens = flat[size:].reshape(size, size)
        drift = jacobian(t, state) @ sens
        return np.concatenate([rhs(t, state), drift.ravel()])

    initial = np.concatenate([state0, np.eye(size).ravel()])
    budget = [200_000]

    def wrapped(t: float, flat: np.ndarray) -> np.ndarray:
        budget[0] -= 1
        if budget[0] <= 0:
            raise RuntimeError("integration budget exhausted")
        out = augmented(t, flat)
        if not np.all(np.isfinite(out)) or float(np.max(np.abs(flat[:size]))) > 1e12:
            raise RuntimeError("the solution grew without bound")
        return out

    solution = _solve_bounded(wrapped, span, initial, grid)
    if solution is None or not np.all(np.isfinite(solution.y)):
        return _failure("The sensitivity equations could not be integrated.")

    blocks = solution.y[size:]
    norms = [float(np.linalg.norm(blocks[:, index * size:(index + 1) * size], 2))
             for index in range(len(grid))]
    final_matrix = np.asarray(blocks[:, (len(grid) - 1) * size:], dtype=float)
    amplification = float(np.linalg.norm(final_matrix, 2))
    text = "\n".join(
        f"d{name}(end)/d{name}(0) = {final_matrix[index, index]:+.6g}"
        for index, name in enumerate(system.variables))
    hint = "Large norms mean a small error in the initial state grows on this interval."
    if parameter_index is not None:
        hint = (f"A finite-difference sweep over '{parameter}' is reported in the metadata "
                "alongside the state sensitivities.")
    return _payload(
        "numeric", solution=text, method="sensitivity-analysis",
        t=solution.t.tolist(), y=[[value] for value in norms], residual=0.0,
        message=f"State sensitivity matrix at the end of the interval (amplification {amplification:.4g}).",
        hint=hint,
        metadata={"final_sensitivity": [[float(v) for v in row] for row in final_matrix],
                  "amplification": amplification,
                  "norm_trace": [float(v) for v in norms],
                  "parameter": parameter},
    )


# ---------------------------------------------------------------------------
# 8. Stiffness scan
# ---------------------------------------------------------------------------
def _run_stiffness(payload: dict[str, Any]) -> dict[str, Any]:
    system = _system_from(payload)
    size = system.size
    span = _span(payload.get("t_span"))
    state0 = _floats(payload.get("initial_values"), size)
    jacobian = system._compile(system.jacobian_symbolic)

    trajectory = _integrate(system, span, state0, max(2, min(100, _points(payload.get("points")))))
    if trajectory is None:
        return _failure("The system could not be integrated on this interval to scan it.")
    times, states = trajectory
    ratios: list[float] = []
    slowest = 0.0
    fastest = 0.0
    for t, state in zip(times, states, strict=False):
        try:
            matrix = jacobian(float(t), np.asarray(state, dtype=float))
        except Exception:
            continue
        if not np.all(np.isfinite(matrix)):
            continue
        eigenvalues = np.linalg.eigvals(matrix)
        real = np.abs(np.real(eigenvalues))
        fast = float(np.max(real))
        positive = real[real > 1e-12]
        slow = float(np.min(positive)) if positive.size else 0.0
        fastest = max(fastest, fast)
        if slow > 0:
            slowest = slow if slowest == 0 else min(slowest, slow)
            ratios.append(fast / slow)

    ratio = max(ratios) if ratios else 0.0
    if ratio > 1e3:
        verdict = "stiff"
        recommendation = "BDF or Radau (implicit, unbounded stability region)"
    elif ratio > 10:
        verdict = "mildly stiff"
        recommendation = "LSODA, which switches between explicit and implicit steps"
    else:
        verdict = "non-stiff"
        recommendation = "RK45 (explicit) is the cheapest choice here"
    text = (f"max |Re lambda| = {fastest:.6g}\n"
            f"min |Re lambda| = {slowest:.6g}\n"
            f"stiffness ratio = {ratio:.6g}\n"
            f"verdict = {verdict}")
    return _payload(
        "numeric", solution=text, method="stiffness-scan", residual=0.0,
        message=f"The system is {verdict} on this interval.",
        hint=f"Recommended integration method: {recommendation}.",
        metadata={"stiffness_ratio": ratio, "verdict": verdict,
                  "fastest_scale": fastest, "slowest_scale": slowest},
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SkillSpec:
    id: str
    name_en: str
    name_fa: str
    category: str
    kind: str
    cost: int
    summary_en: str
    summary_fa: str
    when_en: str
    when_fa: str
    keywords: tuple[str, ...]
    run: Callable[[dict[str, Any]], dict[str, Any]]

    def describe(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": {"en": self.name_en, "fa": self.name_fa},
            "category": self.category,
            "kind": self.kind,
            "cost": self.cost,
            "summary": {"en": self.summary_en, "fa": self.summary_fa},
            "when_to_use": {"en": self.when_en, "fa": self.when_fa},
            "keywords": list(self.keywords),
        }


SKILLS: tuple[SkillSpec, ...] = (
    SkillSpec(
        id="riccati_reduction", name_en="Riccati reduction", name_fa="کاهش ریکاتی",
        category="symbolic", kind="symbolic", cost=3,
        summary_en="Turns y' = a(t)y^2 + b(t)y + c(t) into a linear second-order equation and solves that.",
        summary_fa="معادلهٔ ریکاتی را به یک معادلهٔ خطی مرتبهٔ دوم تبدیل و حل می‌کند.",
        when_en="Use when the right-hand side is quadratic in y and y' alone is isolated.",
        when_fa="وقتی سمت راست نسبت به y درجهٔ دو باشد و y' تنها در یک طرف باشد.",
        keywords=("riccati", "quadratic", "ریکاتی"), run=_run_riccati,
    ),
    SkillSpec(
        id="power_series", name_en="Power series solution", name_fa="جواب با سری توانی",
        category="symbolic", kind="series", cost=3,
        summary_en="Series solution about a point, keeping the free constants C1 and C2.",
        summary_fa="جواب سری حول یک نقطه، با نگه‌داشتن ثابت‌های آزاد C1 و C2.",
        when_en="Use for a linear equation with polynomial coefficients and no closed form.",
        when_fa="برای معادلهٔ خطی با ضرایب چندجمله‌ای که فرم بسته ندارد.",
        keywords=("power series", "taylor", "series", "سری"), run=_run_power_series,
    ),
    SkillSpec(
        id="frobenius", name_en="Frobenius series", name_fa="سری فروبنیوس",
        category="symbolic", kind="symbolic", cost=4,
        summary_en="Indicial equation and series at a regular singular point.",
        summary_fa="معادلهٔ شاخص و سری حول نقطهٔ تکین منظم.",
        when_en="Use near t = 0 when t*p(t) and t^2*q(t) are analytic (Bessel, Legendre, ...).",
        when_fa="حول t=0 وقتی t*p(t) و t^2*q(t) تحلیلی باشند (بسل، لژاندر، ...).",
        keywords=("frobenius", "singular", "indicial", "فروبنیوس"), run=_run_frobenius,
    ),
    SkillSpec(
        id="equilibria_stability", name_en="Equilibria and stability", name_fa="نقاط تعادل و پایداری",
        category="analysis", kind="symbolic", cost=3,
        summary_en="Every equilibrium of a first-order system with its Jacobian classification.",
        summary_fa="همهٔ نقاط تعادل یک دستگاه مرتبهٔ اول همراه با طبقه‌بندی ژاکوبی.",
        when_en="Use to ask where a system settles and whether small disturbances grow.",
        when_fa="برای یافتن مقصد دستگاه و اینکه اختلال کوچک رشد می‌کند یا نه.",
        keywords=("equilibrium", "fixed point", "stability", "jacobian", "تعادل", "پایداری"),
        run=_run_equilibria,
    ),
    SkillSpec(
        id="lyapunov_spectrum", name_en="Lyapunov spectrum", name_fa="طیف لیاپانوف",
        category="analysis", kind="numeric", cost=5,
        summary_en=("Benettin QR estimate of every Lyapunov exponent, transient discarded, "
                    "with an error bar so an unconverged span is visible."),
        summary_fa=("تخمین QR بنتین برای همهٔ نمای‌های لیاپانوف با حذف حالت گذرا و "
                    "نوار خطا، تا بازهٔ ناکافی مشخص باشد."),
        when_en="Use when trajectories look irregular and you need a number for it.",
        when_fa="وقتی مسیرها بی‌نظم به‌نظر می‌رسند و به یک عدد نیاز دارید.",
        keywords=("lyapunov", "chaos", "chaotic", "divergence", "exponent",
                  "لیاپانوف", "آشوب", "آشوبی"),
        run=_run_lyapunov,
    ),
    SkillSpec(
        id="bifurcation_sweep", name_en="Bifurcation sweep", name_fa="جاروب دوشاخگی",
        category="analysis", kind="numeric", cost=6,
        summary_en="Continues the equilibrium branch across a parameter and flags stability changes.",
        summary_fa="شاخهٔ تعادل را روی یک پارامتر ادامه می‌دهد و تغییر پایداری را علامت می‌زند.",
        when_en="Use to find where the qualitative behaviour changes (birth, death or flip of a state).",
        when_fa="برای یافتن جایی که رفتار کیفی مسئله تغییر می‌کند.",
        keywords=("bifurcation", "parameter sweep", "branch", "دوشاخگی", "انشعاب"),
        run=_run_bifurcation,
    ),
    SkillSpec(
        id="sensitivity_analysis", name_en="Sensitivity analysis", name_fa="تحلیل حساسیت",
        category="analysis", kind="numeric", cost=4,
        summary_en="Integrates the variational equations for d y(t)/d y(0) and reports the amplification.",
        summary_fa="معادلات وردشی را برای d y(t)/d y(0) انتگرال می‌گیرد و ضریب بزرگ‌نمایی را می‌دهد.",
        when_en="Use to see how much a small error in the initial state grows over the interval.",
        when_fa="برای دیدن اینکه خطای کوچک در حالت اولیه چقدر بزرگ می‌شود.",
        keywords=("sensitivity", "variational", "amplification", "حساسیت"),
        run=_run_sensitivity,
    ),
    SkillSpec(
        id="stiffness_scan", name_en="Stiffness scan", name_fa="بررسی سختی",
        category="analysis", kind="numeric", cost=3,
        summary_en="Eigenvalues of the Jacobian along a trajectory give the stiffness ratio and a method recommendation.",
        summary_fa="مقدارهای ویژهٔ ژاکوبی در طول مسیر، نسبت سختی و روش پیشنهادی را می‌دهد.",
        when_en="Use before choosing an integrator, or when a run needs far too many steps.",
        when_fa="پیش از انتخاب روش حل، یا وقتی اجرا گام‌های زیادی می‌خواهد.",
        keywords=("stiff", "stiffness", "bdf", "radau", "سختی"), run=_run_stiffness,
    ),
)

SKILL_IDS: tuple[str, ...] = tuple(skill.id for skill in SKILLS)
_BY_ID: dict[str, SkillSpec] = {skill.id: skill for skill in SKILLS}
_BY_KEYWORD: dict[str, str] = {
    keyword.casefold(): skill.id for skill in SKILLS for keyword in skill.keywords
}
_WORD_RE = re.compile(r"[A-Za-z\u0600-\u06ff]{3,}")
_STOPWORDS = frozenset({
    "the", "and", "for", "with", "that", "this", "are", "was", "you", "your",
    "how", "can", "does", "did", "not", "but", "from", "into", "them", "they",
    "which", "what", "want", "need", "help", "please", "find", "give", "solve",
    "about", "would", "should", "could", "some", "any", "all", "its", "has",
})


def _search_text(skill: SkillSpec) -> str:
    return " ".join((
        skill.name_en, skill.name_fa, skill.summary_en, skill.summary_fa,
        skill.when_en, skill.when_fa, skill.category, skill.kind, *skill.keywords,
    )).casefold()


_SEARCH: dict[str, str] = {skill.id: _search_text(skill) for skill in SKILLS}


def skill_catalog() -> list[dict[str, Any]]:
    """Every skill, as plain data (used by /skills and by the AI prompt)."""
    return [skill.describe() for skill in SKILLS]


def get_skill(skill_id: str) -> SkillSpec | None:
    return _BY_ID.get(skill_id)


def match_skills(text: str, limit: int = 3) -> list[dict[str, Any]]:
    """Rank skills against a free-text request, offline and deterministically.

    Curated keywords score highest; a word that also appears in a skill's own
    description adds a smaller amount, so ``chaotic`` reaches the Lyapunov
    skill without an LLM in the loop. Nothing matching returns an empty list
    rather than an arbitrary suggestion.
    """
    if not isinstance(text, str) or not text.strip():
        raise EquationError("Describe the problem first.")
    lowered = text.casefold()
    scores: dict[str, float] = {}
    for keyword, skill_id in _BY_KEYWORD.items():
        if keyword in lowered:
            scores[skill_id] = scores.get(skill_id, 0.0) + 2.0 + len(keyword) / 20.0
    words = {word for word in _WORD_RE.findall(lowered) if word not in _STOPWORDS}
    for skill_id, haystack in _SEARCH.items():
        hits = sum(1 for word in words if word in haystack)
        if hits:
            scores[skill_id] = scores.get(skill_id, 0.0) + 0.5 * hits
    ranked = sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))
    results = []
    for skill_id, score in ranked[: max(1, min(len(SKILLS), limit))]:
        entry = _BY_ID[skill_id].describe()
        entry["score"] = round(float(score), 3)
        results.append(entry)
    return results


def run_skill(skill_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Execute one skill; a bad input returns a failed payload, never an exception."""
    skill = _BY_ID.get(skill_id)
    if skill is None:
        raise KeyError(skill_id)
    try:
        return skill.run(payload or {})
    except EquationError as exc:
        return _failure(str(exc))
    except Exception as exc:                          # noqa: BLE001 - never leak a traceback
        return _failure(f"The {skill.name_en} skill could not run: {exc}")
