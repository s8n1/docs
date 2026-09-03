"""Smoke tests for the FastAPI layer and the served interactive UI."""
import json

import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_health_reports_42_models():
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["models"] == 42


def test_models_metadata():
    res = client.get("/models")
    assert res.status_code == 200
    data = res.json()
    assert data["count"] == 42
    adapters = data["adapters"]
    assert all(adapters[name]["status"] == "supported" for name in data["models"])


def test_index_serves_interactive_ui():
    res = client.get("/")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "DiffEQ" in res.text


def test_static_assets_served():
    js = client.get("/static/app.js")
    assert js.status_code == 200
    assert "MODEL_DEFS" in js.text
    css = client.get("/static/style.css")
    assert css.status_code == 200
    assert ".lang-toggle" in css.text


def test_solve_logistic_returns_strict_json():
    body = {
        "model": "logistic",
        "variables": ["y"],
        "t_span": [0.0, 3.0],
        "initial_values": [1.0],
        "parameters": {"rate": 2.0, "capacity": 10.0},
        "method": "RK45",
        "points": 100,
    }
    res = client.post("/solve", json=body)
    assert res.status_code == 200
    # strict JSON: must not contain Infinity/NaN tokens that break browsers
    parsed = json.loads(res.text)
    assert parsed["status"] == "success"
    assert parsed["method"] in {"RK45", "BDF", "LSODA", "Radau"}
    assert abs(parsed["y"][-1][0] - 9.8) < 0.5  # near carrying capacity K=10
    assert parsed["residual_max"] is None or isinstance(parsed["residual_max"], float)


def test_solve_unknown_model_is_rejected():
    body = {
        "model": "not_a_model",
        "variables": ["y"],
        "t_span": [0.0, 1.0],
        "initial_values": [1.0],
        "points": 10,
    }
    res = client.post("/solve", json=body)
    assert res.status_code == 400


def test_solve_rejects_unsafe_input():
    body = {
        "model": "system_nonlinear",
        "variables": ["y", "y2"],
        "t_span": [1.0, 0.0],  # decreasing span → invalid
        "initial_values": [1.0, 0.5],
        "points": 10,
    }
    res = client.post("/solve", json=body)
    assert res.status_code == 422


def test_stiff_model_forces_bdf_method():
    body = {
        "model": "system_stiff",
        "variables": ["y"],
        "t_span": [0.0, 1.0],
        "initial_values": [1.0],
        "parameters": {"rate": 100.0},
        "method": "RK45",
        "points": 100,
    }
    res = client.post("/solve", json=body)
    assert res.status_code == 200
    data = res.json()
    assert data["method"] == "BDF"
    assert data["status"] == "success"


def test_analyze_local_classifier():
    res = client.post("/analyze", json={"text": "van der pol oscillator", "language": "en"})
    assert res.status_code == 200
    data = res.json()
    assert data["provider"] == "local"
    assert data["data"]["model"] == "van_der_pol"
    assert data["executable"] is False


def test_symbolic_endpoint():
    res = client.post("/solve/symbolic", json={"equation": "-y", "variable": "y", "independent": "t"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "exp" in data["solution"] or "C1" in data["solution"]


def test_symbolic_rejects_code_tokens():
    res = client.post("/solve/symbolic", json={"equation": "__import__('os').system('id')"})
    assert res.status_code == 422
