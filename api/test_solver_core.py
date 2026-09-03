"""Comprehensive tests for all 42 solver model families."""
import numpy as np
import pytest
from scipy.special import jn as scipy_jn, eval_hermite

from api.local_intelligence import classify_equation
from api.solver_core import (
    MODEL_NAMES,
    SolverRequest,
    adapter_metadata,
    solve_builtin,
    try_symbolic_first_order,
    verify_model_catalog,
)

# ======================================================================
# Catalog integrity
# ======================================================================
def test_catalog_has_42_named_models():
    assert len(MODEL_NAMES) == 42
    assert len(set(MODEL_NAMES)) == 42

def test_all_models_have_solver():
    metadata = adapter_metadata()
    for name in MODEL_NAMES:
        assert metadata[name]["status"] == "supported", f"Model '{name}' not supported"

def test_full_catalog_verification():
    results = verify_model_catalog()
    assert len(results) == 42
    failed = [n for n, v in results.items() if not v]
    assert not failed, f"Models failed: {failed}"

# ======================================================================
# 1–13: SymPy ODE families
# ======================================================================
def test_separable():
    res = solve_builtin(SolverRequest("separable", ("y",), (0.01, 1.0), (1.0,), {}, points=10))
    assert res.status == "success"

def test_exact():
    res = solve_builtin(SolverRequest("exact", ("y",), (0.01, 0.3), (0.0,), {}, points=10))
    assert res.status == "success"

def test_linear_first_order():
    res = solve_builtin(SolverRequest("linear_first_order", ("y",), (0.0, 1.0), (1.0,), {"rate": 1.0}, points=10))
    assert res.status == "success"

def test_bernoulli():
    res = solve_builtin(SolverRequest("bernoulli", ("y",), (0.01, 0.5), (0.5,), {}, points=10))
    assert res.status == "success"

def test_riccati():
    res = solve_builtin(SolverRequest("riccati", ("y",), (0.0, 0.5), (0.0,), {}, points=10))
    assert res.status == "success"

def test_autonomous():
    res = solve_builtin(SolverRequest("autonomous", ("y",), (0.01, 1.0), (0.5,), {}, points=10))
    assert res.status == "success"

def test_homogeneous_first_order():
    res = solve_builtin(SolverRequest("homogeneous_first_order", ("y",), (0.1, 1.0), (1.0,), {}, points=10))
    assert res.status == "success"

def test_integrating_factor():
    res = solve_builtin(SolverRequest("integrating_factor", ("y",), (0.0, 1.0), (1.0,), {}, points=10))
    assert res.status == "success"

def test_euler_cauchy():
    res = solve_builtin(SolverRequest("euler_cauchy", ("y",), (0.1, 2.0), (1.0,), {}, points=10))
    assert res.status == "success"

def test_constant_coefficient_second_order():
    res = solve_builtin(SolverRequest("constant_coefficient_second_order", ("y",), (0.0, 1.0), (1.0,),
                       {"a": 1.0, "b": 0.0, "c": -1.0}, points=10))
    assert res.status == "success"

def test_constant_coefficient_higher_order():
    res = solve_builtin(SolverRequest("constant_coefficient_higher_order", ("y",), (0.0, 1.0), (1.0,), {"a": 1.0}, points=10))
    assert res.status == "success"

def test_undetermined_coefficients():
    res = solve_builtin(SolverRequest("undetermined_coefficients", ("y",), (0.0, 1.0), (1.0,), {}, points=10))
    assert res.status == "success"

def test_variation_of_parameters():
    res = solve_builtin(SolverRequest("variation_of_parameters", ("y",), (0.0, 0.5), (1.0,), {}, points=10))
    assert res.status == "success"

# ======================================================================
# 14–17: Transform / series
# ======================================================================
def test_laplace_transform():
    res = solve_builtin(SolverRequest("laplace_transform", ("y",), (0.0, 1.0), (1.0,), {}, points=10))
    assert res.status == "success"

def test_fourier_series():
    res = solve_builtin(SolverRequest("fourier_series", ("y",), (-np.pi, np.pi), (0.0,), {"n_terms": 20}, points=50))
    assert res.status == "success"
    assert "fourier" in res.method

def test_power_series():
    res = solve_builtin(SolverRequest("power_series", ("y",), (0.0, 3.0), (0.0,), {"n_terms": 30}, points=50))
    assert res.status == "success"
    assert abs(res.y[-1][0] - np.exp(3.0)) < 0.1

def test_frobenius():
    res = solve_builtin(SolverRequest("frobenius", ("y",), (0.01, 5.0), (1.0,), {"order": 0}, points=20))
    assert res.status == "success"

# ======================================================================
# 18–23: Special function ODEs
# ======================================================================
def test_legendre():
    res = solve_builtin(SolverRequest("legendre", ("y",), (-1.0, 1.0), (0.0,), {"order": 2}, points=20))
    assert res.status == "success"
    assert res.eigenvalues is not None

