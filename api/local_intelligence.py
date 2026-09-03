"""Offline equation intelligence.

This module deliberately performs classification only. It never executes an
expression. Numerical work is delegated to explicit solver adapters.
"""
from __future__ import annotations

import re
from typing import Any

from api.solver_core import MODEL_NAMES

_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("logistic", ("logistic", "population growth", "رشد لجستیک")),
    ("van_der_pol", ("van der pol", "وان در پل")),
    ("lotka_volterra", ("lotka", "volterra", "شکارچی")),
    ("lorenz", ("lorenz", "لورنتس")),
    ("pendulum", ("pendulum", "آونگ")),
    ("chemical_kinetics", ("chemical", "kinetics", "سینتیک")),
    ("system_stiff", ("stiff", "سخت", "stiffness")),
    ("boundary_value", ("boundary", "مرزی")),
    ("separable", ("separable", "جداشدنی")),
    ("linear_first_order", ("linear", "خطی")),
)

_VARIABLE_RE = re.compile(r"\b([a-zA-Z])\b")


def classify_equation(text: str) -> dict[str, Any]:
    if not isinstance(text, str) or not 1 <= len(text) <= 10_000:
        raise ValueError("equation text must be between 1 and 10000 characters")
    lowered = text.casefold()
    selected = "system_nonlinear"
    for model, terms in _PATTERNS:
        if any(term.casefold() in lowered for term in terms):
            selected = model
            break
    variables = sorted(set(_VARIABLE_RE.findall(text)))
    if not variables:
        variables = ["y"]
    return {
        "model": selected if selected in MODEL_NAMES else "system_nonlinear",
        "variables": variables[:32],
        "parameters": {},
        "source": "local-pattern-classifier",
        "requires_external_api": False,
    }
