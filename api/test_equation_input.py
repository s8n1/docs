"""Free-form equation intake: notation handling, symbolic/numeric solving, safety."""
from __future__ import annotations

import pytest

from api.equation_input import (
    EquationError,
    SymbolicSolution,
    evaluate_solution,
    parse_equation,
    solve_algebraic,
    solve_equation,
    solve_numeric,
    solve_symbolic,
)

# Every answer this solver can produce. The point of the module is that a
# free-form equation never dead-ends, so tests assert *some* answer rather than
# one particular method.
ANSWER_KINDS = {"symbolic", "numeric", "series", "implicit", "integral", "algebraic"}
# Of those, only these can be sampled into a plottable curve.
CURVE_KINDS = {"symbolic", "numeric", "series"}


def _solve(text, **kwargs):
    kwargs.setdefault("t_span", (0.0, 3.0))
    kwargs.setdefault("points", 25)
    return solve_equation(text, **kwargs)


@pytest.mark.parametrize("text", [
    "-y",
    "-2*y + sin(t)",
    "y*(1 - y/10)",
    "y' = -2*y",
    "y' + 2*y = 0",
    "dy/dt = -2*y",
    "2y' + y = 0",
    "y'' + 2*y' + y = 0",
    "y'' = -y",
    "d^2y/dt^2 = -y",
    "x*y' = y",
    "y' = x^2",
    "y\u2032 = x\u00b2 - y",          # unicode prime and superscript
])
def test_notation_variants_all_solve(text):
    result = _solve(text)
    assert result["status"] == "success", text
    assert result["kind"] in ANSWER_KINDS
    assert result["solution"], text
    assert len(result["y"]) == len(result["t"])
    if result["kind"] in CURVE_KINDS:
        assert len(result["t"]) >= 2


def test_bare_rhs_matches_full_equation():
    bare = _solve("y' = -2*y")
    full = _solve("y' + 2*y = 0")
    assert bare["solution"] == full["solution"]


def test_second_order_honours_two_initial_conditions():
    result = _solve("y'' = -y", t_span=(0.0, 6.28), initial=[0.0, 1.0])
    assert result["status"] == "success"
    assert result["order"] == 2
    assert "sin" in result["solution"]
    assert abs(result["y"][0][0]) < 1e-6


def test_inline_initial_conditions_are_parsed():
    result = _solve("y' = -2y, y(0) = 1", t_span=(0.0, 3.0))
    assert result["status"] == "success"
    assert result["initial_values"] == [1.0]
    assert result["t_span"][0] == 0.0
    assert abs(result["y"][0][0] - 1.0) < 1e-6


def test_first_order_missing_closed_form_still_answers():
    result = _solve("y' = y^2 + t^2", t_span=(0.0, 1.0), initial=[0.5])
    assert result["status"] == "success"
    assert result["kind"] in ANSWER_KINDS - {"algebraic", "invalid"}
    assert result["solution"]
    assert len(result["t"]) >= 2


def test_no_closed_form_falls_back_to_taylor_series():
    result = _solve("y' = y^2 + t^2", t_span=(0.0, 1.0), initial=[0.5])
    assert result["kind"] == "series"
    assert "t**" in result["solution"]
    # The series cannot be summed, so the numerical curve supplies the residual,
    # which is the accuracy achieved (see solver_core.integration_error).
    assert result["residual_max"] is not None
    assert 0.0 <= result["residual_max"] < 1e-5
    assert len(result["y"]) == len(result["t"]) >= 2


def test_numeric_residual_is_independent_of_curve_density():
    """Asking for more points must not inflate the reported residual."""
    sparse = _solve("y' = y^2 + t^2", t_span=(0.0, 1.0), initial=[0.5], points=10)
    dense = _solve("y' = y^2 + t^2", t_span=(0.0, 1.0), initial=[0.5], points=400)
    assert sparse["residual_max"] < 1e-5
    assert dense["residual_max"] < 1e-5


