"""Independent solver API + interactive web UI.

Run with:  uvicorn api.main:app --host 0.0.0.0 --port 8000   (or: npm run api)
Open http://localhost:8000/ for the bilingual interactive solver.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from api.ai_provider import AIProviderError, analyze_equation
from api.local_intelligence import classify_equation
from api.solver_core import MODEL_NAMES, STIFF_MODELS, SolverRequest, adapter_metadata, solve_builtin, try_symbolic_first_order

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title="Differential Equation Intelligence API", version="0.2.0")

# The UI is served from the same origin; CORS additionally allows embedding the
# solver from docs or other frontends. Credentials are never used, so * is safe.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _sanitize(value: Any) -> Any:
    """Make arbitrary solver output strict-JSON-safe (browsers reject Infinity/NaN)."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: _sanitize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(v) for v in value]
    return value


class SolveBody(BaseModel):
    model: str = Field(default="system_nonlinear")
    variables: list[str] = Field(min_length=1, max_length=64)
    t_span: tuple[float, float]
    initial_values: list[float]
    parameters: dict[str, float] = Field(default_factory=dict)
    method: Literal["RK45", "BDF", "Radau", "LSODA"] = "RK45"
    rtol: float = Field(default=1e-7, ge=1e-12, le=1e-2)
    atol: float = Field(default=1e-9, ge=1e-14, le=1e-2)
    points: int = Field(default=200, ge=2, le=20_000)


class SymbolicBody(BaseModel):
    equation: str = Field(min_length=1, max_length=2_000)
    variable: str = "y"
    independent: str = "t"


class AnalyzeBody(BaseModel):
    text: str = Field(min_length=1, max_length=10_000)
    language: Literal["en", "fa"] = "en"


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/health")
def health() -> dict[str, object]:
    return {"status": "ok", "solver": "sympy-scipy", "models": len(MODEL_NAMES)}


@app.get("/models")
def models() -> dict[str, object]:
    return {"count": len(MODEL_NAMES), "models": MODEL_NAMES, "adapters": adapter_metadata()}


@app.post("/solve")
def solve(body: SolveBody) -> dict[str, object]:
    if body.model not in MODEL_NAMES:
        raise HTTPException(400, "Unknown model adapter")
    if body.model in STIFF_MODELS and body.method == "RK45":
        method = "BDF"
    else:
        method = body.method
    request = SolverRequest(
        body.model, tuple(body.variables), body.t_span, tuple(body.initial_values),
        body.parameters, method, body.rtol, body.atol, body.points,
    )
    try:
        result = solve_builtin(request)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _sanitize(result.__dict__)


@app.post("/analyze")
def analyze(body: AnalyzeBody) -> dict[str, object]:
    local = classify_equation(body.text)
    local["language"] = body.language
    return {"status": "classified", "data": local, "executable": False, "provider": "local"}


@app.post("/analyze/enhanced")
def enhanced_analyze(body: AnalyzeBody) -> dict[str, object]:
    """Optional remote enhancement; core behavior remains local if unavailable."""
    try:
        result = analyze_equation(body.text, body.language)
    except (AIProviderError, ValueError):
        result = classify_equation(body.text)
        result["language"] = body.language
        return {"status": "classified", "data": result, "executable": False, "provider": "local-fallback"}
    if result.get("model") not in MODEL_NAMES:
        raise HTTPException(422, "AI selected an unsupported model")
    return {"status": "classified", "data": result, "executable": False, "provider": "external-enhancement"}


@app.post("/solve/symbolic")
def symbolic(body: SymbolicBody) -> dict[str, object]:
    result = try_symbolic_first_order(body.equation, body.variable, body.independent)
    if result is None:
        raise HTTPException(422, "No verified symbolic solution was found")
    return {"status": "success", "solution": result, "verified": False,
            "message": "Symbolic result requires numerical verification for the supplied conditions."}


# Static assets for the interactive UI (must be registered after API routes).
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