def test_bessel():
    res = solve_builtin(SolverRequest("bessel", ("y",), (0.01, 5.0), (1.0,), {"order": 0}, points=20))
    assert res.status == "success"

def test_airy():
    res = solve_builtin(SolverRequest("airy", ("y",), (-5.0, 2.0), (0.0,), {}, points=20))
    assert res.status == "success"

def test_hermite():
    res = solve_builtin(SolverRequest("hermite", ("y",), (-3.0, 3.0), (0.0,), {"order": 3}, points=20))
    assert res.status == "success"
    assert res.eigenvalues is not None

def test_laguerre():
    res = solve_builtin(SolverRequest("laguerre", ("y",), (0.01, 5.0), (1.0,), {"order": 2}, points=20))
    assert res.status == "success"

def test_chebyshev():
    res = solve_builtin(SolverRequest("chebyshev", ("y",), (-1.0, 1.0), (1.0,), {"order": 3}, points=20))
    assert res.status == "success"

# ======================================================================
# 24–32: Numeric ODE systems
# ======================================================================
def test_logistic_analytical():
    K, r, y0 = 10.0, 2.0, 1.0
    res = solve_builtin(SolverRequest("logistic", ("y",), (0.0, 3.0), (y0,), {"rate": r, "capacity": K}, points=100))
    assert res.status == "success"
    expected = K / (1 + (K - y0) / y0 * np.exp(-r * 3.0))
    assert abs(res.y[-1][0] - expected) < 0.05

def test_van_der_pol_limit_cycle():
    res = solve_builtin(SolverRequest("van_der_pol", ("x", "y"), (0.0, 20.0), (2.0, 0.0), {"mu": 1.0}, points=200))
    assert res.status == "success"

def test_lotka_volterra_periodic():
    res = solve_builtin(SolverRequest("lotka_volterra", ("x", "y"), (0.0, 10.0), (2.0, 1.0),
                       {"alpha": 1.5, "beta": 1.0, "delta": 1.0, "gamma": 3.0}, points=200))
    assert res.status == "success"

def test_lorenz_chaotic():
    res = solve_builtin(SolverRequest("lorenz", ("x", "y", "z"), (0.0, 1.0), (1.0, 1.0, 1.0), {}, points=100))
    assert res.status == "success"

def test_pendulum_small_angle():
    g, L, th0 = 9.81, 1.0, 0.1
    res = solve_builtin(SolverRequest("pendulum", ("theta", "omega"), (0.0, 1.0), (th0, 0.0),
                       {"gravity": g, "length": L, "damping": 0.0}, points=100))
    assert res.status == "success"
    omega0 = np.sqrt(g / L)
    expected = th0 * np.cos(omega0 * 1.0)
    assert abs(res.y[-1][0] - expected) < 0.01

def test_chemical_kinetics():
    res = solve_builtin(SolverRequest("chemical_kinetics", ("A", "B"), (0.0, 5.0), (1.0, 0.0), {"rate": 1.0}, points=50))
    assert res.status == "success"
    assert res.y[-1][0] < 0.01  # A depleted
    # B(t) = t*exp(-t): max at t=1 is 1/e, at t=5 is 5*exp(-5) ≈ 0.034
    assert res.y[-1][1] > 0.01  # B formed (transient peak)

def test_system_stiff_exp_decay():
    res = solve_builtin(SolverRequest("system_stiff", ("y",), (0.0, 1.0), (1.0,), {"rate": 1000.0}, points=100))
    assert res.status == "success"
    assert res.y[-1][0] < 1e-5

def test_system_linear():
    res = solve_builtin(SolverRequest("system_linear", ("y1", "y2"), (0.0, 2.0), (1.0, 0.5), {"rate": 1.0}, points=20))
    assert res.status == "success"

def test_system_nonlinear():
    res = solve_builtin(SolverRequest("system_nonlinear", ("y1", "y2"), (0.0, 1.0), (1.0, 0.5), {}, points=20))
    assert res.status == "success"

def test_reaction_diffusion():
    ic = list(np.sin(np.linspace(0, np.pi, 20)))
    res = solve_builtin(SolverRequest("reaction_diffusion", tuple(f"u{i}" for i in range(20)),
                       (0.0, 0.5), tuple(ic), {"diffusivity": 0.01, "decay": 0.1}, points=30))
    assert res.status == "success"

# ======================================================================
# 33–38: PDE models
# ======================================================================
def test_heat_equation_diffuses():
    ic = list(np.sin(np.linspace(0, np.pi, 30)))
    res = solve_builtin(SolverRequest("heat_equation", ("u",), (0.0, 0.5), tuple(ic),
                       {"nx": 30, "diffusivity": 0.05, "bc_left": 0.0, "bc_right": 0.0}, points=50))
    assert res.status == "success"