def test_riccati_equation_reduces_to_a_linear_second_order_problem():
    """``y' = y² - t`` is the Airy equation in disguise: y = -u'/u, u'' = t·u.

    SymPy's own ``1st_rational_riccati`` hint raises TypeError here, so this is
    the regression test for the reduction that replaces it.
    """
    result = _solve("y' = y^2 - t", t_span=(0.0, 2.0))
    assert result["status"] == "success"
    assert result["kind"] == "symbolic"
    assert "airy" in result["solution"]


def test_general_power_series_keeps_the_integration_constants():
    """No closed form: the series must still be the general solution."""
    result = _solve("y'' + t*y' + t^2*y = 0", t_span=(0.0, 2.0))
    assert result["status"] == "success"
    assert result["kind"] == "series"
    assert "C1" in result["solution"] and "C2" in result["solution"]


def test_truncation_orders_never_leak_into_an_answer():
    """SymPy's ``factorable`` hint returns ``O(t**6)`` and an ``r(3)`` helper."""
    for text in ("y'' + t*y' + t^2*y = 0", "y' = y^2 + t^2", "y'' + t*y = 0"):
        result = _solve(text, t_span=(0.0, 2.0))
        assert "O(" not in (result["solution"] or ""), text
        assert "r(" not in (result["solution"] or ""), text


def test_linear_equation_keeps_the_quadrature_symbolic():
    """The unevaluated integral is what keeps this equation fast."""
    result = _solve("y' = sin(t)*y + t", t_span=(0.0, 2.0))
    assert result["status"] == "success"
    assert result["kind"] == "integral"
    assert "Integral" in result["solution"]
    # The exact answer cannot be sampled, so the numerical curve rides along.
    assert len(result["t"]) >= 2


def test_linear_equation_with_initial_values_gets_a_particular_answer():
    result = _solve("y' = sin(t)*y + t, y(0) = 1", t_span=(0.0, 2.0))
    assert result["status"] == "success"
    assert result["initial_values"] == [1.0]
    assert result["kind"] == "integral"
    assert "C1" not in result["solution"]


def test_autonomous_second_order_returns_an_energy_integral():
    result = _solve("y'' + sin(y) = 0", t_span=(0.0, 2.0))
    assert result["status"] == "success"
    assert result["kind"] == "implicit"
    assert "Integral" in result["solution"]
    assert len(result["t"]) >= 2


def test_runaway_solution_is_bounded_and_still_answers():
    """``y' = tan(y)`` blows up at t = 0.17; the integrator must not spin."""
    result = _solve("y' = tan(y)", t_span=(0.0, 2.0))
    assert result["status"] == "success"
    assert result["kind"] in ANSWER_KINDS
    assert result["solution"]


def test_non_differential_equation_still_gets_roots():
    result = _solve("x^2 - 5*x + 6 = 0")
    assert result["status"] == "success"
    assert result["kind"] == "algebraic"
    assert result["order"] == 0
    assert "x = 2" in result["solution"] and "x = 3" in result["solution"]


def test_relation_is_solved_for_the_dependent_variable():
    result = _solve("y = x^2")
    assert result["status"] == "success"
    assert result["kind"] == "algebraic"
    assert result["solution"] == "y = x**2"


def test_algebraic_solver_needs_at_most_two_letters():
    assert solve_algebraic("x^2 - 5*x + 6 = 0") is not None
    solution = solve_algebraic("a*b = 6")
    assert isinstance(solution, SymbolicSolution)
    assert solution.pretty.startswith("a = ")
    assert solve_algebraic("a + b + c = 0") is None


def test_implicit_answers_are_not_forced_onto_a_grid():
    parsed = parse_equation("y'' + sin(y) = 0")
    implicit = solve_symbolic(parsed)
    assert implicit is not None and implicit.kind == "implicit"
    assert evaluate_solution(implicit, parsed, (0.0, 2.0), 10) is None


def test_symbolic_only_reports_when_nothing_exact_exists():
    result = solve_equation("y' = y^2 + t^2", t_span=(0.0, 1.0), initial=[0.5],
                            symbolic_only=True)
    assert result["status"] == "failed"
    assert result["kind"] is None
    assert "exact solution" in result["message"]


