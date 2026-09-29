# Agent skills for this repository

These are third-party **Agent Skills** (the open `SKILL.md` standard) installed so
that any AI coding agent working on the DiffEQ Engine — Cursor, Claude Code,
Codex, Amp, and friends — has accurate, curated guidance for the libraries this
engine is built on, the numerics it depends on, and the work it is likely to be
extended with. They are documentation, not application code: nothing in the
running API imports or executes them.

`api/skills.py` is a **different** thing: that is the product's own capability
registry, served to users over `GET /skills`. The files here are for the coding
agents that maintain this repository.

## What is installed

| Skill | Why it is here |
| --- | --- |
| `sympy` | The engine's exact solver *is* SymPy — `dsolve`, `classify_ode`, `lambdify`, hint selection. This is the reference for all of it, including the `O(...)`/`RootOf` traps the answer validator exists to catch. |
| `fluidsim` | Pseudospectral CFD for the PDE families (heat, wave, advection, Laplace/Poisson, reaction–diffusion) and the CFL, dealiasing and resource bounds they need. |
| `pymc` | Bayesian inference for the `inverse_problem` family: posterior distributions over parameters instead of a single fitted point, with real uncertainty. |
| `pymoo` | Multi-objective optimisation (NSGA-II/III, Pareto fronts, constraint handling) for parameter identification where fit quality and regularisation compete. |
| `uncertainty-and-units` | `pint` + `uncertainties`: dimensional checking of user input and GUM-style uncertainty budgets, Monte-Carlo propagation and correct significant figures in reported answers. |
| `statsmodels` | Diagnostics for solution and residual series — stationarity, autocorrelation, ARIMA — when a fitted model needs to be defended rather than just plotted. |
| `dask` | Parallel and out-of-core NumPy for parameter sweeps and large PDE grids that no longer fit the single-process memory budget the solver worker enforces. |
| `optimize-for-gpu` | The GPU path for heavy solves: CuPy/Numba-CUDA acceleration plus the verification step that keeps an accelerated answer trustworthy. |
| `modal` | Serverless cloud compute (including GPUs) for the long-running solves that would otherwise have to run in-process. |
| `get-available-resources` | Resource-aware planning — it maps directly onto this engine's hard limits (`RLIMIT_AS` memory cap, evaluation budget, timeouts) and tells an agent what a workload can actually afford. |
| `matplotlib` | Figure construction for the chart layer. |
| `scientific-visualization` | The auditing half of plotting: accessibility, uncertainty and missing-data displays, colour/contrast review, journal-grade export. |

Installed with [`skills`](https://skills.sh) into `.agents/skills/`, which is the
universal agent-skills location (`.agents/skills/<name>/SKILL.md`). The exact
version of each skill is pinned by hash in `skills-lock.json` at the repository
root.

## Provenance and licence

- Source: <https://github.com/K-Dense-AI/scientific-agent-skills> (MIT).
- Each `SKILL.md` carries its own frontmatter, including `license`,
  `skill-author` and `allowed-tools`. Licences of the vendored material are
  permissive: MIT, BSD-3-Clause and Apache-2.0.
- Skills ship instructions **and**, in some cases, helper scripts (for example
  `fluidsim/scripts/`, `get-available-resources/scripts/`, `matplotlib/scripts/`).
  Agents run with full permissions, so review anything under `scripts/` before
  executing it.

## Adding more skills

```bash
# list what the collection offers
npx -y skills@latest add K-Dense-AI/scientific-agent-skills -l

# install several (repeat -s per skill; never pass a comma-separated list)
npx -y skills@latest add K-Dense-AI/scientific-agent-skills \
  -s pymc -s pymoo -a amp -y --copy

# restore exactly what skills-lock.json pins
npx -y skills@latest experimental_install
```

`-a amp` is the agent whose directory *is* `.agents/skills`; `--copy` is
required so the files are real, not symlinks into the npm cache.

## What is deliberately not installed

The collection has 166 skills; the rest are biology, chemistry, medicine, drug
discovery, genomics and wet-lab automation, which have nothing to do with a
differential-equation engine. Three nearer neighbours were considered and left
out on purpose:

- `qutip` — quantum dynamics. Genuinely ODE/PDE-shaped (Lindblad master
  equations), but the 42-family catalogue has no quantum family yet. Worth
  revisiting the moment one is added.
- `scikit-learn`, `umap-learn`, `transformers`, `pytorch-lightning`,
  `stable-baselines3` — general ML; only useful here behind a surrogate-model
  feature that does not exist yet.
- `latex-posters`, `scientific-slides`, `scientific-writing` — authoring
  outputs for academics, not for this product.
