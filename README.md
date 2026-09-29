# Differential Equation Intelligence

A bilingual (English / فارسی) differential-equation solving product with three layers:

1. **Interactive solver app** — a self-contained web UI (`web/`) served by the Python API. Pick one of the 42 model families or type a free-form first-order ODE, then read the verified solution: exact symbolic forms, eigenvalue lists, residual checks, solver metadata, and a plot. No build step, no external CDNs, no execution of user input.
2. **Independent solver API** — Python/FastAPI using SymPy for symbolic work and SciPy `solve_ivp` methods (`RK45`, `BDF`, `Radau`, `LSODA`) for stiff and non-stiff systems, plus finite-difference PDE solvers, boundary-value, eigenvalue, delay, and inverse-problem adapters.
3. **Mintlify documentation** — this shell documents the engine, the model catalog, and the result policy.

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

## Interactive solver app (bilingual UI)

The UI is static HTML/CSS/JS in `web/` and is served by the API itself:

```bash
npm install
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
npm run api          # uvicorn api.main:app on 0.0.0.0:8000
```

Open **http://localhost:8000** — the model catalog (all 42 families with sensible parameter presets), a free-form symbolic equation tab, English/Persian toggle with full RTL, plots, eigenvalue/symbolic displays, and residual + metadata readouts.

## Engine independence (the guarantee)

The solver engine is **fully standalone**. Solving a problem requires only:

- Python 3
- `numpy`, `scipy`, `sympy`

It does **not** need any of the following to work:

- an external AI provider or API key (no `eval`, no model-generated code)
- network access or internet connectivity
- the FastAPI server, the web UI, Mintlify, or any other process
- a database, queue, or cloud service

`api/solver_core.py` contains no network imports, no `os.environ` reads, and
no environment-variable requirements. `api/local_intelligence.py` classifies
input offline. The only code path that can touch the network is the **optional**
`POST /analyze/enhanced` endpoint, which automatically falls back to the local
classifier when no key is configured or the provider is unreachable — solving
never routes through it. `api/test_independence.py` locks this in: it blocks
all network I/O, removes every AI environment variable, and verifies that all
42 models still solve.

### Run the engine with no server at all

```bash
npm run solve -- --model lorenz --y0 1,1,1 --t0 0 --t1 5 --points 500
python3 -m api.cli --list-models
python3 -m api.cli --verify            # offline smoke test of all 42 models
python3 -m api.cli --symbolic "-2*y + sin(t)"
python3 -m api.cli --model system_stiff --y0 1,2 --method Radau
```

The CLI prints strict JSON to stdout and is scriptable; the FastAPI server is
only an optional presentation layer on top of this same engine.

## The app includes everything it needs

The product is a **single self-contained web app**: the bilingual UI (`web/`, zero
CDN dependencies), the 42-model engine (`api/solver_core.py`), and the FastAPI
server that serves both (`api/main.py`) ship together, with all third-party
libraries declared in `api/requirements.txt` (`numpy`, `scipy`, `sympy`,
`fastapi`, `uvicorn`, `pydantic`). Visitors of the deployed website install
nothing — they only need a browser.

How to run the whole product:

```bash
npm start             # ONE command: auto-provisions deps, then serves UI+API on 0.0.0.0:8000
# or
sh scripts/serve.sh   # same, without npm
```

`npm start` (and `npm run api`) call `scripts/serve.sh`, which creates `.venv`
and installs `requirements.txt` **automatically** when they are missing — you
never install anything by hand. `npm run setup` runs just the provisioning
step. To run the engine with no server at all:

```bash
npm run solve -- --model lorenz --y0 1,1,1 --t0 0 --t1 5 --points 500
```

### Deploy the whole app as one image (any host)

The repo includes a `Dockerfile` that bundles Python, the math libraries, the
engine, and the UI into one image — a host needs only Docker:

```bash
docker build -t diffeq-engine .
docker run -p 8000:8000 diffeq-engine     # → http://localhost:8000
```

### Interactive solver app (bilingual UI)

Open **http://localhost:8000** — the model catalog (all 42 families with sensible parameter presets), a free-form symbolic equation tab, English/Persian toggle with full RTL, plots, eigenvalue/symbolic displays, and residual + metadata readouts.

Useful scripts:

```bash
npm start             # ONE-command start: provision + serve (port 8000)
npm run setup         # create .venv and install all dependencies
npm run solve         # standalone CLI solver (no server)
npm run test:solver   # python solver tests
npm run test:all      # full python suite (solver + API/UI + independence + packaging)
npm run lint          # ruff over api/ (config in ruff.toml; needs requirements-dev.txt)
npm run dev           # Mintlify documentation preview on port 3000
npm run build         # Mintlify export (static docs build)
```

## Local documentation preview

```bash
npm run dev
```

The local solver and pattern classifier run independently in Python and do not require an external API. External AI is optional enhancement only, not a runtime dependency for built-in models.