def test_independent_variable_is_taken_from_the_text():
    parsed = parse_equation("dy/dx + y = 0")
    assert parsed.independent == "x"
    assert parsed.variable == "y"
    assert parsed.order == 1


def test_order_is_detected():
    assert parse_equation("-y").order == 1
    assert parse_equation("y' = -2*y").order == 1
    assert parse_equation("y'' + y = 0").order == 2
    assert parse_equation("d^2y/dt^2 = -y").order == 2


@pytest.mark.parametrize("text", [
    "__import__('os').system('id')",
    "os.system('id')",
    "y' = [1, 2][0]",
    "y' = Symbol('x')",
    "y' = unknownfunc(t)",
    "y' = lambda t: t",
])
def test_unsafe_or_unknown_input_is_rejected(text):
    with pytest.raises(EquationError):
        parse_equation(text)


def test_missing_derivative_is_reported_clearly():
    with pytest.raises(EquationError, match="No derivative"):
        parse_equation("y = x^2")


def test_empty_input_is_rejected():
    with pytest.raises(EquationError):
        parse_equation("   ")


def test_time_span_must_increase():
    with pytest.raises(EquationError, match="time span"):
        solve_equation("-y", t_span=(2.0, 1.0))


def test_third_order_is_rejected_with_a_clear_message():
    with pytest.raises(EquationError, match="second-order"):
        parse_equation("y''' = y")


# ======================================================================
# Every dead end carries a reason
# ======================================================================
def test_numeric_failure_says_what_went_wrong():
    """A blow-up must explain itself, not just fail.

    ``y' = y²`` with ``y(0) = 1`` is ``1/(1-t)``, which runs away before t = 1;
    the magnitude guard stops it and the outcome names the cause.
    """
    outcome = solve_numeric(parse_equation("y' = y^2"), (0.0, 2.0), [1.0], 50)

    assert not outcome.ok
    assert outcome.reason
    assert "without bound" in outcome.reason


def test_impossible_equation_explains_every_attempt(monkeypatch):
    """The last-resort branch reports why each strategy failed.

    The free-form intake almost always answers, so this drives the branch where
    the exact sweep, the series and the integration all fail, and checks that
    each reason reaches the user instead of a bare "it did not work".
    """
    import api.equation_input as eq

    monkeypatch.setattr(eq, "_symbolic_guarded", lambda *a, **k: (None, "exact said no"))
    monkeypatch.setattr(eq, "solve_series", lambda *a, **k: None)
    monkeypatch.setattr(eq, "solve_numeric", lambda *a, **k: eq.NumericOutcome(
        False, "", [], [], float("inf"), "numeric said no"))

    result = solve_equation("y' = y^2 + t^2", t_span=(0.0, 1.0), initial=[0.5])

    assert result["status"] == "failed"
    assert "exact said no" in result["hint"]
    assert "Taylor expansion" in result["hint"]
    assert "numeric said no" in result["hint"]


def test_exact_search_timeout_is_explained(monkeypatch):
    """When the bounded exact sweep is killed, the reason says so."""
    import api.equation_input as eq

    monkeypatch.setattr(eq, "SYMBOLIC_TIMEOUT_SECONDS", 0.0)
    payload, reason = eq._symbolic_guarded("y' = sin(t)*y + t", "y", "t", (0.0, 1.0), [1.0], 16)

    assert payload is None
    assert reason and "time limit" in reason


def test_exact_search_reason_is_reported_when_only_that_path_is_asked(monkeypatch):
    """A symbolic-only request explains why no closed form was reached."""
    import api.equation_input as eq

    monkeypatch.setattr(eq, "_symbolic_guarded", lambda *a, **k: (
        None, "the exact solver ran out of memory or stopped before answering."))

    result = solve_equation("y' = sin(t)*y + t", t_span=(0.0, 1.0), symbolic_only=True)

    assert result["status"] == "failed"
    assert "ran out of memory" in result["hint"]
