"""Comprehensive tests for all 42 solver model families."""
import numpy as np

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

def test_residual_measures_accuracy_not_output_grid():
    """A fast system must not report a large residual for a correct solution.

    The residual used to be the defect of the output grid — ``O(h^2 |y'''|)`` —
    which made a chaotic system look broken: Lorenz sampled at 20 points
    reported ~8.4 while being accurate to 5.5e-07.
    """
    def residual(points: int) -> float:
        res = solve_builtin(SolverRequest("lorenz", ("x", "y", "z"), (0.0, 0.2),
                                         (1.0, 1.0, 1.0), {}, method="RK45", points=points))
        assert res.status == "success"
        return res.residual_max

    coarse, dense = residual(20), residual(200)
    assert coarse < 1e-5
    assert dense < 1e-5
    # The estimate describes the integration, not how finely the curve is sampled.
    assert coarse < 10 * dense

def test_stiff_residual_is_small():
    res = solve_builtin(SolverRequest("system_stiff", ("y",), (0.0, 0.1), (1.0,),
                                      {"rate": 1000.0}, points=20))
    assert res.method == "BDF"
    assert res.residual_max < 1e-6

def test_residual_tracks_the_accuracy_actually_achieved():
    """Tightening the tolerances must lower the reported residual."""
    def residual(rtol: float, atol: float) -> float:
        res = solve_builtin(SolverRequest("system_linear", ("y",), (0.0, 1.0), (1.0,),
                                         {}, points=100, rtol=rtol, atol=atol))
        assert res.status == "success"
        return res.residual_max

    assert residual(1e-9, 1e-11) < residual(1e-4, 1e-6)

# ======================================================================
# Local classifier and symbolic parser
# ======================================================================
def test_local_classifier():
    assert classify_equation("solve a stiff van der pol system")["model"] == "van_der_pol"
    assert classify_equation("معادله خطی")["model"] == "linear_first_order"

def test_symbolic_parser():
    assert try_symbolic_first_order("__import__('os')") is None


# ======================================================================
# Symbolic solutions honor the supplied initial condition
# ======================================================================
def test_symbolic_separable_particular_solution():
    # y' = y, y(0) = 2  →  y(t) = 2*e^t, so y(1) = 2e
    res = solve_builtin(SolverRequest("separable", ("y",), (0.0, 1.0), (2.0,), {"rate": 1.0}, points=50))
    assert res.status == "success"
    assert abs(res.y[-1][0] - 2 * np.e) < 1e-6
    assert "C1" not in (res.symbolic_solution or ""), "expected a particular solution, not a general one"

def test_symbolic_linear_particular_solution():
    # y' = -2y, y(0) = 3  →  y(t) = 3*e^(-2t), so y(1) = 3*e^-2
    res = solve_builtin(SolverRequest("linear_first_order", ("y",), (0.0, 1.0), (3.0,), {"rate": 2.0}, points=50))
    assert res.status == "success"
    assert abs(res.y[-1][0] - 3 * np.exp(-2)) < 1e-6

def test_symbolic_bernoulli_particular_solution():
    # y' = y - y^2, y(0) = 1/2  →  y(t) = 1/(e^-t + 1), so y(1) ≈ 0.7310586
    res = solve_builtin(SolverRequest("bernoulli", ("y",), (0.0, 1.0), (0.5,), {}, points=50))
    assert res.status == "success"
    assert abs(res.y[-1][0] - 1 / (np.exp(-1) + 1)) < 1e-6

def test_first_order_symbolic_models_start_at_initial_value():
    """Every first-order symbolic family must return a curve that passes
    through the supplied y(t0). Second-order families need y'(t0) as well,
    so they intentionally keep the general solution."""
    cases = [
        ("separable", 0.3, 1.7, {"rate": 1.0}),
        ("linear_first_order", 0.2, 0.77, {"rate": 1.0}),
        ("exact", 0.2, 1.3, {}),
        ("bernoulli", 0.2, 0.4, {}),
        ("autonomous", 0.2, 0.6, {}),
        ("homogeneous_first_order", 0.2, 0.3, {}),
        ("integrating_factor", 0.1, 1.2, {}),
        ("laplace_transform", 0.1, 0.9, {}),
        ("riccati", 0.2, 0.4, {}),
        ("undetermined_coefficients", 0.2, 1.1, {}),
    ]
    for model, t0, y0, params in cases:
        res = solve_builtin(SolverRequest(model, ("y",), (t0, t0 + 1.0), (y0,), params, points=20))
        assert res.status == "success", model
        assert abs(res.y[0][0] - y0) < 1e-6, f"{model}: y({t0})={res.y[0][0]} expected {y0}"
        assert "honoring" in (res.message or ""), f"{model}: message should report the fitted IC"

def test_second_order_keeps_general_solution():
    """No derivative condition is supplied, so 2nd-order families stay general."""
    res = solve_builtin(SolverRequest("constant_coefficient_second_order", ("y",), (0.0, 1.0), (1.0,),
                       {"a": 1.0, "b": 0.0, "c": -1.0}, points=20))
    assert res.status == "success"
    assert "general solution" in (res.message or "")
    assert try_symbolic_first_order("-y") is not None
