# Differential Equation Intelligence

This repository currently contains the Mintlify documentation shell for a planned bilingual differential-equation solving product. The production product must execute equation solving in a separate, resource-limited API; documentation alone cannot solve user equations.

## Product contract

After a user submits an equation, the service should attempt to return:

1. A symbolic closed-form solution when one exists.
2. Otherwise a numerically validated solution with method, tolerances, initial/boundary conditions, and residual/error metrics.
3. If the problem cannot be solved reliably, a precise limitation and the furthest validated result—not generic instructions.

The system must never claim universal solvability. Nonlinear, chaotic, singular, ill-posed, and high-dimensional problems require numerical checks and may only have approximate solutions.

## Required architecture

- **Web client:** bilingual Persian/English input, equations in LaTeX or structured form, plots, steps, residuals, and downloadable results.
- **Independent solver API:** Python service using SymPy for symbolic work and SciPy `solve_ivp` methods (`BDF`, `Radau`, and `LSODA` where available) for stiff and non-stiff systems.
- **Safe execution:** parse into an allowlisted equation AST; never use `eval`, execute generated Python, or accept arbitrary user code. Enforce limits on dimensions, time span, steps, memory, CPU, and wall time.
- **AI reasoning layer:** normalize natural-language requests, classify them against the 42 supported model families, select a solver, and explain verified results. The AI is not the numerical authority; solver output and residual checks are.
- **Job storage/queue:** persist status and results separately from the docs site. Use a managed database and a background-job system for expensive solves.

## 42-model coverage

The final catalog should include tests and solver adapters for first-order ODEs, separable/exact/linear/Bernoulli/Riccati forms, higher-order constant-coefficient equations, Euler-Cauchy equations, systems of ODEs, stiff systems, boundary-value problems, eigenvalue problems, Laplace/Fourier forms, and representative nonlinear, PDE, and numerical families. Each family needs explicit assumptions, supported syntax, fallback behavior, and verification tests.

## Local documentation preview

```bash
npm install
npm run dev
```

The current `npm run build` command validates and exports the Mintlify documentation. The local solver and pattern classifier run independently in Python and do not require an external API. External AI is optional enhancement only, not a runtime dependency for built-in models.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest api/test_solver_core.py -q
.venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000
```

`POST /solve` uses local allowlisted adapters. `POST /analyze` uses the offline classifier and always works without credentials. `POST /analyze/enhanced` optionally calls an OpenAI-compatible provider and falls back to the local classifier on failure. The solver does not depend on AI or any external API to compute deterministic built-in models.

## Required production configuration

The solver API will require provider-specific values configured through the environment manager, not committed to this repository. No AI key is required for local classification or deterministic solving. `AI_API_KEY` or `SAMBANOVA_API_KEY` is optional and only enables enhanced natural-language interpretation. Database/queue configuration is required only for persistent, distributed production jobs; the local engine runs without them.
