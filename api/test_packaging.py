"""Guards for the "the app includes everything it needs" contract.

The product must run for a website visitor without them installing anything:
the UI must be served from the same app that runs the engine, every third-party
library must be declared so hosting/containers install it, and a one-command
runner (plus a container) must exist to start everything.
"""
from __future__ import annotations

from pathlib import Path

API_DIR = Path(__file__).resolve().parent
ROOT = API_DIR.parent
WEB_DIR = ROOT / "web"

_RUNTIME_DEPS = ("numpy", "scipy", "sympy", "fastapi", "uvicorn", "pydantic")


def test_requirements_declare_every_runtime_library() -> None:
    """numpy/scipy/sympy + server libs must be declared so nothing is missing."""
    text = (API_DIR / "requirements.txt").read_text(encoding="utf-8")
    assert "-r api/requirements.txt" in (ROOT / "requirements.txt").read_text(encoding="utf-8"), \
        "root requirements.txt must include api/requirements.txt"
    missing = [dep for dep in _RUNTIME_DEPS if not any(
        line.strip().startswith(dep) for line in text.splitlines()
    )]
    assert not missing, f"runtime dependencies missing from api/requirements.txt: {missing}"
    # Test-time libraries must also be declared so `pytest` works out of the box.
    for dep in ("pytest", "httpx"):
        assert any(line.strip().startswith(dep) for line in text.splitlines()), \
            f"test dependency {dep} must be declared"


def test_web_assets_load_nothing_external() -> None:
    """The browser UI must not fetch any external resource (no CDN, no fonts)."""
    for filename in ("index.html", "app.js", "style.css"):
        content = (WEB_DIR / filename).read_text(encoding="utf-8")
        # The only http literal is the SVG xmlns namespace inside the data-URI favicon,
        # which is not a network request. Strip it, then require zero URLs.
        content = content.replace("http://www.w3.org/2000/svg", "")
        for needle in ("src=\"http", "src='http", "href=\"http", "href='http",
                       "@import url(", "fetch('http", 'fetch("http'):
            assert needle not in content, f"{filename} references external resource: {needle}"


def test_single_command_runner_and_container_are_present() -> None:
    """One-command start + container packaging must exist and cover the runtime."""
    serve = (ROOT / "scripts" / "serve.sh").read_text(encoding="utf-8")
    assert "scripts/setup.sh" in serve
    assert "uvicorn api.main:app" in serve

    setup = (ROOT / "scripts" / "setup.sh").read_text(encoding="utf-8")
    assert "-r requirements.txt" in setup
    assert "numpy, scipy, sympy" in setup

    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "pip install --no-cache-dir -r requirements.txt" in dockerfile
    assert "api.main:app" in dockerfile
    assert "COPY api/" in dockerfile and "COPY web/" in dockerfile

    pkg = (ROOT / "package.json").read_text(encoding="utf-8")
    for script in ('"start"', '"api"', '"setup"', '"solve"'):
        assert script in pkg, f"package.json must define {script}"


def test_single_app_serves_ui_and_engine_together() -> None:
    """One process serves the UI and the engine — visitors need one URL."""
    import json

    from fastapi.testclient import TestClient

    from api.main import app

    client = TestClient(app)
    index = client.get("/")
    assert index.status_code == 200
    assert 'src="/static/app.js"' in index.text or 'href="/static/style.css"' in index.text
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/style.css").status_code == 200
    solve = client.post("/solve", json={
        "model": "logistic", "variables": ["y"], "t_span": [0.0, 3.0],
        "initial_values": [1.0], "parameters": {"rate": 2.0, "capacity": 10.0},
        "points": 50,
    })
    assert solve.status_code == 200
    assert json.loads(solve.text)["status"] == "success"
