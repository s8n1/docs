"""Independent solver API. Run with: uvicorn api.main:app --host 0.0.0.0 --port 8000"""
from __future__ import annotations

from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from api.ai_provider import AIProviderError, analyze_equation
from api.local_intelligence import classify_equation
from api.solver_core import MODEL_NAMES, STIFF_MODELS, SolverRequest, adapter_metadata, solve_builtin, try_symbolic_first_order

app = FastAPI(title="Differential Equation Intelligence API", version="0.1.0")

class SolveBody(BaseModel):
    model: str = Field(default="system_nonlinear")
    variables: list[str] = Field(min_length=1, max_length=32)
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
    request = SolverRequest(body.model, tuple(body.variables), body.t_span, tuple(body.initial_values), body.parameters, method, body.rtol, body.atol, body.points)
    try:
        result = solve_builtin(request)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return result.__dict__

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
    return {"status": "success", "solution": result, "verified": False, "message": "Symbolic result requires numerical verification for the supplied conditions."}