`POST /solve` uses local allowlisted adapters. `POST /analyze` uses the offline classifier and always works without credentials. `POST /analyze/enhanced` optionally calls an OpenAI-compatible provider and falls back to the local classifier on failure. The solver does not depend on AI or any external API to compute deterministic built-in models — the same guarantee is exercised directly by `python3 -m api.cli`.

## Accounts, tokens & payments

The product is a monetized web app on top of the solver engine:

- **Accounts** — sign up and sign in with email **or username** (PBKDF2-hashed);
  there is no phone-number step anywhere. Sessions are SQLite-backed tokens in an
  HttpOnly cookie.
- **Fixed admin** — an admin account is seeded idempotently on startup from
  `ADMIN_USERNAME` / `ADMIN_PASSWORD` (the defaults live in `api/db.py` and are
  shown only in the operator's own environment, never in the docs). It signs in
  with username + password only, gets unlimited token access, and has full
  control over every account.
- **Tokens, not time** — token packs never expire. Each pack credits tokens that
  are spent per operation by difficulty: 1 token for the elementary ODE families
  up to 9 for inverse problems, 4 for a symbolic solve, 1 for local
  classification. Beyond the included 500 output points, each extra 1000 points
  costs 1 more token. New accounts get 50 signup tokens; anonymous visitors get a
  40-token trial session (10 symbolic solves) tied to their cookie.
- **Enforcement** — every gated call checks the balance server-side and returns
  HTTP `402` with `code: insufficient_tokens` and `upgrade_url: /pricing` when the
  balance cannot cover the operation. Admin accounts are unlimited.
- **Payment gateways** — ZarinPal (toman; sent as Rial/`IRR` by default, override
  with `ZARINPAL_CURRENCY=IRT`), IDPay (rial), and direct **USDT-TRC20** wallet
  payments. Gateways are only called with real credentials configured via
  environment variables; without them the endpoints return a clear 503 instead of
  failing silently.
- **Crypto flow** — the buyer sends USDT-TRC20 to the wallet address shown on the
  pricing page, submits the TXID, and the admin confirms the payment from the
  admin panel, which credits the pack's tokens (an order can be confirmed once).
- **Admin panel** (`/admin`) — dashboard stats (users, tokens outstanding/sold/
  spent, revenue by currency, pending orders), token adjustment and pack grants
  for **any** account, payment order review with crypto confirmation (Tronscan
  link), the token ledger, and site settings (USDT wallet address, per-model
  token prices).

### Privacy & access control

- Every `/api/admin/*` route answers `401` to anonymous visitors and `403` to
  signed-in non-admins — project data (accounts, balances, orders, revenue) is
  visible to the admin only. An account can only ever read its own user object,
  token history, and orders.
- Login is throttled in-process: after 8 failed attempts for the same
  identifier + client host within 5 minutes the API answers `429` until the
  window slides past, so the admin password cannot be guessed by brute force.
  A successful login clears the counter.
- Session cookies are `HttpOnly` and `SameSite=Lax`, and marked `Secure`
  automatically when the request arrives over HTTPS.
- No wildcard CORS: the API grants no cross-origin access, so third-party sites
  cannot script it.
- `.env`, `data/`, and `*.db` are git-ignored; the SQLite database is never
  served by the app (only `web/` is mounted as static files).
- Set `ADMIN_PASSWORD` (and optionally `ADMIN_USERNAME`) per deployment instead
  of relying on the built-in default, or rotate it from `/account` after signing
  in (`POST /api/account/password` requires the current password).

### Environment variables (secrets live in Settings → Environment, never in git)

| Variable | Purpose | Required? |
|---|---|---|
| `ZARINPAL_MERCHANT_ID` | ZarinPal merchant id | only for ZarinPal payments |
| `ZARINPAL_SANDBOX` | `1`/`true` to use the ZarinPal sandbox | optional |
| `IDPAY_API_KEY` | IDPay API key | only for IDPay payments |
| `IDPAY_SANDBOX` | `1`/`true` to send the IDPay sandbox header | optional |
| `ZARINPAL_CURRENCY` | `IRR` (default) or `IRT` — currency sent to ZarinPal | optional |
| `USDT_TRC20_WALLET` | Fallback USDT-TRC20 wallet (editable in admin settings) | only for crypto payments |
| `ADMIN_USERNAME` | Fixed admin username (default `admin`) | optional |
| `ADMIN_PASSWORD` | Admin password — set it per deployment instead of relying on the built-in default | recommended |
| `ADMIN_EMAIL` | Fixed admin email (default `admin@diffeq.local`) | optional |
| `DIFFEQ_DB` | Override the SQLite database path (default `data/app.db`) | optional |

### Getting into the admin panel

The admin account is seeded automatically on the first start, so it always
exists — but its password is never printed in the repository. Use either route:

```bash
# 1) sign in with the seeded admin username + password (see ADMIN_USERNAME /
#    ADMIN_PASSWORD, or the defaults in api/db.py), then open /admin
# 2) make your own account the admin, no password sharing needed:
python3 -m api.cli --list-users                    # find your account
python3 -m api.cli --promote you@example.com       # grant the admin role
python3 -m api.cli --set-password you@example.com  # reset a password
python3 -m api.cli --demote you@example.com        # take it back (last admin protected)
```

Once signed in, `/account` has a **change password** card — replace the seeded
default with one only you know. The admin account is unlimited: it never spends
tokens and never gets blocked.

### Quick start for the full product

```bash
npm start                 # provisions deps and serves UI + API on 0.0.0.0:8000
# open http://localhost:8000/          → write any equation and solve it
# open http://localhost:8000/auth      → sign in with email/username + password
# open http://localhost:8000/admin     → every account, token control, orders
# open http://localhost:8000/pricing   → buy a token pack (ZarinPal / IDPay / USDT-TRC20)
```

### Solving an equation in any notation

`POST /solve/equation` accepts the equation the way a human writes it and always
answers. Every response carries a `kind`; there is never a dead end:

| `kind` | The answer you get |
| --- | --- |
| `symbolic` | Closed form `y(t) = …`, sampled into a curve when it can be |
| `integral` | Exact, with the quadrature left unevaluated (`∫ …`) — evaluating it is exactly what makes `y' = sin(t)·y + t` expensive |
| `implicit` | The equation integrated once, e.g. the energy integral `∫ dy/√(2(F(y)+C₁)) = t + C₂` for `y'' = f(y)` |
| `series` | Taylor expansion of the solution at the start of the interval, with the numerical curve alongside |
| `algebraic` | No derivative in the input (`x^2 - 5x + 6 = 0` → roots, `y = x^2` → solved for `y`) |
| `numeric` | Verified SciPy integration (RK45 → BDF → Radau) with tolerances and residual |

Both the symbolic sweep and the numerical integration run under hard time,
memory, step-count and magnitude caps, so a singular equation such as
`y' = tan(y)` is reported as bounded instead of hanging the request.

```bash
python3 -m api.cli --equation "y'' + 2*y' + y = 0" --y0 1,0 --t1 5
```

```text
-2*y + sin(t)            bare right-hand side of y' = f(t, y)
y' = -2*y                prime notation
dy/dt = -2*y             Leibniz notation
y' + 2*y = 0             implicit form
2y' + y = 0              implicit multiplication
y'' + 2*y' + y = 0       second order
d^2y/dt^2 = -y           second-order Leibniz
y' = -2y, y(0) = 1       inline initial conditions
y′ = x² - y              unicode primes, superscripts, Persian digits
```

### Solver skills

The engine also exposes a registry of independently callable **skills**
(`api/skills.py`) — one named capability each, with a bilingual description, a
token price and a single entry point. `GET /skills` is free, so an agent can plan
before spending anything.

| Skill | What it does |
| --- | --- |
| `riccati_reduction` | `y' = a(t)y² + b(t)y + c(t)` → linear second order, so `y' = y² - t` returns the Airy closed form |
| `power_series` | series solution keeping `C1`/`C2` |
| `frobenius` | indicial equation + series at a regular singular point, including whether a logarithm is needed |
| `equilibria_stability` | every equilibrium of a first-order system with its Jacobian classification |
| `lyapunov_spectrum` | Benettin QR estimate of the full Lyapunov spectrum (Lorenz → `+0.85, 0, −14.5`) |
| `bifurcation_sweep` | equilibrium branch continued across a parameter, with the stability transitions flagged |
| `sensitivity_analysis` | variational equations for `∂y(t)/∂y(0)` and the amplification factor |
| `stiffness_scan` | stiffness ratio along a trajectory plus a method recommendation |

```bash
curl -s localhost:8000/skills | python3 -m json.tool | head
curl -s -X POST localhost:8000/skills/match -H 'content-type: application/json' \
  -d '{"text": "is this system chaotic?"}'
```

`POST /analyze` suggests a skill locally, and `POST /analyze/enhanced` passes the
whole catalog to the model in its prompt.

### Agent skills for coding assistants

Twelve third-party Agent Skills are vendored under `.agents/skills/` so any AI
coding agent working on this repository has curated guidance for the libraries
the engine is built on and the work it is likely to grow into: `sympy` and
`fluidsim` (exact solving and PDE simulation), `pymc`, `pymoo`,
`uncertainty-and-units` and `statsmodels` (inverse problems, optimisation and
uncertainty), `dask`, `optimize-for-gpu`, `modal` and `get-available-resources`
(scale and resource limits), and `matplotlib` plus `scientific-visualization`
(figures). They are documentation for agents, never imported by the running API.
Provenance, the reasoning per skill and what was left out are in
`.agents/README.md`; versions are pinned by hash in `skills-lock.json`.

## Required production configuration

The solver API will require provider-specific values configured through the environment manager, not committed to this repository. No AI key is required for local classification or deterministic solving. `AI_API_KEY` or `SAMBANOVA_API_KEY` is optional and only enables enhanced natural-language interpretation. Database/queue configuration is required only for persistent, distributed production jobs; the local engine runs without them.
