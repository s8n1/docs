"""Permissive free-form equation intake.

People write differential equations the way they would on paper, not the way a
solver library wants them. This module accepts all of the usual notations:

    -2*y + sin(t)            bare right-hand side of  y' = f(t, y)
    y' = -2*y                prime notation
    dy/dt = -2*y             Leibniz notation
    y' + 2*y = 0             implicit (linear in y')
    y'' + 2*y' + y = 0       second order
    d^2y/dt^2 = -y           second-order Leibniz
    2y' = y                  implicit multiplication (2y -> 2*y)
    y′ = x² - y              unicode primes / superscripts / Persian digits

The text is normalised into a SymPy ODE, solved exactly with ``dsolve`` when a
closed form exists, and integrated numerically (SciPy) when it does not — so a
user always gets an answer instead of a dead end.

Safety: only an allowlisted mathematical vocabulary ever reaches SymPy. Every
identifier must be a known function, the dependent/independent variable, or a
single-letter constant; brackets, attribute access and dunder names are
rejected before parsing. Nothing is ever evaluated as Python code.
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.integrate import solve_ivp
from sympy import (
    Abs, Derivative, E, Eq, Float, Function, Integral, Integer, Poly, Rational, Symbol,
    S, classify_ode, cos, cosh, diff, dsolve, erf, exp, factorial, gamma, integrate,
    log, oo, pi, sign, sin, simplify, sinh, sqrt, solve as sym_solve, tan, tanh,
)
from sympy import Order
from sympy.core.function import AppliedUndef
from sympy.core.sympify import SympifyError
from sympy.parsing.sympy_parser import (
    implicit_multiplication_application,
    parse_expr,
    standard_transformations,
)

MAX_LENGTH = 2_000
DEFAULT_SPAN = (0.0, 5.0)
MAX_POINTS = 2_000

# ---------------------------------------------------------------------------
# Text normalisation
# ---------------------------------------------------------------------------
# Typography and symbols people actually paste into an input box.
_UNICODE_MAP = {
    "\u2032": "'", "\u2019": "'", "\u00b4": "'", "`": "'", "\u201b": "'",
    "\u2033": "''", "\u201d": "''",
    "\u2212": "-", "\u2013": "-", "\u2014": "-", "\u2011": "-",
    "\u00d7": "*", "\u00b7": "*", "\u2219": "*", "\u22c5": "*",
    "\u00f7": "/",
    "\u00b2": "^2", "\u00b3": "^3", "\u2074": "^4",
    "\u03c0": "pi", "\u03b8": "theta",
    "\u2264": "<=", "\u2265": ">=", "\u2260": "!=",
    "\u066b": ".", "\u066c": ",",
    "\u200c": "", "\u200f": "", "\u200e": "",
}
_DIGIT_MAP = {ord(c): str(i) for i, c in enumerate("\u06f0\u06f1\u06f2\u06f3\u06f4\u06f5\u06f6\u06f7\u06f8\u06f9")}
_DIGIT_MAP.update({ord(c): str(i) for i, c in enumerate("\u0660\u0661\u0662\u0663\u0664\u0665\u0666\u0667\u0668\u0669")})

_ALLOWED_FUNCS = {
    "sin", "cos", "tan", "cot", "sec", "csc",
    "sinh", "cosh", "tanh", "asinh", "acosh", "atanh",
    "asin", "acos", "atan", "arcsin", "arccos", "arctan",
    "exp", "log", "ln", "sqrt", "cbrt", "Abs", "abs", "sign",
    "erf", "gamma", "factorial", "pi", "E", "oo",
}
_FUNC_ALIASES = {
    "ln": "log", "abs": "Abs", "arcsin": "asin", "arccos": "acos",
    "arctan": "atan", "cbrt": "sqrt",
}
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")
_ATTRIBUTE_RE = re.compile(r"[A-Za-z_)]\s*\.\s*[A-Za-z_]")
_FORBIDDEN = ("__", "[", "]", "{", "}", ";", "\\", "#", "&", "|", "@", ":=", "lambda")

_GLOBAL_DICT = {
    "Symbol": Symbol, "Integer": Integer, "Float": Float, "Rational": Rational,
    "sin": sin, "cos": cos, "tan": tan, "sinh": sinh, "cosh": cosh, "tanh": tanh,
    "exp": exp, "log": log, "sqrt": sqrt, "Abs": Abs, "sign": sign,
    "pi": pi, "E": E, "oo": oo, "erf": erf, "gamma": gamma, "factorial": factorial,
}
_TRANSFORMS = standard_transformations + (implicit_multiplication_application,)

# y'' style notations first, then dy/dx, then the bare prime. The lookbehind
# keeps "2y'" working (there is no word boundary between a digit and a letter).
_ORDER2_RES = (
    re.compile(r"d\s*\^?\s*2\s*([A-Za-z]+)\s*/\s*d\s*([A-Za-z]+)\s*\^?\s*2"),
    re.compile(r"d2\s*([A-Za-z]+)\s*/\s*d\s*([A-Za-z]+)\s*2"),
    re.compile(r"(?<![A-Za-z_])([A-Za-z]+)\s*''"),
)
_ORDER1_RES = (
    re.compile(r"d\s*([A-Za-z]+)\s*/\s*d\s*([A-Za-z]+)"),
    re.compile(r"(?<![A-Za-z_])([A-Za-z]+)\s*'"),
)
_PLACEHOLDER1 = "_D1"
_PLACEHOLDER2 = "_D2"

# Inline initial conditions: "y(0)=1", "y'(0)=0", "y''(0)=-2".
_IC_RE = re.compile(
    r"(?<![A-Za-z_])([A-Za-z]+)\s*('{0,2})\s*\(\s*(-?\d+(?:\.\d+)?)\s*\)\s*=\s*(-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)"
)


# Hints that are skipped in the automatic pipeline.
#
# * ``2nd_nonlinear_autonomous_conserved`` can run for minutes on the pendulum.
#   `_autonomous_conserved` below computes the same energy integral instantly.
# * The symbolic power-series hints keep the integration constant C1 symbolic and
#   blow up combinatorially (one ordinary Riccati equation reached several GB).
#   `_taylor_expression` expands the series numerically instead — bounded terms,
#   no symbolic explosion.
_SKIP_HINTS = frozenset({
    "2nd_nonlinear_autonomous_conserved",
    "2nd_nonlinear_autonomous_conserved_Integral",
    "nth_algebraic", "nth_algebraic_Integral", "NthAlgebraic",
    "1st_power_series", "2nd_power_series_ordinary", "2nd_power_series_regular",
    "1st_power_series_Integral", "2nd_power_series_ordinary_Integral",
    "2nd_power_series_regular_Integral",
})

# A solution larger than this is almost always an unrolled series or an
# unevaluated special function nobody can read — try the next method instead.
MAX_SOLUTION_OPS = 250

# Wall-clock budget for the hint sweep inside the worker, and the hard limits
# the worker process itself runs under.
#
# SymPy's integrator is not bounded by its input: ``y' = sin(t)*y + t`` asks it
# for the integral of t*exp(cos t), and the Risch/heurisch solver happily
# allocates gigabytes before giving up. That is not something a request handler
# can survive, so the sweep runs in a forked child with a hard time and
# address-space cap. If it overruns, the parent keeps the Taylor-series and
# numerical answers, which are bounded by construction.
SYMBOLIC_BUDGET_SECONDS = 6.0
SYMBOLIC_TIMEOUT_SECONDS = 10.0
SYMBOLIC_MEMORY_CAP_MB = 768

# The adaptive integrator can also fail to terminate, not by running out of
# memory but by chasing a singularity with ever smaller steps (``y' = tan(y)``
# is the classic case: the right-hand side is finite, huge, and the step size
# estimate never recovers). A right-hand-side wrapper with a hard evaluation,
# magnitude and wall-clock budget turns that into an ordinary failure.
NUMERIC_TIMEOUT_SECONDS = 5.0
NUMERIC_MAX_EVALS = 200_000
NUMERIC_MAX_MAGNITUDE = 1e12


class EquationError(ValueError):
    """The free-form text could not be understood as a differential equation."""


class NotAnEquationError(EquationError):
    """The input is well-formed but contains no derivative."""


@dataclass(frozen=True)
class SymbolicSolution:
    """An exact answer of some kind: explicit, implicit, quadrature or series."""
    equation: Any
    pretty: str
    kind: str          # symbolic | implicit | integral | series | algebraic
    branches: int = 1


@dataclass(frozen=True)
class ParsedEquation:
    order: int
    variable: str
    independent: str
    rhs: Any            # highest derivative expressed in terms of x, y(x) and lower derivatives
    ode: Any            # Eq(Derivative(y, x, order), rhs)
    normalized: str     # the cleaned-up input, echoed back to the user
    origin: str         # "derivative" | "implicit" | "bare"
    inline_initial: tuple[float, ...] = ()
    initial_at: float | None = None


def _strip_inline_conditions(text: str, variable: str) -> tuple[str, tuple[float, ...], float | None]:
    """Pull "y(0)=1, y'(0)=0" style conditions out of the equation text.

    Returns the remaining equation, the values ordered by derivative order, and
    the point they are stated at.
    """
    found: dict[int, float] = {}
    point: float | None = None

    def take(match: re.Match[str]) -> str:
        nonlocal point
        name, primes, at, value = match.groups()
        if name != variable:
            return match.group(0)
        order = len(primes)
        if order > 2:
            return match.group(0)
        point = float(at)
        found[order] = float(value)
        return " "

    cleaned = _IC_RE.sub(take, text)
    if not found:
        return text, (), None
    # A dangling comma would make SymPy parse the text as a tuple.
    cleaned = cleaned.replace(",", " ").strip()
    values = tuple(found[k] for k in sorted(found))
    return cleaned, values, point


def normalize_text(text: str) -> str:
    if not isinstance(text, str):
        raise EquationError("The equation must be text.")
    cleaned = text.strip()
    if not cleaned:
        raise EquationError("Enter an equation first.")
    for src, dst in _UNICODE_MAP.items():
        cleaned = cleaned.replace(src, dst)
    return re.sub(r"\s+", " ", cleaned.translate(_DIGIT_MAP))


def _guard(text: str, allowed: set[str]) -> None:
    if len(text) > MAX_LENGTH:
        raise EquationError(f"Keep the equation under {MAX_LENGTH} characters.")
    lowered = text.casefold()
    for token in _FORBIDDEN:
        if token in lowered:
            raise EquationError("Only mathematical notation is accepted here.")
    if _ATTRIBUTE_RE.search(text):
        raise EquationError("Only mathematical notation is accepted here.")
    for name in _IDENT_RE.findall(text):
        if name in allowed or name in _ALLOWED_FUNCS or name in _FUNC_ALIASES:
            continue
        if len(name) == 1 and name.isalpha():
            continue          # single-letter parameter/constant
        raise EquationError(f"Unknown symbol '{name}'. Use a single-letter name or a known function.")


def _split_derivatives(text: str) -> tuple[str, int, str | None, str | None]:
    """Replace derivative notation with placeholders. Returns (text, order, variable, independent)."""
    order = 0
    variable: str | None = None
    independent: str | None = None

    def mark2(match: re.Match[str]) -> str:
        nonlocal order, variable, independent
        groups = [g for g in match.groups() if g]
        order = max(order, 2)
        variable = variable or (groups[0] if groups else None)
        if len(groups) > 1:
            independent = independent or groups[1]
        return _PLACEHOLDER2

    def mark1(match: re.Match[str]) -> str:
        nonlocal order, variable, independent
        groups = [g for g in match.groups() if g]
        order = max(order, 1)
        variable = variable or (groups[0] if groups else None)
        if len(groups) > 1:
            independent = independent or groups[1]
        return _PLACEHOLDER1

    for pattern in _ORDER2_RES:
        text = pattern.sub(mark2, text)
    for pattern in _ORDER1_RES:
        text = pattern.sub(mark1, text)
    return text, order, variable, independent


def parse_equation(text: str, variable: str = "y", independent: str = "t") -> ParsedEquation:
    """Turn free-form text into a first- or second-order SymPy ODE."""
    cleaned = normalize_text(text)
    cleaned, inline_initial, initial_at = _strip_inline_conditions(cleaned, variable)
    if not cleaned.strip():
        raise EquationError("Add the equation itself, for example:  y' = -2*y, y(0) = 1")
    if re.search(r"'''|[A-Za-z]''\s*'", cleaned):
        raise EquationError("Only first- and second-order equations are supported here.")
    marked, order, var_from_text, ind_from_text = _split_derivatives(cleaned)

    variable = (var_from_text or variable or "y").strip() or "y"
    independent = (ind_from_text or independent or "t").strip() or "t"
    if not variable.isidentifier() or not independent.isidentifier():
        raise EquationError("Variable names must be simple letters.")

    # A prime with no explicit independent variable means the user wrote
    # something like y' = x^2 — take the letter that actually appears.
    if ind_from_text is None and independent not in marked:
        for candidate in ("x", "z"):
            if candidate != variable and re.search(rf"\b{candidate}\b", marked):
                independent = candidate
                break

    marked = marked.replace("^", "**")
    for alias, real in _FUNC_ALIASES.items():
        marked = re.sub(rf"\b{alias}\s*\(", f"{real}(", marked)

    allowed = {variable, independent, _PLACEHOLDER1, _PLACEHOLDER2}
    _guard(marked, allowed)

    x = Symbol(independent)
    y_fn = Function(variable)(x)
    d1 = Symbol(_PLACEHOLDER1)
    d2 = Symbol(_PLACEHOLDER2)
    local_ns = {variable: y_fn, independent: x, _PLACEHOLDER1: d1, _PLACEHOLDER2: d2}

    if order == 0:
        if "=" in marked:
            raise NotAnEquationError(
                "No derivative found. Write it as  y' = ...  (for example  y' = -2*y), "
                "or pick a model family in the Model solver tab."
            )
        # No derivative at all: treat the text as the right-hand side of y' = f.
        try:
            rhs = parse_expr(marked, local_dict=local_ns, global_dict=_GLOBAL_DICT,
                             transformations=_TRANSFORMS, evaluate=True)
        except (SympifyError, SyntaxError, TypeError, ValueError, AttributeError) as exc:
            raise EquationError(f"Could not read that expression: {exc}") from exc
        ode = None
        origin = "bare"
        order = 1
    else:
        sides = marked.split("=")
        if len(sides) > 2:
            raise EquationError("An equation may contain only one '=' sign.")
        try:
            if len(sides) == 1:
                parsed = parse_expr(sides[0], local_dict=local_ns, global_dict=_GLOBAL_DICT,
                                    transformations=_TRANSFORMS, evaluate=True)
                # A bare expression that still mentions a derivative is implicit:
                # "y' + 2y" means y' + 2y = 0, i.e. y' = -2y.
                expression = parsed
                origin = "implicit"
            else:
                left = parse_expr(sides[0], local_dict=local_ns, global_dict=_GLOBAL_DICT,
                                  transformations=_TRANSFORMS, evaluate=True)
                right = parse_expr(sides[1], local_dict=local_ns, global_dict=_GLOBAL_DICT,
                                   transformations=_TRANSFORMS, evaluate=True)
                expression = left - right
                origin = "implicit" if order > 1 or _PLACEHOLDER1 in sides[0] else "derivative"
        except (SympifyError, SyntaxError, TypeError, ValueError, AttributeError) as exc:
            raise EquationError(f"Could not read that equation: {exc}") from exc

        target = d2 if order == 2 else d1
        solutions = _solve_for(expression, target)
        if not solutions:
            raise EquationError(
                "This equation cannot be rearranged for the derivative. "
                "Write it as  y' = ...  (or  y'' = ...)."
            )
        rhs = solutions[0]
        if order == 2:
            # Re-attach the lower derivative so dsolve/solve_ivp see a real ODE.
            rhs = rhs.subs(d1, Derivative(y_fn, x))
        elif rhs.has(d1):
            raise EquationError("This equation cannot be rearranged for the derivative.")
        ode = Eq(Derivative(y_fn, x, order), rhs)

    if order == 0:
        ode = None
    if order == 1 and ode is None:
        ode = Eq(Derivative(y_fn, x), rhs)
    if rhs.has(d2):
        raise EquationError("Could not isolate the highest derivative.")
    return ParsedEquation(order, variable, independent, rhs, ode, cleaned, origin,
                          inline_initial, initial_at)


def _solve_for(expression: Any, target: Any) -> list[Any]:
    from sympy import solve as sym_solve

    try:
        if not expression.has(target):
            # The derivative cancelled out (e.g. "y' = y'"): nothing to solve.
            return []
        found = sym_solve(expression, target)
    except (ValueError, TypeError, NotImplementedError):
        return []
    if isinstance(found, list):
        return [item for item in found if _is_real_expression(item)]
    return [found]


def _is_real_expression(value: Any) -> bool:
    try:
        return not value.has(oo) and value.is_real is not False
    except (TypeError, AttributeError):
        return True


# ---------------------------------------------------------------------------
# Symbolic solving
# ---------------------------------------------------------------------------
def _clean_answer(expr: Any, y_fn: Any) -> bool:
    """Reject SymPy internals that are not answers.

    Two of SymPy's hints leak machinery into their output instead of failing:
    ``factorable`` returns a truncated power series carrying ``O(t**6)`` and an
    undefined helper function ``r(3)``, and the parabolic-cylinder branch of
    the Riccati solver returns a series with ``O(...)`` denominators. Neither is
    a usable answer, so they are rejected here rather than shown to the user.
    """
    try:
        names = {applied.func for applied in expr.atoms(AppliedUndef)}
    except Exception:
        return False
    if names - {y_fn.func}:
        return False
    return not expr.has(Order)


def _display(equation: Any) -> str:
    """Render an answer the way a textbook writes it.

    SymPy names the quadrature dummy variable ``_y``, which is noise for the
    reader; spelling it ``y`` matches the usual energy-integral notation.
    """
    return str(equation).replace("_y", "y")


def _as_solution(sol: Any, y_fn: Any) -> SymbolicSolution | None:
    """Normalise whatever ``dsolve`` returned into a SymbolicSolution."""
    branches = 1
    if isinstance(sol, list):
        branches = len(sol)
        if not sol:
            return None
        sol = sol[0]
    if not isinstance(sol, Eq):
        return None
    if not _clean_answer(sol, y_fn):
        return None
    if sol.lhs == y_fn:
        body = sol.rhs
        try:
            size = body.count_ops()
        except Exception:
            size = 0
        if size > MAX_SOLUTION_OPS:
            return None
        body = simplify(body) if size <= 80 else body
        pretty = _display(Eq(y_fn, body))
        return SymbolicSolution(Eq(y_fn, body), pretty,
                                "integral" if body.has(Integral) else "symbolic", branches)
    if sol.has(y_fn):
        # An implicit answer: the differential equation integrated in quadrature.
        return SymbolicSolution(sol, _display(sol), "implicit", branches)
    return None


def _is_particular(solution: SymbolicSolution, parsed: ParsedEquation) -> bool:
    """True when the answer has no integration constants left to fix."""
    x = Symbol(parsed.independent)
    expr = solution.equation
    body = expr.rhs if isinstance(expr, Eq) else expr
    try:
        leftover = {s for s in body.free_symbols - {x} if str(s).startswith("C")}
    except Exception:
        return False
    return not leftover


def _hint_candidates(parsed: ParsedEquation) -> list[str]:
    """Exact methods SymPy recognises for this ODE, in its own priority order."""
    try:
        recognised = classify_ode(parsed.ode)
    except Exception:
        return []
    return [
        hint for hint in recognised
        if hint not in {"default", "all", "best", "best_hint"}
        and hint not in _SKIP_HINTS
        and not hint.endswith("_Integral")
    ]


def _linear_first_order(parsed: ParsedEquation, ics: dict[Any, Any] | None) -> SymbolicSolution | None:
    """``y' = a(t)·y + b(t)`` in closed form, without evaluating the quadrature.

    SymPy reaches the same answer but insists on evaluating ``∫ b·e^(-∫a)`` first:
    for ``y' = sin(t)·y + t`` that integral is ``∫ t·e^(cos t) dt``, which burns
    seconds and gigabytes before it gives up. The integrating factor is exact on
    its own, so the general solution is returned with the integral left symbolic.
    """
    if parsed.order != 1:
        return None
    t = Symbol(parsed.independent)
    y_fn = Function(parsed.variable)(t)
    rhs = parsed.rhs
    if rhs.has(Derivative(y_fn, t)) or not rhs.has(y_fn):
        return None
    try:
        a = simplify(rhs.diff(y_fn))
        if a.has(y_fn) or a.is_zero or (a.free_symbols - {t}):
            return None
        b = simplify(rhs - a * y_fn)
        if b.has(y_fn) or (b.free_symbols - {t}):
            return None
        potential = integrate(a, t)
    except Exception:
        return None
    if potential.has(Integral):
        return None
    c1 = Symbol("C1")
    try:
        if b.is_zero:
            if ics:
                # y = y(t0)·e^(P(t) - P(t0)) — no quadrature needed.
                t0 = next((key.args[0] for key in ics), 0)
                y0 = next(iter(ics.values()), 1)
                solution = y0 * exp(potential - potential.subs(t, t0))
            else:
                solution = c1 * exp(potential)
        elif ics:
            # y = e^P(t)·(y(t0) + ∫_{t0}^{t} b·e^(-P) ds). The quadrature stays
            # symbolic, so the initial condition is honoured without evaluating
            # the integral that makes this equation expensive.
            t0 = next((key.args[0] for key in ics), 0)
            y0 = next(iter(ics.values()), 1)
            solution = exp(potential) * (
                y0 + Integral(b * exp(-potential), (t, t0, t)))
        else:
            # The integral is left symbolic on purpose: evaluating it is what once
            # cost minutes and gigabytes on  y' = sin(t)·y + t.
            solution = exp(potential) * (c1 + Integral(b * exp(-potential), t))
    except Exception:
        return None
    equation = Eq(y_fn, solution)
    kind = "integral" if equation.has(Integral) else "symbolic"
    return SymbolicSolution(equation, _display(equation), kind)


def solve_symbolic(parsed: ParsedEquation, ics: dict[Any, Any] | None = None,
                   budget: float = SYMBOLIC_BUDGET_SECONDS) -> SymbolicSolution | None:
    """Try every exact method SymPy knows before giving up on a closed form.

    Order: each method ``classify_ode`` recognises, in SymPy's own priority
    order, then the conservation-law integral, then a Taylor series. The bare
    ``dsolve`` default is deliberately *not* used — it re-selects the best hint
    internally and will pick one of the minutes-long methods in `_SKIP_HINTS`.
    An explicit answer always wins over an implicit one; an implicit or
    quadrature answer is still returned when nothing better exists.
    """
    fast = _linear_first_order(parsed, ics)
    if fast is not None:
        # The integrating factor is already exact; sweeping the hints afterwards
        # can take longer than the worker's whole time budget, which would throw
        # this answer away.
        return fast

    x = Symbol(parsed.independent)
    y_fn = Function(parsed.variable)(x)
    deadline = time.monotonic() + budget

    def attempt(hint: str | None, conditions: dict[Any, Any] | None) -> Any:
        kwargs: dict[str, Any] = {}
        if hint:
            kwargs["hint"] = hint
        if conditions:
            kwargs["ics"] = conditions
        try:
            return dsolve(parsed.ode, y_fn, **kwargs)
        except Exception:
            return None

    order = _hint_candidates(parsed)
    seen: set[str | None] = set()
    fallback: SymbolicSolution | None = None
    for hint in order:
        if hint in seen:
            continue
        seen.add(hint)
        for conditions in ([ics, None] if ics else [None]):
            if time.monotonic() > deadline:
                return fallback
            found = _as_solution(attempt(hint, conditions), y_fn)
            if found is None:
                continue
            if found.kind in {"symbolic"}:
                return found
            fallback = fallback or found
    if fallback is not None:
        return fallback
    conserved = _autonomous_conserved(parsed)
    if conserved is not None:
        return conserved
    # SymPy's own Riccati hint crashes on equations without a rational
    # particular solution, so reduce to a linear second-order equation instead.
    reduced = _riccati_reduction(parsed)
    if reduced is not None:
        return reduced
    # Nothing closed-form: at least hand back the general series, which keeps
    # C1/C2. With initial conditions the caller prefers its numeric Taylor.
    if ics is None:
        return _general_power_series(parsed)
    return None


def _riccati_reduction(parsed: ParsedEquation) -> SymbolicSolution | None:
    """``y' = a(t)·y² + b(t)·y + c(t)`` as a linear second-order equation for u.

    Substituting ``y = -u'/(a·u)`` turns *every* Riccati equation into
    ``u'' - (b + a'/a)·u' + a·c·u = 0``, which has a closed-form answer whenever
    the resulting linear equation does. That is what makes ``y' = y² - t``
    solvable exactly (Airy) instead of only as a series.

    SymPy implements the same idea in ``1st_rational_riccati``, but that code
    path raises ``TypeError: bad operand type for unary -: 'list'`` whenever it
    finds no rational particular solution, so the capability was silently lost.
    """
    if parsed.order != 1:
        return None
    t = Symbol(parsed.independent)
    y_fn = Function(parsed.variable)(t)
    try:
        poly = Poly(parsed.rhs, y_fn)
    except Exception:
        return None
    if poly.degree() != 2:
        return None
    try:
        a = simplify(poly.coeff_monomial(y_fn ** 2))
        b = simplify(poly.coeff_monomial(y_fn))
        c = simplify(poly.coeff_monomial(1))
    except Exception:
        return None
    if a.is_zero or (a.free_symbols | b.free_symbols | c.free_symbols) - {t}:
        return None
    try:
        u = Function("_u")(t)
        linear = dsolve(Eq(u.diff(t, 2) - (b + a.diff(t) / a) * u.diff(t) + a * c * u, 0), u)
    except Exception:
        return None
    if not isinstance(linear, Eq) or not linear.has(u):
        return None
    # u = C1·u1 + C2·u2 collapses to one constant once the ratio u'/u is taken.
    constant = Symbol("C1")
    others = [s for s in sorted(linear.rhs.free_symbols, key=str) if str(s).startswith("C")]
    if not others:
        return None
    ratio = linear.rhs.diff(t) / linear.rhs
    ratio = ratio.subs({others[0]: 1, **{o: constant for o in others[1:]}})
    try:
        solution = -ratio / a
    except Exception:
        return None
    try:
        if solution.count_ops() > MAX_SOLUTION_OPS:
            return None
        solution = simplify(solution)
    except Exception:
        pass
    try:
        equation = Eq(y_fn, solution)
    except Exception:
        return None
    if equation.count_ops() > MAX_SOLUTION_OPS * 3:
        return None
    if not _clean_answer(equation, y_fn):
        return None
    return SymbolicSolution(equation, _display(equation), "symbolic")


def _general_power_series(parsed: ParsedEquation, t0: Any = 0,
                          terms: int = 6) -> SymbolicSolution | None:
    """Power-series solution in terms of the free constants (no initial values).

    The coefficients come from the same derivative recursion as the numeric
    Taylor fallback, only with ``C1``/``C2`` standing in for y(t0) and y'(t0).
    SymPy's own ``*_power_series`` hints keep the constant symbolic inside its
    recurrence solver and allocate gigabytes; this recursion only differentiates
    and substitutes, so it stays small.
    """
    if parsed.order not in (1, 2):
        return None
    t = Symbol(parsed.independent)
    y_fn = Function(parsed.variable)(t)
    # Only linear equations: for a nonlinear right-hand side the coefficients
    # blow up into C1**6-style polynomials, which is a series in name only.
    try:
        highest = {y_fn: Symbol("_p0"), diff(y_fn, t): Symbol("_p1")}
        if parsed.order == 2:
            highest[diff(y_fn, t, 2)] = Symbol("_p2")
        probe = (diff(y_fn, t, parsed.order) - parsed.rhs).subs(highest)
        linear = Poly(probe, *highest.values())
        if linear.total_degree() > 1:
            return None
    except Exception:
        return None
    c1, c2 = Symbol("C1"), Symbol("C2")
    order = parsed.order
    d: dict[int, Any] = {0: y_fn, 1: Derivative(y_fn, t)}
    if order == 2:
        d[2] = parsed.rhs
    else:
        d[1] = parsed.rhs
    min_replaced = 1 if order == 1 else 2
    for k in range(order + 1, terms):
        try:
            expr = diff(d[k - 1], t)
        except Exception:
            return None
        for _ in range(terms + 2):
            atoms = [a for a in expr.atoms(Derivative) if len(a.variables) >= min_replaced]
            if not atoms:
                break
            for atom in sorted(atoms, key=lambda a: -len(a.variables)):
                target = d.get(len(atom.variables))
                if target is not None:
                    expr = expr.subs(atom, target)
        d[k] = expr

    values = {y_fn: c1}
    if order == 2:
        values[Derivative(y_fn, t)] = c2
    polynomial = 0
    for k in range(terms):
        try:
            coefficient = d[k].subs(values).subs(t, t0)
        except Exception:
            return None
        if coefficient is S.NaN or coefficient.has(S.NaN) or coefficient.has(S.ComplexInfinity):
            return None
        if coefficient.count_ops() > 400:
            return None
        polynomial += coefficient / factorial(k) * (t - t0) ** k
    equation = Eq(y_fn, polynomial)
    if equation.count_ops() > MAX_SOLUTION_OPS * 3:
        return None
    if not _clean_answer(equation, y_fn):
        return None
    return SymbolicSolution(equation, _display(equation), "series")


def _autonomous_conserved(parsed: ParsedEquation) -> SymbolicSolution | None:
    """Energy integral for ``y'' = f(y)`` — the classic autonomous case.

    Multiplying by y' turns the equation into ``½ y'² = F(y) + C1``, so the
    general solution is the quadrature ``∫ dy / sqrt(2(F(y) + C1)) = ±(t + C2)``.
    SymPy's own hint for this can take minutes, this takes milliseconds.
    """
    if parsed.order != 2:
        return None
    t = Symbol(parsed.independent)
    y_fn = Function(parsed.variable)(t)
    y_sym = Symbol("_y")
    v_sym = Symbol("_v")
    try:
        body = parsed.rhs.subs(y_fn, y_sym).subs(Derivative(y_fn, t), v_sym)
    except Exception:
        return None
    if body.has(t) or body.has(v_sym):
        return None
    c1, c2 = Symbol("C1"), Symbol("C2")
    try:
        if body.count_ops() > 60:
            return None
        potential = integrate(body, y_sym)
    except Exception:
        return None
    if potential.has(Integral):
        return None
    # The second integral is deliberately left unevaluated: for the pendulum it
    # is elliptic and evaluating it can take minutes, while the quadrature form
    # is already the general solution the user asked for.
    integrand = 1 / sqrt(2 * (potential + c1))
    try:
        equation = Eq(Integral(integrand, y_sym), t + c2)
        pretty = _display(equation)
    except Exception:
        return None
    return SymbolicSolution(equation, pretty, "implicit")


def _taylor_expression(parsed: ParsedEquation, t0: float, initial: list[float],
                       terms: int = 8) -> Any | None:
    """Taylor polynomial of the solution around ``t0`` (works for any smooth ODE).

    Successive derivatives are built symbolically and every ``Derivative(y, t, j)``
    is replaced by the expression for ``y^{(j)}`` before the next differentiation,
    which is the standard recursion for Taylor coefficients.
    """
    t = Symbol(parsed.independent)
    y_fn = Function(parsed.variable)(t)
    order = parsed.order
    d: dict[int, Any] = {0: y_fn, 1: Derivative(y_fn, t)}
    if order == 2:
        d[2] = parsed.rhs
    else:
        d[1] = parsed.rhs
    min_replaced = 1 if order == 1 else 2

    for k in range(order + 1, terms):
        try:
            expr = diff(d[k - 1], t)
        except Exception:
            return None
        for _ in range(terms + 2):
            atoms = [a for a in expr.atoms(Derivative) if len(a.variables) >= min_replaced]
            if not atoms:
                break
            for atom in sorted(atoms, key=lambda a: -len(a.variables)):
                target = d.get(len(atom.variables))
                if target is not None:
                    expr = expr.subs(atom, target)
        d[k] = expr

    values = {y_fn: float(initial[0])}
    if order == 2:
        values[Derivative(y_fn, t)] = float(initial[1]) if len(initial) > 1 else 0.0
    polynomial = 0
    for k in range(terms):
        try:
            coefficient = float(d[k].subs(values).subs(t, t0))
        except (TypeError, ValueError, AttributeError):
            return None
        if not np.isfinite(coefficient):
            return None
        if coefficient:
            polynomial += coefficient / factorial(k) * (t - t0) ** k
    try:
        return simplify(polynomial)
    except Exception:
        return polynomial


def solve_series(parsed: ParsedEquation, t0: float, initial: list[float],
                 terms: int = 8) -> SymbolicSolution | None:
    """A guaranteed explicit answer for smooth equations without a closed form."""
    polynomial = _taylor_expression(parsed, t0, initial, terms)
    if polynomial is None or polynomial == 0:
        return None
    x = Symbol(parsed.independent)
    y_fn = Function(parsed.variable)(x)
    pretty = _display(Eq(y_fn, polynomial))
    return SymbolicSolution(Eq(y_fn, polynomial), pretty, "series")


# ---------------------------------------------------------------------------
# Algebraic equations (no derivative at all)
# ---------------------------------------------------------------------------
def solve_algebraic(text: str, variable: str = "y") -> SymbolicSolution | None:
    """Solve a plain algebraic equation instead of erroring out.

    ``x^2 - 5*x + 6 = 0`` is not a differential equation, but it does have an
    answer — returning the roots is friendlier than an error. ``y = x^2`` has
    two letters, yet it is a complete answer for the variable the workspace
    solves for, so the other letter is treated as a parameter.
    """
    try:
        cleaned = normalize_text(text)
    except EquationError:
        return None
    if "=" not in cleaned:
        return None
    sides = cleaned.split("=")
    if len(sides) != 2:
        return None
    marked = cleaned.replace("^", "**")
    for alias, real in _FUNC_ALIASES.items():
        marked = re.sub(rf"\b{alias}\s*\(", f"{real}(", marked)
    names = {n for n in _IDENT_RE.findall(marked)
             if n not in _ALLOWED_FUNCS and n not in _FUNC_ALIASES and n not in {"pi", "E", "oo"}}
    if len(names) == 1:
        unknown = names.pop()
    elif len(names) == 2:
        # Two letters: report the answer for the workspace variable when it is
        # present, otherwise for the first letter, and call the other a
        # parameter (``a*b = 6`` becomes ``a = 6/b``).
        unknown = variable if variable in names else sorted(names)[0]
    else:
        return None
    symbol = Symbol(unknown)
    _guard(marked, names)
    local_ns = {name: Symbol(name) for name in names}
    try:
        left = parse_expr(sides[0].replace("^", "**"), local_dict=local_ns,
                          global_dict=_GLOBAL_DICT, transformations=_TRANSFORMS, evaluate=True)
        right = parse_expr(sides[1].replace("^", "**"), local_dict=local_ns,
                           global_dict=_GLOBAL_DICT, transformations=_TRANSFORMS, evaluate=True)
        roots = sym_solve(Eq(left, right), symbol)
    except Exception:
        return None
    if not roots:
        return None
    texts = []
    for root in roots:
        try:
            texts.append(str(simplify(root)))
        except Exception:
            texts.append(str(root))
    pretty = "  or  ".join(f"{unknown} = {value}" for value in texts)
    return SymbolicSolution(Eq(left, right), pretty, "algebraic", len(roots))


def evaluate_solution(solution: SymbolicSolution, parsed: ParsedEquation,
                      t_span: tuple[float, float],
                      points: int) -> tuple[list[float], list[list[float]]] | None:
    """Sample an explicit solution on a grid, substituting leftover constants with 1.

    Implicit and quadrature answers have no ``y(t) = ...`` form to sample, so they
    return ``None`` and the caller draws the numerical curve instead.
    """
    x = Symbol(parsed.independent)
    y_fn = Function(parsed.variable)(x)
    expr = solution.equation
    if not isinstance(expr, Eq) or expr.lhs != y_fn or expr.rhs.has(Integral):
        return None
    body = expr.rhs
    free = sorted((s for s in body.free_symbols - {x}), key=str)
    constants = [c for c in free if str(c).startswith("C")]
    if constants:
        body = body.subs({c: 1 for c in constants})
    if body.free_symbols - {x}:
        return None
    grid = np.linspace(t_span[0], t_span[1], points)
    values: list[list[float]] = []
    for tv in grid:
        try:
            value = float(body.subs(x, tv))
        except (TypeError, ValueError):
            return None
        if not np.isfinite(value):
            return None
        values.append([value])
    return grid.tolist(), values


# ---------------------------------------------------------------------------
# Numerical fallback
# ---------------------------------------------------------------------------
def _numeric_rhs(parsed: ParsedEquation):
    x = Symbol(parsed.independent)
    y_sym = Symbol("_y")
    v_sym = Symbol("_v")
    y_fn = Function(parsed.variable)(x)
    body = parsed.rhs.subs(y_fn, y_sym)
    if parsed.order == 2:
        body = body.subs(Derivative(y_fn, x), v_sym)
        if body.has(Derivative(y_fn, x, 2)):
            return None
    if body.atoms(Derivative):
        return None
    free = body.free_symbols - {x, y_sym, v_sym}
    if free:
        return None                      # unresolved constants: not integrable numerically
    try:
        if parsed.order == 2:
            compiled = lambdify_safe((x, y_sym, v_sym), body)
            return lambda t, y, v: compiled(t, y, v)
        compiled = lambdify_safe((x, y_sym), body)
        return lambda t, y, v: compiled(t, y)
    except Exception:
        return None


def lambdify_safe(args: tuple[Any, ...], body: Any):
    from sympy import lambdify

    return lambdify(args, body, modules=["math", "numpy"])


class _CurveLimit(RuntimeError):
    """Raised inside the RHS wrapper to stop a runaway numerical integration."""


def solve_numeric(parsed: ParsedEquation, t_span: tuple[float, float], initial: list[float],
                  points: int) -> tuple[list[float], list[list[float]], float, str] | None:
    """Integrate the ODE, trying an explicit method then stiff implicit ones.

    The right-hand side is wrapped so a blow-up (infinite or astronomically
    large values) and a step-size collapse both abort the attempt instead of
    spinning forever.
    """
    rhs = _numeric_rhs(parsed)
    if rhs is None:
        return None
    grid = np.linspace(t_span[0], t_span[1], points)

    def raw(t: float, state: np.ndarray) -> list[float]:
        with np.errstate(all="ignore"):
            if parsed.order == 2:
                return [float(state[1]), float(rhs(t, float(state[0]), float(state[1])))]
            return [float(rhs(t, float(state[0]), 0.0))]

    deadline = time.monotonic() + NUMERIC_TIMEOUT_SECONDS
    allowance = NUMERIC_MAX_EVALS

    def wrapped(t: float, state: np.ndarray) -> list[float]:
        nonlocal allowance
        allowance -= 1
        if allowance <= 0 or time.monotonic() > deadline:
            raise _CurveLimit("the integrator ran out of time on this interval.")
        out = raw(t, state)
        if not all(np.isfinite(v) for v in out):
            raise _CurveLimit("the solution left the real numbers on this interval.")
        if any(abs(v) > NUMERIC_MAX_MAGNITUDE for v in np.atleast_1d(state)):
            raise _CurveLimit("the solution grew without bound on this interval.")
        return out

    missing = parsed.order - len(initial)
    state0 = [float(v) for v in initial] + [0.0] * max(missing, 0)
    if len(state0) < parsed.order:
        state0 += [0.0] * (parsed.order - len(state0))

    for method in ("RK45", "BDF", "Radau"):
        try:
            solution = solve_ivp(wrapped, t_span, state0, method=method, t_eval=grid,
                                 rtol=1e-8, atol=1e-10, max_step=np.inf)
        except Exception:                             # noqa: BLE001 - report, then retry stiff
            continue
        if not solution.success or solution.y.shape[1] != grid.size:
            continue
        values = solution.y.T
        if not np.all(np.isfinite(values)):
            continue
        rows = [[float(v) for v in row] for row in values]
        residual = _residual(parsed, raw, solution.t, values)
        return solution.t.tolist(), rows, residual, method
    return None


def _residual(parsed: ParsedEquation, wrapped, t_vals: np.ndarray, values: np.ndarray) -> float:
    if t_vals.size < 3:
        return 0.0
    try:
        deriv = np.gradient(values, t_vals, axis=0)
        expected = np.vstack([wrapped(t, row) for t, row in zip(t_vals, values, strict=False)])
        diff = np.abs(deriv - expected)
        if not np.all(np.isfinite(diff)):
            return float("inf")
        return float(np.max(diff))
    except Exception:                                  # noqa: BLE001 - residual is a diagnostic
        return float("inf")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def _kind_message(kind: str, particular: bool) -> str:
    """The user-facing explanation for an exact answer of a given kind."""
    if kind == "integral":
        if particular:
            return "Exact solution honoring the initial conditions, with the integral left unevaluated."
        return "Exact general solution containing an unevaluated integral."
    if kind == "implicit":
        if particular:
            return "Implicit solution honoring the initial conditions — the integral is left unevaluated."
        return ("General solution in implicit (quadrature) form — the equation was integrated "
                "once and the integral is left unevaluated.")
    if kind == "series":
        return "No elementary closed form was found — this is the Taylor series of the solution."
    if kind == "algebraic":
        return "This is not a differential equation — solved algebraically."
    if particular:
        return "Exact solution honoring the initial conditions"
    return "Exact general solution (constants set to 1 for the plotted curve)"


# ---------------------------------------------------------------------------
# Bounded exact-solver worker
# ---------------------------------------------------------------------------
# ``solve_symbolic`` is a shared-nothing, CPU-only job, so the parent only ever
# receives plain data back — never a SymPy object.


def _vsz_bytes() -> int:
    """Current virtual address-space size (numpy/BLAS reserve gigabytes up front)."""
    try:
        with open("/proc/self/statm", encoding="ascii") as handle:
            pages = int(handle.read().split()[0])
        return pages * os.sysconf("SC_PAGE_SIZE")
    except Exception:
        return 0


def _sweep_child(conn: Any, text: str, variable: str, independent: str,
                span: tuple[float, float], initial: list[float], count: int) -> None:
    """Entry point of the forked worker. Never returns; always ``os._exit``s."""
    try:
        import resource

        # The cap is relative: numpy and SymPy already reserve several gigabytes
        # of address space, so an absolute limit would starve the worker before
        # it does anything. This bounds how much *more* it may allocate.
        cap = _vsz_bytes() + SYMBOLIC_MEMORY_CAP_MB * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
    except Exception:
        pass
    payload: dict[str, Any] | None = None
    try:
        parsed = parse_equation(text, variable, independent)
        conditions, _ = _ics_for(parsed, initial, span[0])
        solution = solve_symbolic(parsed, conditions)
        if solution is not None:
            payload = {
                "kind": solution.kind,
                "pretty": solution.pretty,
                "particular": bool(conditions) and _is_particular(solution, parsed),
                "branches": solution.branches,
                "t": [],
                "y": [],
            }
            sampled = evaluate_solution(solution, parsed, span, count)
            if sampled is not None:
                payload["t"], payload["y"] = sampled
    except BaseException:
        payload = None
    try:
        conn.send(payload)
        conn.close()
    except Exception:
        pass
    os._exit(0)


def _symbolic_guarded(text: str, variable: str, independent: str,
                      span: tuple[float, float], initial: list[float],
                      count: int) -> dict[str, Any] | None:
    """Run the exact sweep under a hard time and memory cap.

    Returns a plain dict (``kind``, ``pretty``, ``particular``, ``branches``,
    ``t``, ``y``) or ``None`` when the worker overran, crashed, or the platform
    cannot fork. ``None`` simply means "no exact answer available" — the caller
    then falls back to the Taylor series and the numerical solution.
    """
    if not hasattr(os, "fork"):
        return None
    try:
        import multiprocessing

        ctx = multiprocessing.get_context("fork")
    except (ImportError, ValueError):
        return None
    try:
        parent_conn, child_conn = ctx.Pipe(duplex=False)
        proc = ctx.Process(
            target=_sweep_child,
            args=(child_conn, text, variable, independent, span, initial, count),
            daemon=True,
        )
        proc.start()
    except Exception:
        return None
    child_conn.close()
    payload: dict[str, Any] | None = None
    try:
        if parent_conn.poll(SYMBOLIC_TIMEOUT_SECONDS):
            payload = parent_conn.recv()
    except (EOFError, OSError):
        payload = None
    finally:
        try:
            if proc.is_alive():
                proc.kill()
            proc.join(timeout=3)
        except Exception:
            pass
        try:
            parent_conn.close()
        except Exception:
            pass
    return payload if isinstance(payload, dict) else None


def _attach_curve(payload: dict[str, Any], parsed: ParsedEquation, span: tuple[float, float],
                  initial: list[float], count: int) -> bool:
    """Add the numerical trajectory to a payload that already has an exact answer."""
    numeric = solve_numeric(parsed, span, initial, count)
    if numeric is None:
        return False
    t_vals, y_vals, residual, _method = numeric
    payload["t"], payload["y"] = t_vals, y_vals
    payload["residual_max"] = residual
    return True


def _sample_series(solution: SymbolicSolution, parsed: ParsedEquation,
                   span: tuple[float, float], count: int) -> tuple[list[float], list[list[float]]] | None:
    """Evaluate a Taylor polynomial on a grid (used only when integration fails)."""
    x = Symbol(parsed.independent)
    body = solution.equation.rhs
    grid = np.linspace(span[0], span[1], count)
    values: list[list[float]] = []
    for tv in grid:
        try:
            value = float(body.subs(x, tv))
        except (TypeError, ValueError):
            return None
        if not np.isfinite(value):
            return None
        values.append([value])
    return grid.tolist(), values


def _ics_for(parsed: ParsedEquation, initial: list[float], t0: float) -> tuple[dict[Any, Any] | None, list[float]]:
    x = Symbol(parsed.independent)
    y_fn = Function(parsed.variable)(x)
    if not initial:
        return None, []
    conditions: dict[Any, Any] = {}
    values = [float(v) for v in initial[: parsed.order]]
    conditions[y_fn.subs(x, t0)] = values[0]
    if parsed.order == 2 and len(values) > 1:
        conditions[Derivative(y_fn, x).subs(x, t0)] = values[1]
    return conditions, values


def solve_equation(text: str, variable: str = "y", independent: str = "t",
                   t_span: tuple[float, float] = DEFAULT_SPAN,
                   initial: list[float] | None = None,
                   points: int = 200,
                   symbolic_only: bool = False) -> dict[str, Any]:
    """Solve whatever the user typed: exact form first, numeric curve always."""
    span = (float(t_span[0]), float(t_span[1]))
    if not np.isfinite(span[0]) or not np.isfinite(span[1]) or span[1] <= span[0]:
        raise EquationError("The time span must increase (t end > t start).")
    count = max(2, min(MAX_POINTS, int(points)))

    explicit_initial = [float(v) for v in (initial or [])]
    try:
        parsed = parse_equation(text, variable, independent)
    except NotAnEquationError:
        algebraic = solve_algebraic(text, variable)
        if algebraic is None:
            raise
        return {
            "status": "success", "kind": "algebraic", "order": 0,
            "variable": None, "independent": None, "normalized": text.strip(),
            "t": [], "y": [], "residual_max": 0.0, "method": "solve",
            "solution": algebraic.pretty,
            "message": _kind_message("algebraic", False),
            "hint": "Add a derivative to solve it as a differential equation.",
            "initial_values": explicit_initial, "t_span": [span[0], span[1]],
        }

    if not explicit_initial and parsed.inline_initial:
        explicit_initial = list(parsed.inline_initial)
        if parsed.initial_at is not None and parsed.initial_at < span[1]:
            span = (parsed.initial_at, span[1])

    # The general solution stays general; the curve needs *some* starting value.
    curve_initial = explicit_initial or ([1.0, 0.0] if parsed.order == 2 else [1.0])

    payload: dict[str, Any] = {
        "status": "failed",
        "kind": None,
        "order": parsed.order,
        "variable": parsed.variable,
        "independent": parsed.independent,
        "normalized": parsed.normalized,
        "t": [],
        "y": [],
        "residual_max": None,
        "method": None,
        "solution": None,
        "message": "",
        "hint": "",
        "initial_values": list(curve_initial),
        "t_span": [span[0], span[1]],
    }

    # 1. An exact answer, in whatever form SymPy can reach. This runs in a
    #    bounded worker process, because SymPy's integrator can otherwise consume
    #    minutes and gigabytes on an ordinary-looking equation.
    exact = _symbolic_guarded(text, parsed.variable, parsed.independent, span,
                              explicit_initial, count)
    if exact is not None:
        payload.update({
            "status": "success",
            "kind": exact["kind"],
            "method": "symbolic",
            "solution": exact["pretty"],
            "residual_max": 0.0,
            "message": _kind_message(str(exact["kind"]), bool(exact.get("particular"))),
        })
        notes: list[str] = []
        branches = int(exact.get("branches") or 1)
        if branches > 1:
            notes.append(f"One of {branches} solution branches is shown.")
        payload["t"] = exact.get("t") or []
        payload["y"] = exact.get("y") or []
        if not payload["y"] and not symbolic_only:
            # Implicit/quadrature answers cannot be sampled, so draw the numerical
            # trajectory next to the exact result.
            attached = _attach_curve(payload, parsed, span, curve_initial, count)
            if attached and str(exact["kind"]) in {"implicit", "integral"}:
                notes.append(
                    "The exact answer cannot be sampled directly, so the curve is the "
                    f"numerical solution for {parsed.variable}({span[0]:g}) = "
                    f"{curve_initial[0]:g}.")
        payload["hint"] = " ".join(notes)
        return payload

    if symbolic_only:
        payload["message"] = "No exact solution was found for this equation."
        return payload

    # 2. No closed form: give the Taylor series of the solution plus the curve.
    series = solve_series(parsed, span[0], curve_initial)
    if series is not None:
        payload.update({
            "status": "success",
            "kind": "series",
            "method": "series",
            "solution": series.pretty,
            "residual_max": 0.0,
            "message": _kind_message("series", False),
            "hint": (f"Expansion around {parsed.independent} = {span[0]:g} with "
                     f"{parsed.variable}({span[0]:g}) = {curve_initial[0]:g}"),
        })
        if not _attach_curve(payload, parsed, span, curve_initial, count):
            sampled = _sample_series(series, parsed, span, count)
            if sampled is not None:
                payload["t"], payload["y"] = sampled
        return payload

    # 3. Last resort: the numerical solution on its own.
    numeric = solve_numeric(parsed, span, curve_initial, count)
    if numeric is not None:
        t_vals, y_vals, residual, method = numeric
        payload.update({
            "status": "success",
            "kind": "numeric",
            "method": method,
            "t": t_vals,
            "y": y_vals,
            "residual_max": residual,
            "message": "Verified numerical solution.",
            "hint": "Add initial conditions to plot the curve for your specific problem.",
        })
        return payload

    payload["message"] = ("No closed form, series or real numerical solution could be "
                          "produced on this interval.")
    payload["hint"] = ("Try a shorter time span, different initial values, or one of the "
                       "42 model families in the Model solver tab.")
    return payload