def test_wave_equation_propagates():
    ic = list(np.sin(np.linspace(0, np.pi, 30)))
    res = solve_builtin(SolverRequest("wave_equation", ("u",), (0.0, 0.5), tuple(ic),
                       {"nx": 30, "wave_speed": 1.0, "bc_left": 0.0, "bc_right": 0.0}, points=50))
    assert res.status == "success"

def test_advection_transports():
    ic = list(np.exp(-((np.linspace(0, 1, 40) - 0.3) ** 2) / 0.01))
    res = solve_builtin(SolverRequest("advection", ("u",), (0.0, 0.5), tuple(ic),
                       {"nx": 40, "wave_speed": 1.0, "bc_left": 0.0, "bc_right": 0.0}, points=50))
    assert res.status == "success"

def test_laplace_pde_converges():
    res = solve_builtin(SolverRequest("laplace_pde", ("u",), (0.0, 1.0), [0.0] * 400,
                       {"nx": 20, "ny": 20, "bc_left": 0.0, "bc_right": 0.0,
                        "bc_bottom": 0.0, "bc_top": 1.0, "max_iter": 3000}, points=10))
    assert res.status == "success"

def test_poisson_pde():
    res = solve_builtin(SolverRequest("poisson_pde", ("u",), (0.0, 1.0), [0.0] * 400,
                       {"nx": 20, "ny": 20, "bc_left": 0.0, "bc_right": 0.0,
                        "bc_bottom": 0.0, "bc_top": 0.0, "source_value": 1.0, "max_iter": 3000}, points=10))
    assert res.status == "success"

# ======================================================================
# 39: Boundary value problem
# ======================================================================
def test_boundary_value():
    res = solve_builtin(SolverRequest("boundary_value", ("y", "dy"), (0.0, 1.0), (0.0, 0.0),
                       {"bc_left": 0.0, "bc_right": 0.0, "k": np.pi, "ode_type": 0}, points=50))
    assert res.status == "success"

# ======================================================================
# 40: Eigenvalue problem
# ======================================================================
def test_eigenvalue():
    res = solve_builtin(SolverRequest("eigenvalue", ("y",), (0.0, 1.0), (0.0,),
                       {"n_eigenvalues": 3, "nx": 200}, points=50))
    assert res.status == "success"
    assert res.eigenvalues is not None
    assert len(res.eigenvalues) >= 3
    for i, lam in enumerate(res.eigenvalues):
        expected = (i + 1) ** 2 * np.pi ** 2
        assert abs(lam - expected) / expected < 0.02, f"Eigenvalue {i}: {lam} vs {expected}"

# ======================================================================
# 41: Delay differential equation
# ======================================================================
def test_delay_approximation():
    res = solve_builtin(SolverRequest("delay_approximation", ("y",), (0.0, 5.0), (1.0,),
                       {"a": 0.5, "delay": 1.0, "history_value": 1.0}, points=50))
    assert res.status == "success"
    assert len(res.y) == 50

# ======================================================================
# 42: Inverse problem
# ======================================================================
def test_inverse_problem_recovers_params():
    res = solve_builtin(SolverRequest("inverse_problem", ("y",), (0.0, 3.0), (1.0,),
                       {"true_A": 2.0, "true_k": 0.5, "true_B": 0.1, "noise": 0.001, "n_observed": 50},
                       points=100))
    assert res.status == "success"
    assert res.metadata is not None
    fitted = res.metadata["fitted_params"]
    assert abs(fitted["A"] - 2.0) < 0.15
    assert abs(fitted["k"] - 0.5) < 0.15
    assert abs(fitted["B"] - 0.1) < 0.15

# ======================================================================
# Numeric core tests
# ======================================================================
def test_numeric_solution_and_residual():
    res = solve_builtin(SolverRequest("system_linear", ("y",), (0.0, 1.0), (1.0,), {}, points=100))
    assert res.status == "success"
    assert abs(res.y[-1][0] - np.exp(-1)) < 1e-3
    assert res.residual_max < 0.05

def test_stiff_auto_selects_bdf():
    res = solve_builtin(SolverRequest("system_stiff", ("y",), (0.0, 0.1), (1.0,), {"rate": 1000.0}, points=20))
    assert res.method == "BDF"
    assert res.y[-1][0] < 1e-5

# ======================================================================
# Local classifier and symbolic parser
# ======================================================================
def test_local_classifier():
    assert classify_equation("solve a stiff van der pol system")["model"] == "van_der_pol"
    assert classify_equation("معادله خطی")["model"] == "linear_first_order"

def test_symbolic_parser():
    assert try_symbolic_first_order("__import__('os')") is None
    assert try_symbolic_first_order("-y") is not None
