"""AI orchestration boundary.

The model may classify and explain a problem, but the numerical solver remains
the authority. No model output is executed as Python or SymPy code.
"""
from __future__ import annotations

import json
import os
from typing import Any
from urllib import request


class AIProviderError(RuntimeError):
    pass


def _config() -> tuple[str, str, str]:
    api_key = os.environ.get("AI_API_KEY") or os.environ.get("SAMBANOVA_API_KEY")
    base_url = os.environ.get("AI_BASE_URL", "https://api.sambanova.ai/v1")
    model = os.environ.get("AI_MODEL", "Meta-Llama-3.1-70B-Instruct")
    if not api_key:
        raise AIProviderError("AI_API_KEY is not configured")
    return api_key, base_url.rstrip("/"), model


def _skills_brief() -> str:
    """One-line-per-skill catalog for the prompt (imported lazily to avoid a cycle)."""
    from api.skills import skill_catalog

    return "; ".join(
        f"{entry['id']} ({entry['category']}): {entry['summary']['en']}"
        for entry in skill_catalog()
    )


def analyze_equation(user_text: str, language: str = "en") -> dict[str, Any]:
    """Ask an OpenAI-compatible provider for JSON metadata only.

    The response is treated as untrusted data and validated by callers before
    entering the allowlisted solver adapters.
    """
    if not 1 <= len(user_text) <= 10_000:
        raise ValueError("equation text must be between 1 and 10000 characters")
    api_key, base_url, model = _config()
    payload = {
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": (
                "Return JSON only with keys model, skill, variables, parameters, "
                "initial_values, t_span, and explanation. Never return code. "
                "Choose 'model' only from the supported model catalog. "
                "Choose 'skill' only from this catalog, or null when none fits: "
                + _skills_brief()
            )},
            {"role": "user", "content": json.dumps({"language": language, "text": user_text})},
        ],
    }
    req = request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=30) as response:
            body = json.loads(response.read().decode())
        content = body["choices"][0]["message"]["content"]
        parsed = json.loads(content)
    except Exception as exc:
        raise AIProviderError("AI provider request failed") from exc
    if not isinstance(parsed, dict) or "model" not in parsed:
        raise AIProviderError("AI provider returned an invalid structured response")
    return parsed
