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
npm run dev           # Mintlify documentation preview on port 3000
npm run build         # Mintlify export (static docs build)
```

## Local documentation preview

```bash
npm run dev
```

The local solver and pattern classifier run independently in Python and do not require an external API. External AI is optional enhancement only, not a runtime dependency for built-in models.

`POST /solve` uses local allowlisted adapters. `POST /analyze` uses the offline classifier and always works without credentials. `POST /analyze/enhanced` optionally calls an OpenAI-compatible provider and falls back to the local classifier on failure. The solver does not depend on AI or any external API to compute deterministic built-in models — the same guarantee is exercised directly by `python3 -m api.cli`.

## Accounts, subscriptions & payments

The product is a monetized web app on top of the solver engine:

- **Accounts** — email/password sign-up and sign-in (PBKDF2-hashed), SQLite-backed
  sessions in an HttpOnly cookie. The first registered user becomes the **admin**.
- **Plans** — Free (5 solves/day, 500 points, premium models blocked) and Pro
  (monthly/yearly, 100–1000 solves/day, up to 20 000 points, all models). When a
  subscription lapses the account is **automatically restricted back to Free**
  — enforced server-side on every `/solve` call, not just in the UI.
- **Payment gateways** — ZarinPal (toman), IDPay (rial), and direct **USDT-TRC20**
  wallet payments. Gateways are only called with real credentials configured via
  environment variables; without them the endpoints return a clear 503 instead of
  failing silently.
- **Crypto flow** — the buyer sends USDT-TRC20 to the wallet address shown on the
  pricing page, submits the TXID, and the admin confirms the payment from the
  admin panel, which activates the subscription.
- **Admin panel** (`/admin`) — dashboard stats (users, active subscriptions,
  revenue by currency, solves today), user management (roles, ban, grant/extend
  subscriptions), payment order review with crypto confirmation, and site
  settings (USDT wallet address, premium-model block list).

### Environment variables (secrets live in Settings → Environment, never in git)

| Variable | Purpose | Required? |
|---|---|---|
| `ZARINPAL_MERCHANT_ID` | ZarinPal merchant id | only for ZarinPal payments |
| `ZARINPAL_SANDBOX` | `1`/`true` to use the ZarinPal sandbox | optional |
| `IDPAY_API_KEY` | IDPay API key | only for IDPay payments |
| `IDPAY_SANDBOX` | `1`/`true` to send the IDPay sandbox header | optional |
| `USDT_TRC20_WALLET` | Fallback USDT-TRC20 wallet (editable in admin settings) | only for crypto payments |
| `ADMIN_EMAIL` | (future) designated admin email — currently the first registered user is admin | optional |
| `DIFFEQ_DB` | Override the SQLite database path (default `data/app.db`) | optional |

### Quick start for the full product

```bash
npm start                 # provisions deps and serves UI + API on 0.0.0.0:8000
# open http://localhost:8000/auth      → register (first user becomes admin)
# open http://localhost:8000/admin     → admin panel
# open http://localhost:8000/pricing   → buy a plan (ZarinPal / IDPay / USDT-TRC20)
```

## Required production configuration

The solver API will require provider-specific values configured through the environment manager, not committed to this repository. No AI key is required for local classification or deterministic solving. `AI_API_KEY` or `SAMBANOVA_API_KEY` is optional and only enables enhanced natural-language interpretation. Database/queue configuration is required only for persistent, distributed production jobs; the local engine runs without them.
