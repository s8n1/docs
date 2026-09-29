"""Skills: registry shape, the maths of each capability, and the API surface."""
from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from api import tokens
from api.equation_input import EquationError
from api.main import app
from api.skills import (
    SKILL_IDS,
    classify_eigenvalues,
    get_skill,
    match_skills,
    parse_system,
    run_skill,
    skill_catalog,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def funded_anon_session(monkeypatch):
    """Each test starts with a fresh anonymous session, funded for the test.

    The real trial balance is deliberately tiny, so it is raised here: these
    tests are about the API surface and its charging behaviour, not about how
    large the free trial is.
    """
    monkeypatch.setattr(tokens, "ANON_TOKENS", 500)
    client.post("/api/auth/logout", json={})
    yield
    client.post("/api/auth/logout", json={})


def _ok(skill_id, **body):
    result = run_skill(skill_id, body)
    assert result["status"] == "success", (skill_id, result["message"])
    return result


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
def test_catalog_is_serialisable_and_complete():
    catalog = skill_catalog()
    assert len(catalog) == len(SKILL_IDS) == 8
    for entry in catalog:
        assert set(entry) == {"id", "name", "category", "kind", "cost", "summary",
                              "when_to_use", "keywords"}
        assert set(entry["name"]) == {"en", "fa"}
        assert set(entry["summary"]) == {"en", "fa"}
        assert set(entry["when_to_use"]) == {"en", "fa"}
        assert entry["cost"] > 0
        assert callable(get_skill(entry["id"]).run)


def test_skill_prices_are_overridable_from_the_admin_table():
    assert tokens.skill_cost("lyapunov_spectrum", 5) == 5
    assert tokens.skill_cost("not-a-skill", 3) == 3


def test_match_skills_ranks_by_keyword():
    ranked = match_skills("find the chaos and lyapunov exponent", limit=3)
    assert ranked[0]["id"] == "lyapunov_spectrum"
    ranked = match_skills("frobenius series at a singular point", limit=3)
    assert ranked[0]["id"] == "frobenius"


def test_match_skills_rejects_empty_text():
    with pytest.raises(EquationError):
        match_skills("   ")


# ---------------------------------------------------------------------------
# System parsing safety
# ---------------------------------------------------------------------------
def test_parse_system_reads_variables_and_implicit_parameters():
    variables, exprs, parameters, independent = parse_system(["y' = a*y - z", "z' = y"])
    assert variables == ("y", "z")
    assert parameters == ("a",)
    assert independent == "t"
    assert len(exprs) == 2


def test_parse_system_accepts_leibniz_notation():
    variables, _, _, _ = parse_system(["dy/dx = -y"])
    assert variables == ("y",)


@pytest.mark.parametrize("bad", [
    ["y' = __import__('os').system('id')"],
    ["y' = y", "y' = -y"],                        # the same variable twice
    ["y' = [1, 2][0]"],
    ["y' = lambda t: t"],
    ["not a system at all"],
])
def test_parse_system_rejects_bad_input(bad):
    with pytest.raises(EquationError):
        parse_system(bad)


def test_parse_system_accepts_a_bare_variable_name():
    variables, _, _, _ = parse_system(["y = -y"])
    assert variables == ("y",)


def test_classify_eigenvalues_covers_the_classic_cases():
    assert classify_eigenvalues(np.array([-1.0, -2.0])) == "stable node"
    assert classify_eigenvalues(np.array([1.0, 2.0])) == "unstable node"
    assert classify_eigenvalues(np.array([-1.0, 1.0])) == "saddle (unstable)"
    assert classify_eigenvalues(np.array([-1 + 2j, -1 - 2j])) == "stable spiral"
    assert classify_eigenvalues(np.array([2j, -2j])) == "centre (marginal)"


# ---------------------------------------------------------------------------
# Symbolic skills
# ---------------------------------------------------------------------------
def test_riccati_skill_returns_the_airy_form():
    result = _ok("riccati_reduction", equation="y' = y^2 - t")
    assert result["kind"] == "symbolic"
    assert "airy" in result["solution"]


def test_riccati_skill_reports_a_non_riccati_equation():
    result = run_skill("riccati_reduction", {"equation": "y' = -2*y"})
    assert result["status"] == "failed"
    assert "Riccati" in result["message"]


def test_power_series_skill_keeps_both_constants():
    result = _ok("power_series", equation="y'' + t*y' + t^2*y = 0")
    assert result["kind"] == "series"
    assert "C1" in result["solution"] and "C2" in result["solution"]


def test_frobenius_skill_solves_bessel():
    result = _ok("frobenius", equation="t^2*y'' + t*y' + (t^2 - 1/4)*y = 0")
    assert result["metadata"]["indicial_roots"] == ["1/2", "-1/2"]
    # Both roots give a series here: J_{1/2} and J_{-1/2} have no log term.
    assert result["metadata"]["integer_gap"] is True
    assert "logarithm" not in result["hint"]


def test_frobenius_skill_flags_the_logarithmic_second_solution():
    result = _ok("frobenius", equation="t^2*y'' + t*y' + (t^2 - 1)*y = 0")
    assert result["metadata"]["indicial_roots"] == ["1", "-1"]
    assert "logarithm" in result["hint"]


def test_frobenius_skill_rejects_an_irregular_singular_point():
    result = run_skill("frobenius", {"equation": "t^3*y'' + y = 0"})
    assert result["status"] == "failed"


# ---------------------------------------------------------------------------
# Analytical skills
# ---------------------------------------------------------------------------
def test_equilibria_skill_classifies_a_saddle_and_a_spiral():
    result = _ok("equilibria_stability", system=["y' = y*(1 - z)", "z' = -z + y"])
    entries = result["metadata"]["equilibria"]
    found = {(tuple(entry["point"]), entry["stability"]) for entry in entries}
    assert ((0.0, 0.0), "saddle (unstable)") in found
    assert ((1.0, 1.0), "stable spiral") in found


def test_equilibria_skill_works_in_one_dimension():
    result = _ok("equilibria_stability", system=["y' = y^2 - 1"])
    labels = {entry["point"][0]: entry["stability"] for entry in result["metadata"]["equilibria"]}
    assert labels[-1.0] == "stable node"
    assert labels[1.0] == "unstable node"


def test_lyapunov_exponent_is_negative_for_a_stable_node():
    result = _ok("lyapunov_spectrum", system=["y' = -3*y"],
                 initial_values=[1.0], t_span=[0.0, 20.0])
    assert result["metadata"]["largest"] == pytest.approx(-3.0, abs=0.05)
    assert result["metadata"]["reliable"] is True
    assert "Stable" in result["message"]


def test_lyapunov_spectrum_of_lorenz_is_chaotic():
    """Regression: the QR factor must be fed back each step.

    Measuring the time-averaged Jacobian instead keeps the trace right (so the
    sum of the exponents still matches) while every individual exponent is
    wrong and the system is misreported as stable.
    """
    result = _ok("lyapunov_spectrum",
                 system=["dx/dt = 10*(y - x)", "dy/dt = x*(28 - z) - y",
                         "dz/dt = x*y - 8*z/3"],
                 initial_values=[1.0, 1.0, 1.0], t_span=[0.0, 200.0])
    exponents = result["metadata"]["exponents"]
    assert exponents[0] > 0.5, exponents
    assert abs(exponents[1]) < 0.2, exponents
    assert exponents[2] < -12.0, exponents
    # The sum equals the divergence of the flow, trace(J) = -10 - 1 - 8/3.
    assert sum(exponents) == pytest.approx(-41.0 / 3.0, rel=1e-3)
    assert "Chaotic" in result["message"]
    # Converged, and within a few percent of the literature value for these
    # parameters (0.906).
    assert result["metadata"]["reliable"] is True
    assert exponents[0] == pytest.approx(0.906, abs=0.05)


def test_lyapunov_warns_instead_of_believing_a_short_interval():
    """A short run used to report +0.13 on Lorenz, whose true value is +0.906.

    The estimator converges from below, so believing it made chaos look tame.
    A span that is too short must now be flagged, never passed off as the
    exponent.
    """
    result = _ok("lyapunov_spectrum",
                 system=["dx/dt = 10*(y - x)", "dy/dt = x*(28 - z) - y",
                         "dz/dt = x*y - 8*z/3"],
                 initial_values=[1.0, 1.0, 1.0], t_span=[0.0, 5.0])
    assert result["metadata"]["reliable"] is False
    assert "Not converged" in result["message"]
    assert "t_span" in result["hint"]
    # The value is still offered, but with its error bar attached.
    assert "+/-" in result["solution"]


def test_lyapunov_default_span_is_long_enough_to_converge():
    """Omitting t_span must not fall back to the free-form solver's short default."""
    result = _ok("lyapunov_spectrum",
                 system=["dx/dt = 10*(y - x)", "dy/dt = x*(28 - z) - y",
                         "dz/dt = x*y - 8*z/3"],
                 initial_values=[1.0, 1.0, 1.0])
    assert result["metadata"]["reliable"] is True
    assert result["metadata"]["interval"][1] >= 100.0
    assert result["metadata"]["largest"] == pytest.approx(0.906, abs=0.06)
    assert "Chaotic" in result["message"]


def test_bifurcation_sweep_finds_the_pitchfork_of_a_cubic():
    result = _ok("bifurcation_sweep", system=["y' = a*y - y^3"], parameter="a",
                 parameter_range=[-1.0, 2.0], steps=40)
    transitions = result["metadata"]["transitions"]
    assert transitions, "the equilibrium count changes at a = 0"
    assert any(abs(item["parameter"]) < 0.2 for item in transitions)


def test_bifurcation_sweep_needs_a_real_parameter():
    result = run_skill("bifurcation_sweep", {"system": ["y' = -y"], "parameter": "q"})
    assert result["status"] == "failed"
    assert "does not appear" in result["message"]


def test_sensitivity_of_a_decay_matches_the_analytic_factor():
    result = _ok("sensitivity_analysis", system=["y' = -2*y"], initial_values=[1.0],
                 t_span=[0.0, 3.0])
    # d y(3) / d y(0) = exp(-6)
    assert result["metadata"]["amplification"] == pytest.approx(float(np.exp(-6.0)), rel=1e-4)


def test_stiffness_scan_recognises_a_stiff_system():
    result = _ok("stiffness_scan", system=["y' = -1000*y + z", "z' = -y"],
                 initial_values=[1.0, 0.0], t_span=[0.0, 0.5])
    assert result["metadata"]["verdict"] == "stiff"
    assert "BDF" in result["hint"]


def test_stiffness_scan_calls_a_slow_system_non_stiff():
    result = _ok("stiffness_scan", system=["y' = -y"], initial_values=[1.0],
                 t_span=[0.0, 5.0])
    assert result["metadata"]["verdict"] in {"non-stiff", "mildly stiff"}


def test_blow_up_is_bounded_and_silent(capfd):
    """A trajectory that leaves the reals must fail fast, and quietly.

    This guards the integrator choice: LSODA printed `capi_return is NULL` to
    stderr and swallowed the real reason when its Python callback raised.
    """
    result = run_skill("stiffness_scan", {
        "system": ["y' = y**2"], "initial_values": [1.0], "t_span": [0.0, 5.0], "points": 20})
    assert result["status"] == "failed"
    assert "could not be integrated" in result["message"]
    assert result["t"] == []
    captured = capfd.readouterr()
    assert "capi_return" not in captured.err


def test_blow_up_sensitivity_fails_cleanly():
    result = run_skill("sensitivity_analysis", {
        "system": ["y' = y**2"], "initial_values": [1.0], "t_span": [0.0, 10.0], "points": 20})
    assert result["status"] == "failed"
    assert "could not be integrated" in result["message"]


def test_every_skill_answers_or_explains_itself():
    """No skill may raise: an unusable input becomes a failed payload."""
    probes = {
        "riccati_reduction": {}, "power_series": {}, "frobenius": {},
        "equilibria_stability": {}, "lyapunov_spectrum": {},
        "bifurcation_sweep": {}, "sensitivity_analysis": {}, "stiffness_scan": {},
    }
    for skill_id, body in probes.items():
        result = run_skill(skill_id, body)
        assert result["status"] in {"success", "failed"}
        assert result["message"], skill_id


def test_unknown_skill_id_is_a_key_error():
    with pytest.raises(KeyError):
        run_skill("no-such-skill", {})


# ---------------------------------------------------------------------------
# HTTP surface
# ---------------------------------------------------------------------------
def test_skills_catalog_endpoint_is_free():
    res = client.get("/skills")
    assert res.status_code == 200
    data = res.json()
    assert data["count"] == 8
    assert {entry["id"] for entry in data["skills"]} == set(SKILL_IDS)


def test_skill_endpoint_runs_and_charges_tokens():
    res = client.post("/skills/equilibria_stability",
                      json={"system": ["y' = y^2 - 1"]})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["skill"] == "equilibria_stability"
    assert data["skill_name"]["fa"]
    assert data["entitlement"]["tokens_charged"] == data["entitlement"]["tokens_charged"]


def test_skill_endpoint_does_not_charge_for_a_failure():
    res = client.post("/skills/riccati_reduction", json={"equation": "y' = -2*y"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "failed"
    assert data["entitlement"]["tokens_charged"] == 0


def test_skill_endpoint_404s_for_an_unknown_id():
    res = client.post("/skills/nope", json={})
    assert res.status_code == 404


def test_skill_match_endpoint_suggests_a_skill():
    res = client.post("/skills/match", json={"text": "is this system chaotic?"})
    assert res.status_code == 200
    assert res.json()["matches"][0]["id"] == "lyapunov_spectrum"


def test_analyze_endpoint_suggests_a_skill_locally():
    res = client.post("/analyze", json={"text": "find the equilibria and their stability"})
    assert res.status_code == 200
    assert res.json()["data"]["skill"] == "equilibria_stability"


def test_free_form_solve_reports_a_skill_guess():
    res = client.post("/solve/equation", json={"equation": "y' = y^2 - t"})
    assert res.status_code == 200
    assert res.json()["kind"] == "symbolic"
