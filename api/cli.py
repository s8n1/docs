"""Standalone solver CLI — the engine with no server, no network, no API keys.

The only things this needs are Python 3 and the three scientific libraries
(numpy, scipy, sympy). It does not import the FastAPI app, does not perform
network I/O, and does not read any environment variable.

Examples (run from the repository root):

    python3 -m api.cli --list-models
    python3 -m api.cli --model logistic --y0 1.0 --t0 0 --t1 3 \
        --param rate=2 --param capacity=10
    python3 -m api.cli --model system_stiff --y0 1,2 --method Radau --points 500
    python3 -m api.cli --symbolic "-2*y + sin(t)"
    python3 -m api.cli --verify
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from typing import Any

from api.solver_core import (
    MODEL_NAMES,
    SolverRequest,
    solve_builtin,
    try_symbolic_first_order,
    verify_model_catalog,
)


def _sanitize(value: Any) -> Any:
    """Make any value strict-JSON-safe (Infinity/NaN are not valid JSON)."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: _sanitize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(v) for v in value]
    return value


def _parse_floats(raw: str) -> list[float]:
    return [float(x) for x in raw.split(",") if x.strip() != ""]


def build_request(args: argparse.Namespace) -> SolverRequest:
    parameters: dict[str, float] = {}
    for item in args.param:
        if "=" not in item:
            raise ValueError(f"--param expects key=value, got: {item!r}")
        key, value = item.split("=", 1)
        try:
            parameters[key.strip()] = float(value)
        except ValueError as exc:
            raise ValueError(f"parameter {key!r} must be numeric") from exc
    if args.method not in ("RK45", "BDF", "Radau", "LSODA"):
        raise ValueError("--method must be one of RK45, BDF, Radau, LSODA")
    initial_values = _parse_floats(args.y0) if args.y0 else [1.0]
    variables = tuple(v.strip() for v in args.vars.split(",") if v.strip())
    if not variables:
        variables = tuple(f"y{i}" for i in range(len(initial_values)))
    if len(initial_values) == 1 and len(variables) > 1:
        initial_values = initial_values * len(variables)
    if args.t1 <= args.t0:
        raise ValueError("--t1 must be greater than --t0")
    return SolverRequest(
        model=args.model,
        variables=variables,
        t_span=(args.t0, args.t1),
        initial_values=tuple(initial_values),
        parameters=parameters,
        method=args.method,
        points=args.points,
    )


def _summarize_result(result: Any, full: bool) -> dict[str, Any]:
    data = _sanitize(result.__dict__)
    if full:
        return data
    # Compact summary: skip the raw trajectory unless --full was requested.
    summary = {k: v for k, v in data.items() if k not in ("t", "y")}
    if data.get("y"):
        import numpy as np  # noqa: PLC0415 - numpy is already a core dependency

        arr = np.asarray(data["y"], dtype=float)
        if arr.size:
            summary["final_state"] = [float(x) for x in arr[-1]]
            summary["min"] = float(np.min(arr)) if arr.size else None
            summary["max"] = float(np.max(arr)) if arr.size else None
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m api.cli",
        description="Standalone differential-equation solver (no server, no network, no keys).",
    )
    parser.add_argument("--model", default="logistic", help="one of the 42 model families")
    parser.add_argument("--vars", default="", help="comma-separated state variable names")
    parser.add_argument("--y0", default="", help="comma-separated initial values")
    parser.add_argument("--t0", type=float, default=0.0, help="start of time span")
    parser.add_argument("--t1", type=float, default=1.0, help="end of time span")
    parser.add_argument("--points", type=int, default=200, help="output points (2..50000)")
    parser.add_argument("--method", default="RK45", help="RK45 | BDF | Radau | LSODA")
    parser.add_argument("--param", action="append", default=[], metavar="k=v", help="repeatable parameter, e.g. --param rate=2")
    parser.add_argument("--symbolic", metavar="EXPR", help="solve y' = EXPR symbolically, e.g. '-2*y + sin(t)'")
    parser.add_argument("--list-models", action="store_true", help="print the 42 model families")
    parser.add_argument("--verify", action="store_true", help="run the offline smoke test for all 42 models")
    parser.add_argument("--full", action="store_true", help="include the full trajectory in the output")
    args = parser.parse_args(argv)

    try:
        if args.list_models:
            print(json.dumps({"count": len(MODEL_NAMES), "models": MODEL_NAMES}, indent=2))
            return 0
        if args.verify:
            checks = verify_model_catalog()
            ok = {k: v for k, v in checks.items() if v}
            bad = {k: v for k, v in checks.items() if not v}
            print(json.dumps({"passed": len(ok), "failed": len(bad), "checks": checks}, indent=2))
            return 0 if not bad else 1
        if args.symbolic:
            solution = try_symbolic_first_order(args.symbolic)
            if solution is None:
                print(json.dumps({"status": "failed", "solution": None}, indent=2))
                return 1
            print(json.dumps({"status": "success", "solution": solution}, indent=2))
            return 0
        request = build_request(args)
        result = solve_builtin(request)
        payload = _summarize_result(result, args.full)
        payload["model"] = request.model
        print(json.dumps(payload, indent=2))
        return 0 if result.status == "success" else 1
    except (ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
