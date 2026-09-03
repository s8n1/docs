"""Independence guarantees for the solver engine.

These tests lock in the product contract: the engine must solve without any
external service, network access, environment variable, API key, or server
process. If a future change makes the core solver depend on any of those,
these tests fail on purpose.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import urllib.request
from pathlib import Path

import pytest

from api.local_intelligence import classify_equation
from api.solver_core import MODEL_NAMES, try_symbolic_first_order, verify_model_catalog

REPO_ROOT = Path(__file__).resolve().parent.parent
CORE_SOURCE = (Path(__file__).resolve().parent / "solver_core.py").read_text(encoding="utf-8")

#: Env vars that would connect an external provider. Solving must ignore them.
_AI_ENV_KEYS = ("AI_API_KEY", "SAMBANOVA_API_KEY", "OPENAI_API_KEY", "AI_BASE_URL", "AI_MODEL")


@pytest.fixture(autouse=True)
def _no_ai_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _AI_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_solver_core_source_has_no_network_or_env_dependencies() -> None:
    """The engine module must not import network clients or read env vars."""
    forbidden = [
        "urllib", "requests", "httpx", "aiohttp", "socket", "openai",
        "os.environ", "getenv", "API_KEY", "urlopen", "socket.socket",
        "http://", "https://",
    ]
    hits = [token for token in forbidden if token in CORE_SOURCE]
    assert not hits, f"solver_core.py references forbidden external dependencies: {hits}"


def test_all_42_models_solve_with_network_blocked_and_no_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every model must solve offline: network calls are forced to explode."""
    def _block(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network access attempted during offline solving")

    monkeypatch.setattr(urllib.request, "urlopen", _block)
    monkeypatch.setattr(socket, "socket", _block)
    monkeypatch.setattr(socket, "create_connection", _block)

    checks = verify_model_catalog()
    assert set(checks) == set(MODEL_NAMES), "catalog smoke test must cover all 42 models"
    failed = [name for name, ok in checks.items() if not ok]
    assert not failed, f"offline solve failed for: {failed}"


def test_classifier_and_symbolic_solving_are_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Local classification and free-form symbolic solving never go remote."""
    def _block(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network access attempted")

    monkeypatch.setattr(urllib.request, "urlopen", _block)
    monkeypatch.setattr(socket, "socket", _block)

    classified = classify_equation("van der pol oscillator with mu = 1")
    assert classified["model"] == "van_der_pol"
    assert classified["requires_external_api"] is False

    solution = try_symbolic_first_order("-y")
    assert solution is not None
    assert "exp" in solution or "C1" in solution


def test_standalone_cli_solves_without_server_and_without_keys() -> None:
    """python3 -m api.cli must solve directly, with no FastAPI process involved."""
    env = {k: v for k, v in os.environ.items() if k not in _AI_ENV_KEYS}
    proc = subprocess.run(
        [sys.executable, "-m", "api.cli", "--model", "logistic",
         "--y0", "1.0", "--t0", "0", "--t1", "3",
         "--param", "rate=2", "--param", "capacity=10", "--points", "100"],
        capture_output=True, text=True, timeout=120, cwd=REPO_ROOT, env=env,
    )
    assert proc.returncode == 0, f"CLI failed:\n{proc.stdout}\n{proc.stderr}"
    data = json.loads(proc.stdout)
    assert data["status"] == "success"
    assert data["model"] == "logistic"
    # Near carrying capacity K=10 at the end of the window.
    assert abs(data["final_state"][0] - 9.8) < 0.5


def test_standalone_cli_can_verify_all_models() -> None:
    env = {k: v for k, v in os.environ.items() if k not in _AI_ENV_KEYS}
    proc = subprocess.run(
        [sys.executable, "-m", "api.cli", "--verify"],
        capture_output=True, text=True, timeout=180, cwd=REPO_ROOT, env=env,
    )
    assert proc.returncode == 0, f"CLI verify failed:\n{proc.stdout}\n{proc.stderr}"
    data = json.loads(proc.stdout)
    assert data["passed"] == 42
    assert data["failed"] == 0


def test_standalone_cli_symbolic_without_server() -> None:
    env = {k: v for k, v in os.environ.items() if k not in _AI_ENV_KEYS}
    proc = subprocess.run(
        [sys.executable, "-m", "api.cli", "--symbolic", "-2*y + sin(t)"],
        capture_output=True, text=True, timeout=60, cwd=REPO_ROOT, env=env,
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data["status"] == "success"
    assert "C1" in data["solution"] or "exp" in data["solution"]


def test_cli_rejects_unknown_model_and_bad_parameters() -> None:
    env = {k: v for k, v in os.environ.items() if k not in _AI_ENV_KEYS}
    proc = subprocess.run(
        [sys.executable, "-m", "api.cli", "--model", "not_a_model"],
        capture_output=True, text=True, timeout=60, cwd=REPO_ROOT, env=env,
    )
    assert proc.returncode != 0
    proc2 = subprocess.run(
        [sys.executable, "-m", "api.cli", "--model", "logistic", "--param", "rate=notanumber"],
        capture_output=True, text=True, timeout=60, cwd=REPO_ROOT, env=env,
    )
    assert proc2.returncode != 0
