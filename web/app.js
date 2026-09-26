/* DiffEQ Engine — interactive solver UI (no build step, no eval, no external deps) */
"use strict";

/* ============================= i18n ============================= */
const I18N = {
  "brand-title": { en: "DiffEQ Engine", fa: "موتور دیف‌ایکیو" },
  "brand-sub": { en: "Symbolic + numerical differential equation solver · 42 model families", fa: "حل‌کنندهٔ نمادین و عددی معادلات دیفرانسیل · ۴۲ خانوادهٔ مدل" },
  "tabs-model": { en: "Model solver", fa: "حل‌گر مدلی" },
  "tabs-free": { en: "Free equation", fa: "معادلهٔ آزاد" },
  "cat-model-title": { en: "1 · Choose a model family", fa: "۱ · خانوادهٔ مدل را انتخاب کنید" },
  "cat-param-title": { en: "2 · Configure inputs", fa: "۲ · ورودی‌ها را تنظیم کنید" },
  search: { en: "Search models…", fa: "جست‌وجوی مدل‌ها…" },
  t0: { en: "t start (t₀)", fa: "آغاز بازه (t₀)" },
  t1: { en: "t end (t₁)", fa: "پایان بازه (t₁)" },
  profile: { en: "Initial spatial profile", fa: "پروفایل اولیهٔ فضایی" },
  "profile-sine": { en: "sine bump", fa: "برآمدگی سینوسی" },
  "profile-gauss": { en: "gaussian bump", fa: "برآمدگی گاوسی" },
  "profile-flat": { en: "constant", fa: "ثابت" },
  amplitude: { en: "Amplitude", fa: "دامنه" },
  "profile-hint": { en: "Spatial grid values are generated from the profile.", fa: "مقادیر شبکهٔ فضایی از روی پروفایل ساخته می‌شوند." },
  points: { en: "Output points", fa: "تعداد نقاط خروجی" },
  "btn-solve": { en: "⚡ Solve", fa: "⚡ حل کن" },
  "btn-example": { en: "Try an example", fa: "یک مثال امتحان کن" },
  "btn-symbolic": { en: "Solve symbolically", fa: "حل نمادین" },
  "btn-classify": { en: "Classify (local)", fa: "تشخیص نوع (محلی)" },
  "result-title": { en: "Solution", fa: "جواب" },
  "meta-title": { en: "Solver metadata", fa: "فرادادهٔ حل‌کننده" },
  "free-title": { en: "Solve a first-order ODE symbolically", fa: "حل نمادین معادلهٔ دیفرانسیل مرتبهٔ اول" },
  "free-hint": { en: "Write only the right-hand side f(t, y) of y′ = f(t, y).", fa: "فقط سمت راست f(t, y) معادلهٔ y′ = f(t, y) را بنویسید." },
  "about-title": { en: "Engine", fa: "موتور" },
  about1: { en: "SymPy for exact solutions of ODE families.", fa: "SymPy برای جواب‌های دقیق خانواده‌های ODE." },
  about2: { en: "SciPy RK45 / BDF / Radau / LSODA for numerical systems, with automatic BDF for stiff problems.", fa: "روش‌های عددی RK45 / BDF / Radau / LSODA با انتخاب خودکار BDF برای مسائل سخت." },
  about3: { en: "Finite-difference solvers for heat, wave, advection, Laplace and Poisson PDEs.", fa: "حل‌کننده‌های تفاضل محدود برای معادلات حرارت، موج، جابه‌جایی، لاپلاس و پواسون." },
  about4: { en: "Boundary value problems, Sturm–Liouville eigenvalues, delay equations, and inverse (curve-fit) problems.", fa: "مسائل مقدار مرزی، مقدارهای ویژهٔ استورم–لیوویل، معادلات تأخیری و مسائل معکوس." },
  about5: { en: "Every result carries a residual check and verification metadata. No user input is ever executed as code.", fa: "هر نتیجه با بررسی باقی‌مانده و فرادادهٔ اعتبارسنجی همراه است. هیچ ورودی کاربری هرگز به‌صورت کد اجرا نمی‌شود." },
  about6: { en: "Token packs never expire: each tool and model costs tokens by difficulty, and your balance is shown in the header.", fa: "پک‌های توکن منقضی نمی‌شوند: هزینهٔ هر ابزار و مدل بر اساس سختی از توکن‌های شما کم می‌شود و موجودی در سربرگ نمایش داده می‌شود." },
  "connecting": { en: "Connecting to the solver API…", fa: "در حال اتصال به API حل‌کننده…" },
  "cost-hint": { en: "Cost", fa: "هزینه" },
  "tokens": { en: "tokens", fa: "توکن" },
  "tokens-left": { en: "balance", fa: "موجودی" },
  "upgrade-tokens": { en: "Not enough tokens — top up to continue.", fa: "توکن کافی نیست — برای ادامه حساب خود را شارژ کنید." },
  "view-plans": { en: "View packs →", fa: "مشاهدهٔ پک‌ها ←" },
  "api-down": { en: "Solver API unreachable. Start it with: npm run api (port 8000).", fa: "API حل‌کننده در دسترس نیست. با دستور npm run api آن را اجرا کنید." },
  "free-sym-empty": { en: "Enter an equation first.", fa: "ابتدا یک معادله وارد کنید." },
  "free-class-title": { en: "Local classification", fa: "تشخیص محلی" },
  "stats-end": { en: "State at final step", fa: "مقدار متغیرها در پایان" },
  "stats-min": { en: "min", fa: "کمینه" },
  "stats-max": { en: "max", fa: "بیشینه" },
  "stats-final": { en: "final", fa: "پایانی" },
  "sol-symbolic": { en: "Exact (symbolic) solution", fa: "جواب دقیق (نمادین)" },
  "sol-eigen": { en: "Computed eigenvalues", fa: "مقدارهای ویژهٔ محاسبه‌شده" },
  "dim-msg": { en: "result", fa: "نتیجه" },
  "residual": { en: "residual", fa: "باقی‌مانده" },
  "method": { en: "method", fa: "روش" },
  "status": { en: "status", fa: "وضعیت" },
  "msg": { en: "message", fa: "پیام" },
  "eigen-val": { en: "λ", fa: "λ" },
  "plot-x": { en: "t", fa: "t" },
};

function tr(key) {
  const entry = I18N[key] || { en: key, fa: key };
  return entry[LANG] || entry.en;
}

let LANG = "en";

/* ============================= Model presets ============================= */
/* group keys: sym = symbolic ODE · num = numerical system · stiff · series · special · pde · grid-ode · bvp · eigen · delay · inverse */
const MODEL_DEFS = {
  /* --- symbolic first-order / classical ODE families --- */
  separable: { g: "sym", en: "Separable", fa: "جداپذیر", t0: 0.01, t1: 1.0 },
  exact: { g: "sym", en: "Exact", fa: "دقیق", t0: 0.01, t1: 1.0, y0: 1.0 },
  linear_first_order: { g: "sym", en: "Linear first-order", fa: "خطی مرتبهٔ اول", t0: 0, t1: 1.0, params: [["rate", "rate / نرخ", 1.0]] },
  bernoulli: { g: "sym", en: "Bernoulli", fa: "برنولی", t0: 0.01, t1: 1.0, y0: 0.5 },
  riccati: { g: "sym", en: "Riccati", fa: "ریکاتی", t0: 0, t1: 0.5, y0: 0 },
  autonomous: { g: "sym", en: "Autonomous", fa: "خودمختار", t0: 0.01, t1: 1.0, y0: 0.5 },
  homogeneous_first_order: { g: "sym", en: "Homogeneous first-order", fa: "همگن مرتبهٔ اول", t0: 0.1, t1: 1.0, y0: 0.1 },
  integrating_factor: { g: "sym", en: "Integrating factor", fa: "عامل انتگرال‌ساز", t0: 0, t1: 1.0 },
  euler_cauchy: { g: "sym", en: "Euler–Cauchy", fa: "اویلر–کوشی", t0: 0.1, t1: 2.0 },
  undetermined_coefficients: { g: "sym", en: "Undetermined coefficients", fa: "ضرایب نامعین", t0: 0, t1: 1.0 },
  variation_of_parameters: { g: "sym", en: "Variation of parameters", fa: "تغییر پارامترها", t0: 0, t1: 0.5 },
  laplace_transform: { g: "series", en: "Laplace transform", fa: "تبدیل لاپلاس", t0: 0, t1: 1.0 },
  /* --- constant coefficient higher-order --- */
  constant_coefficient_second_order: { g: "cc", en: "Constant coeff. (2nd order)", fa: "ضرایب ثابت (مرتبهٔ ۲)", t0: 0, t1: 1.0, params: [["a", "a", 1.0], ["b", "b", 0.0], ["c", "c", -1.0]] },
  constant_coefficient_higher_order: { g: "cc", en: "Constant coeff. (higher order)", fa: "ضرایب ثابت (مرتبهٔ بالا)", t0: 0, t1: 1.0, params: [["a", "a", 1.0]] },
  /* --- series / transforms --- */
  fourier_series: { g: "series", en: "Fourier series", fa: "سری فوریه", t0: -3.141592653589793, t1: 3.141592653589793, y0: 0, pts: 200, params: [["n_terms", "n terms", 20]] },
  power_series: { g: "series", en: "Power series", fa: "سری توانی", t0: 0, t1: 3.0, y0: 0, pts: 160, params: [["n_terms", "n terms", 30]] },
  frobenius: { g: "series", en: "Frobenius series", fa: "سری فروبنیوس", t0: 0.01, t1: 5.0, pts: 120, params: [["order", "order / مرتبه", 0]] },
  /* --- special function ODEs --- */
  legendre: { g: "special", en: "Legendre", fa: "لژاندر", t0: -1, t1: 1.0, y0: 0, pts: 160, params: [["order", "order / مرتبه", 2]] },
  bessel: { g: "special", en: "Bessel", fa: "بسل", t0: 0.01, t1: 5.0, pts: 160, params: [["order", "order / مرتبه", 0]] },
  airy: { g: "special", en: "Airy", fa: "ایری", t0: -5, t1: 2.0, y0: 0, pts: 200 },
  hermite: { g: "special", en: "Hermite", fa: "هرمیت", t0: -3, t1: 3.0, y0: 0, pts: 160, params: [["order", "order / مرتبه", 3]] },
  laguerre: { g: "special", en: "Laguerre", fa: "لاگر", t0: 0.01, t1: 5.0, pts: 160, params: [["order", "order / مرتبه", 2]] },
  chebyshev: { g: "special", en: "Chebyshev", fa: "چبیشف", t0: -1, t1: 1.0, pts: 160, params: [["order", "order / مرتبه", 3]] },
  /* --- numerical ODE systems --- */
  logistic: { g: "num", en: "Logistic growth", fa: "رشد لجستیک", vars: ["y"], y0: [1.0], t0: 0, t1: 3.0, params: [["rate", "rate / نرخ", 2.0], ["capacity", "K / ظرفیت", 10.0]] },
  van_der_pol: { g: "num", en: "Van der Pol oscillator", fa: "نوسان‌گر وان‌درپل", vars: ["x", "y"], y0: [2.0, 0.0], t0: 0, t1: 20.0, params: [["mu", "μ", 1.0]] },
  lotka_volterra: { g: "num", en: "Lotka–Volterra", fa: "لاتکا–وولترا", vars: ["x", "y"], y0: [2.0, 1.0], t0: 0, t1: 10.0, params: [["alpha", "α", 1.5], ["beta", "β", 1.0], ["delta", "δ", 1.0], ["gamma", "γ", 3.0]] },
  lorenz: { g: "num", en: "Lorenz attractor", fa: "جاذبهٔ لورنتس", vars: ["x", "y", "z"], y0: [1.0, 1.0, 1.0], t0: 0, t1: 5.0, params: [["sigma", "σ", 10.0], ["rho", "ρ", 28.0], ["beta", "β", 2.6666666666666665]] },
  pendulum: { g: "num", en: "Pendulum", fa: "آونگ", vars: ["theta", "omega"], y0: [0.1, 0.0], t0: 0, t1: 10.0, params: [["gravity", "g / شتاب گرانش", 9.81], ["length", "L / طول", 1.0], ["damping", "damping / میرایی", 0.0]] },
  system_linear: { g: "num", en: "Linear system", fa: "دستگاه خطی", vars: ["y1", "y2"], y0: [1.0, 0.5], t0: 0, t1: 2.0, params: [["rate", "rate / نرخ", 1.0]] },
  system_nonlinear: { g: "num", en: "Nonlinear system", fa: "دستگاه غیرخطی", vars: ["y1", "y2"], y0: [1.0, 0.5], t0: 0, t1: 2.0, params: [["rate", "rate / نرخ", 1.0], ["coupling", "coupling / جفت‌شدگی", 0.05]] },
  chemical_kinetics: { g: "stiff", en: "Chemical kinetics (stiff)", fa: "سینتیک شیمیایی (سخت)", vars: ["A", "B"], y0: [1.0, 0.0], t0: 0, t1: 5.0, params: [["rate", "rate / نرخ", 1.0]] },
  system_stiff: { g: "stiff", en: "Stiff decay system", fa: "دستگاه واپاشی سخت", vars: ["y"], y0: [1.0], t0: 0, t1: 1.0, params: [["rate", "rate / نرخ", 100.0]] },
  reaction_diffusion: { g: "gridnum", en: "Reaction–diffusion (1D grid)", fa: "واکنش–نفوذ (شبکهٔ ۱بعدی)", t0: 0, t1: 0.5, grid: true, params: [["nx", "n grid points", 20], ["diffusivity", "D / ضریب نفوذ", 0.02], ["decay", "decay / واپاشی", 0.2]] },
  /* --- PDE --- */
  heat_equation: { g: "pde", en: "Heat equation (1D)", fa: "معادلهٔ گرما (۱بعدی)", t0: 0, t1: 0.5, grid: true, params: [["nx", "n grid points", 30], ["diffusivity", "α / ضریب نفوذ گرمایی", 0.05], ["bc_left", "u(left)", 0.0], ["bc_right", "u(right)", 0.0]] },
  wave_equation: { g: "pde", en: "Wave equation (1D)", fa: "معادلهٔ موج (۱بعدی)", t0: 0, t1: 1.0, grid: true, params: [["nx", "n grid points", 30], ["wave_speed", "c / سرعت موج", 1.0], ["bc_left", "u(left)", 0.0], ["bc_right", "u(right)", 0.0]] },
  advection: { g: "pde", en: "Advection (1D)", fa: "جابه‌جایی (۱بعدی)", t0: 0, t1: 0.5, grid: true, profile: "gauss", params: [["nx", "n grid points", 40], ["wave_speed", "c / سرعت", 1.0], ["bc_left", "u(left)", 0.0], ["bc_right", "u(right)", 0.0]] },
  laplace_pde: { g: "pde", en: "Laplace equation (2D)", fa: "معادلهٔ لاپلاس (۲بعدی)", t0: 0, t1: 1.0, grid: true, zeroIC: true, pts: 10, params: [["nx", "nx", 20], ["ny", "ny", 20], ["bc_left", "u(left)", 0.0], ["bc_right", "u(right)", 0.0], ["bc_bottom", "u(bottom)", 0.0], ["bc_top", "u(top)", 1.0], ["max_iter", "max iterations", 5000]] },
  poisson_pde: { g: "pde", en: "Poisson equation (2D)", fa: "معادلهٔ پواسون (۲بعدی)", t0: 0, t1: 1.0, grid: true, zeroIC: true, pts: 10, params: [["nx", "nx", 20], ["ny", "ny", 20], ["bc_left", "u(left)", 0.0], ["bc_right", "u(right)", 0.0], ["bc_bottom", "u(bottom)", 0.0], ["bc_top", "u(top)", 0.0], ["source_value", "source f", 1.0], ["max_iter", "max iterations", 5000]] },
  /* --- special problem classes --- */
  boundary_value: { g: "bvp", en: "Boundary value problem", fa: "مسئلهٔ مقدار مرزی", vars: ["y", "y'"], y0: [0.0, 0.0], t0: 0, t1: 1.0, params: [["ode_type", "ode type", 0], ["k", "k", 1.5707963267948966], ["mesh_points", "mesh points", 20], ["bc_left", "y(a)", 0.0], ["bc_right", "y(b)", 1.0]] },
  eigenvalue: { g: "eigen", en: "Eigenvalue (Sturm–Liouville)", fa: "مقدار ویژه (استورم–لیوویل)", vars: ["y"], y0: [0.0], t0: 0, t1: 1.0, pts: 100, params: [["length", "L / طول", 1.0], ["nx", "n grid points", 200], ["n_eigenvalues", "count", 5]] },
  delay_approximation: { g: "delay", en: "Delay differential equation", fa: "معادلهٔ دیفرانسیل تأخیری", vars: ["y"], y0: [1.0], t0: 0, t1: 10.0, pts: 300, params: [["a", "a", 1.0], ["delay", "τ / تأخیر", 0.5], ["history_value", "history y₀", 1.0]] },
  inverse_problem: { g: "inverse", en: "Inverse problem (curve fit)", fa: "مسئلهٔ معکوس (برازش منحنی)", vars: ["obs"], y0: [0.0], t0: 0, t1: 5.0, params: [["true_A", "true A", 2.0], ["true_k", "true k", 0.5], ["true_B", "true B", 0.1], ["noise", "noise σ", 0.02], ["n_observed", "n observations", 20]] },
};

const GROUP_ORDER = [
  ["sym", { en: "Symbolic ODE families", fa: "خانواده‌های نمادین ODE" }],
  ["cc", { en: "Constant-coefficient ODE", fa: "ODE با ضرایب ثابت" }],
  ["series", { en: "Transforms & series", fa: "تبدیل‌ها و سری‌ها" }],
  ["special", { en: "Special functions", fa: "توابع ویژه" }],
  ["num", { en: "Numerical systems", fa: "سیستم‌های عددی" }],
  ["stiff", { en: "Stiff systems (BDF / Radau)", fa: "سیستم‌های سخت (BDF / Radau)" }],
  ["gridnum", { en: "Grid numerical systems", fa: "سیستم‌های شبکه‌ای" }],
  ["pde", { en: "Partial differential equations", fa: "معادلات با مشتقات جزئی (PDE)" }],
  ["bvp", { en: "Boundary value problem", fa: "مسئلهٔ مقدار مرزی" }],
  ["eigen", { en: "Eigenvalue problem", fa: "مسئلهٔ مقدار ویژه" }],
  ["delay", { en: "Delay equation", fa: "معادلهٔ تأخیری" }],
  ["inverse", { en: "Inverse problem", fa: "مسئلهٔ معکوس" }],
];

const PALETTE = ["#38e1b4", "#4da3ff", "#ffb454", "#ff6b6b", "#c792ea", "#ffd166", "#6cffd9", "#8be9fd"];

/* ============================= DOM helpers ============================= */
const $ = (id) => document.getElementById(id);
const el = (tag, cls, text) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
};

let currentModel = "logistic";
let modelNames = Object.keys(MODEL_DEFS);
let TOKEN_COSTS = {};
let MY_ENTITLEMENT = null;
let exampleIdx = 0;
const EXAMPLE_CYCLE = ["logistic", "van_der_pol", "lorenz", "pendulum", "heat_equation", "eigenvalue", "boundary_value", "inverse_problem"];

function fmtInt(n) {
  if (n === null || n === undefined) return "∞";
  try { return Number(n).toLocaleString(LANG === "fa" ? "fa-IR" : "en-US"); }
  catch (_) { return String(n); }
}

function fmt(x, digits = 5) {
  if (x === null || x === undefined) return "—";
  if (typeof x !== "number" || !isFinite(x)) return x === Infinity ? "∞" : String(x);
  const a = Math.abs(x);
  if (a !== 0 && (a >= 1e6 || a < 1e-4)) return x.toExponential(3);
  return String(parseFloat(x.toFixed(digits)));
}

function readNum(input, fallback) {
  const v = parseFloat(input.value);
  return isFinite(v) ? v : fallback;
}

/* ============================= Catalog / config UI ============================= */
function buildModelOptions() {
  const sel = $("model-select");
  sel.innerHTML = "";
  const q = $("model-search").value.trim().toLowerCase();
  for (const [gid, gname] of GROUP_ORDER) {
    const names = modelNames.filter((n) => MODEL_DEFS[n].g === gid);
    if (!names.length) continue;
    const opts = names.filter((n) => {
      if (!q) return true;
      const d = MODEL_DEFS[n];
      return (d.en + " " + d.fa + " " + n).toLowerCase().includes(q);
    });
    if (!opts.length) continue;
    const group = el("optgroup");
    group.label = gname[LANG];
    for (const n of opts) {
      const d = MODEL_DEFS[n];
      const o = el("option");
      o.value = n;
      const cost = TOKEN_COSTS[n];
      o.textContent = `${LANG === "fa" ? d.fa : d.en}  (${n})${cost ? ` — ${cost} ${tr("tokens")}` : ""}`;
      group.appendChild(o);
    }
    sel.appendChild(group);
  }
}

function paramsOf(def) {
  return (def.params || []).map(([k, label, dv]) => ({ k, label, dv }));
}

function buildConfigUI() {
  const def = MODEL_DEFS[currentModel];
  const vars = def.vars || ["y"];
  const y0 = def.y0 || (def.y0 === 0 ? [0] : vars.map(() => 1.0));

  /* initial conditions */
  const icGrid = $("ic-grid");
  icGrid.innerHTML = "";
  if (!def.grid) {
    const head = el("div", "hint");
    head.textContent = LANG === "fa" ? "شرایط اولیهٔ متغیرهای حالت:" : "Initial values for the state variables:";
    icGrid.appendChild(head);
    vars.forEach((v, i) => {
      const lab = el("label", "field");
      const span = el("span", "lbl");
      span.textContent = `${v}(t₀)`;
      const inp = el("input");
      inp.type = "number";
      inp.step = "any";
      inp.value = String(y0[i] ?? 1);
      inp.dataset.ic = String(i);
      lab.appendChild(span);
      lab.appendChild(inp);
      icGrid.appendChild(lab);
    });
  }

  /* parameters */
  const pGrid = $("param-grid");
  pGrid.innerHTML = "";
  const headP = el("div", "hint");
  headP.textContent = LANG === "fa" ? "پارامترهای معادله:" : "Equation parameters:";
  pGrid.appendChild(headP);
  for (const { k, label, dv } of paramsOf(def)) {
    const lab = el("label", "field");
    const span = el("span", "lbl");
    span.textContent = label;
    const inp = el("input");
    inp.type = "number";
    inp.step = "any";
    inp.value = String(dv);
    inp.dataset.param = k;
    lab.appendChild(span);
    lab.appendChild(inp);
    pGrid.appendChild(lab);
  }

  /* span / method / points */
  $("p-t0").value = String(def.t0 ?? 0);
  $("p-t1").value = String(def.t1 ?? 1);
  $("p-points").value = String(def.pts || 200);
  $("p-rtol").value = "1e-7";
  $("p-method").value = "auto";

  /* grid profile section */
  $("grid-profile").classList.toggle("hidden", !def.grid);
  if (def.grid) {
    const prof = def.profile || "sine";
    $("p-profile").value = prof;
    $("p-amplitude").value = String(def.zeroIC ? 0 : 1);
    if (def.zeroIC) {
      $("p-profile").value = "flat";
      $("p-profile").disabled = true;
    } else {
      $("p-profile").disabled = false;
    }
  }

  describeModel(def);
}

function describeModel(def) {
  const box = $("model-desc");
  box.innerHTML = "";
  const kindText = GROUP_ORDER.find(([g]) => g === def.g)[1][LANG];
  const b = el("span");
  b.textContent = `« ${LANG === "fa" ? def.fa : def.en} » · ${kindText} · `;
  box.appendChild(b);
  const code = el("code");
  code.textContent = currentModel;
  box.appendChild(code);
  const cost = TOKEN_COSTS[currentModel];
  if (cost) {
    const c = el("span");
    c.textContent = ` · ${tr("cost-hint")}: ${cost} ${tr("tokens")}`;
    box.appendChild(c);
  }
}

function currentCost() {
  const base = TOKEN_COSTS[currentModel] || 2;
  const points = Math.min(2000, Math.max(2, Math.round(readNum($("p-points"), 200))));
  return base + Math.max(0, Math.floor((points - 500) / 1000));
}

function updateCostHint() {
  const box = $("cost-hint");
  if (!box) return;
  let text = `${tr("cost-hint")}: ${currentCost()} ${tr("tokens")}`;
  if (MY_ENTITLEMENT) {
    const balance = MY_ENTITLEMENT.unlimited ? null : MY_ENTITLEMENT.tokens;
    text += ` · ${tr("tokens-left")}: ${balance === null ? "∞" : fmtInt(balance)}`;
  }
  box.textContent = text;
}

function selectModel(name) {
  if (!MODEL_DEFS[name]) return;
  currentModel = name;
  buildConfigUI();
  updateCostHint();
}

function readConfig() {
  const def = MODEL_DEFS[currentModel];
  const params = {};
  document.querySelectorAll("#param-grid input[data-param]").forEach((inp) => {
    params[inp.dataset.param] = readNum(inp, NaN);
  });

  let vars, ic;
  if (def.grid) {
    const nx = nxOf(def, params);
    ic = genProfile(def, params, nx);
    /* PDE solvers accept a single state name; grid ODEs need one name per node */
    vars = def.g === "gridnum" ? ic.map((_, i) => `u${i}`) : ["u"];
  } else {
    vars = def.vars || ["y"];
    ic = [];
    document.querySelectorAll("#ic-grid input[data-ic]").forEach((inp) => {
      ic.push(readNum(inp, 1));
    });
  }

  return {
    model: currentModel,
    variables: vars,
    t_span: [readNum($("p-t0"), 0), readNum($("p-t1"), 1)],
    initial_values: ic,
    parameters: params,
    method: $("p-method").value === "auto" ? "RK45" : $("p-method").value,
    rtol: readNum($("p-rtol"), 1e-7),
    atol: 1e-9,
    points: Math.min(2000, Math.max(2, Math.round(readNum($("p-points"), 200)))),
  };
}

function nxOf(def, params) {
  const raw = params.nx != null ? Math.round(params.nx) : 10;
  const cap = def.g === "gridnum" ? 60 : 200; /* backend caps state dims at 64 */
  return Math.max(2, Math.min(cap, raw));
}

function genProfile(def, params, nx) {
  const amp = readNum($("p-amplitude"), 1);
  const kind = def.zeroIC ? "zeros" : $("p-profile").value;
  if (def.zeroIC) {
    // laplace/poisson: solvers initialize from boundary conditions
    const ny = (def.params || []).some(([k]) => k === "ny") ? Math.max(2, Math.round(params.ny || nx)) : nx;
    const size = (def.params || []).some(([k]) => k === "ny") ? nx * ny : nx;
    return new Array(size).fill(0);
  }
  const out = [];
  for (let i = 0; i < nx; i++) {
    const x = nx > 1 ? i / (nx - 1) : 0;
    if (kind === "gauss") out.push(amp * Math.exp(-Math.pow(x - 0.3, 2) / 0.01));
    else if (kind === "flat") out.push(amp);
    else out.push(amp * Math.sin(Math.PI * x));
  }
  return out;
}

/* ============================= API ============================= */
async function api(path, body) {
  const res = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let data = null;
  try { data = await res.json(); } catch (_) { /* empty body */ }
  if (!res.ok) {
    const msg = (data && (data.detail || data.message)) || `HTTP ${res.status}`;
    const err = new Error(typeof msg === "string" ? msg : (msg && msg.message ? msg.message : JSON.stringify(msg)));
    err.status = res.status;
    err.detail = msg && typeof msg === "object" ? msg : null;
    throw err;
  }
  return data;
}

function setBanner(kind, msg) {
  const b = $("banner-" + kind);
  b.textContent = msg || "";
  b.classList.toggle("hidden", !msg);
}

/* ============================= Result rendering ============================= */
function showResults(data, def) {
  const card = $("results");
  card.classList.remove("hidden");
  card.scrollIntoView({ behavior: "smooth", block: "nearest" });

  const chips = $("res-chips");
  chips.innerHTML = "";
  const addChip = (cls, key) => chips.appendChild(el("span", "chip " + cls, key));
  addChip(data.status === "success" ? "ok" : "err", tr("status") + ": " + data.status);
  addChip("info", tr("method") + ": " + data.method);

  /* symbolic */
  const sym = $("res-symbolic");
  sym.classList.toggle("hidden", !data.symbolic_solution);
  if (data.symbolic_solution) {
    sym.textContent = tr("sol-symbolic") + ":  " + data.symbolic_solution;
  }

  /* eigenvalues */
  const eig = $("res-eigen");
  eig.classList.toggle("hidden", !(data.eigenvalues && data.eigenvalues.length));
  if (data.eigenvalues && data.eigenvalues.length) {
    eig.innerHTML = "";
    const h = el("div", "hint");
    h.textContent = tr("sol-eigen") + " (Sturm–Liouville):";
    eig.appendChild(h);
    const ul = el("ul");
    data.eigenvalues.slice(0, 12).forEach((v) => {
      const li = el("li");
      li.textContent = `${tr("eigen-val")}₁… = `;
      li.textContent = `λ = ${fmt(v)}`;
      ul.appendChild(li);
    });
    eig.appendChild(ul);
  }

  /* chart */
  const plotWrap = $("plot-wrap");
  const t = data.t || [];
  const y = data.y || [];
  const hasShape = Array.isArray(t) && Array.isArray(y) && y.length > 1 && y[0] && t.length >= 2;
  plotWrap.classList.toggle("hidden", !hasShape);
  if (hasShape) drawPlot(t, y, def, data);

  /* summary stats */
  const grid = $("res-grid");
  grid.innerHTML = "";
  const addStat = (k, v, small) => {
    const s = el("div", "stat");
    s.appendChild(el("div", "k", k));
    s.appendChild(el("div", "v" + (small ? " small" : ""), v));
    grid.appendChild(s);
  };
  addStat(tr("residual"), fmt(data.residual_max), true);
  addStat(tr("msg"), String(data.message || ""), true);
  if (hasShape && y[0].length === 1) {
    addStat(tr("stats-final"), fmt(y[y.length - 1][0]));
  } else if (hasShape && y[0].length <= 12) {
    const names = (def.vars && def.vars.length === y[0].length) ? def.vars : y[0].map((_, i) => `y${i}`);
    const last = y[y.length - 1];
    names.forEach((n, i) => {
      addStat(n + "  " + tr("stats-final"), fmt(last[i]), true);
    });
  }

  /* metadata */
  const meta = $("res-meta");
  const metaObj = {};
  if (data.metadata) metaObj.metadata = data.metadata;
  metaObj.samples = hasShape ? `${t.length} × ${y[0].length}` : "n/a";
  if (data.eigenvalues) metaObj.eigenvalue_count = data.eigenvalues.length;
  meta.textContent = JSON.stringify(metaObj, null, 2);
}

function downsample(arr, max) {
  if (arr.length <= max) return arr;
  const step = arr.length / max;
  const out = [];
  for (let i = 0; i < max; i++) out.push(arr[Math.min(arr.length - 1, Math.round(i * step))]);
  return out;
}

function drawPlot(tRaw, yRaw, def, data) {
  const canvas = $("plot");
  const ctx = canvas.getContext("2d");
  const W = canvas.width, H = canvas.height;
  ctx.clearRect(0, 0, W, H);

  const rows = yRaw.length;
  const cols = yRaw[0].length;
  const gridPde = cols > 8 || (def.g === "pde") || (def.g === "gridnum") || (def.g === "eigen");

  let xs, series;
  let legend = [];
  const tMin = Math.min(...tRaw.map(Number));
  const tMax = Math.max(...tRaw.map(Number));

  const gridView = gridPde;
  if (gridView) {
    /* rows are curves over the column index (PDE snapshots / eigenfunctions / grid systems) */
    const N = Math.min(8, rows);
    const idxs = [];
    for (let i = 0; i < N; i++) idxs.push(Math.round(i * (rows - 1) / Math.max(N - 1, 1)));
    xs = yRaw[0].map((_, j) => j);
    series = idxs.map((r) => yRaw[r].map((v) => (v === null || !isFinite(v) ? NaN : v)));
    legend = idxs.map((r) => {
      if (def.g === "eigen") return `φ${r + 1}`;
      const tv = tRaw[r];
      return `#${r}${tv !== undefined ? " (" + fmt(tv) + ")" : ""}`;
    });
  } else {
    /* time series: each column over the independent variable */
    xs = tRaw.map(Number);
    const N = Math.min(cols, 8);
    const names = (def.vars && def.vars.length === cols) ? def.vars : yRaw[0].map((_, i) => `y${i}`);
    series = [];
    for (let i = 0; i < N; i++) {
      series.push(yRaw.map((row) => (row[i] === null || !isFinite(row[i]) ? NaN : row[i])));
    }
    legend = names.slice(0, N);
  }

  const maxX = Math.max(xs.length - 1, 1);
  let vMin = Infinity, vMax = -Infinity;
  series.forEach((s) => s.forEach((v) => { if (!isNaN(v)) { vMin = Math.min(vMin, v); vMax = Math.max(vMax, v); } }));
  if (!isFinite(vMin)) { vMin = 0; vMax = 1; }
  if (vMin === vMax) { vMin -= 1; vMax += 1; }
  const pad = (vMax - vMin) * 0.08;
  vMin -= pad; vMax += pad;

  const PADL = 64, PADR = 16, PADT = 14, PADB = 30;
  const pw = W - PADL - PADR, ph = H - PADT - PADB;
  const X = (i) => PADL + (i / maxX) * pw;
  const Y = (v) => PADT + (1 - (v - vMin) / (vMax - vMin)) * ph;

  /* grid + axes */
  ctx.strokeStyle = "#1c2636";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 5; i++) {
    const gy = PADT + (ph * i) / 5;
    ctx.beginPath(); ctx.moveTo(PADL, gy); ctx.lineTo(W - PADR, gy); ctx.stroke();
    const gx = PADL + (pw * i) / 5;
    ctx.beginPath(); ctx.moveTo(gx, PADT); ctx.lineTo(gx, H - PADB); ctx.stroke();
  }
  ctx.fillStyle = "#7d92ac";
  ctx.font = "11px monospace";
  ctx.textAlign = "right";
  for (let i = 0; i <= 4; i++) {
    const val = vMax - ((vMax - vMin) * i) / 4;
    ctx.fillText(fmt(val, 3), PADL - 6, PADT + (ph * i) / 4 + 4);
  }
  ctx.textAlign = "center";
  const xStep = Math.max(1, Math.floor(xs.length / 5));
  for (let i = 0; i < xs.length; i += xStep) {
    ctx.fillText(fmt(xs[i], 3), X(i), H - 8);
  }

  /* series */
  series.forEach((s, si) => {
    const color = PALETTE[si % PALETTE.length];
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.beginPath();
    let started = false;
    for (let i = 0; i < s.length; i++) {
      if (isNaN(s[i])) { started = false; continue; }
      const px = X(i), py = Y(s[i]);
      if (!started) { ctx.moveTo(px, py); started = true; }
      else ctx.lineTo(px, py);
    }
    ctx.stroke();
  });

  /* legend */
  const legEl = $("plot-legend");
  legEl.innerHTML = "";
  legend.slice(0, 8).forEach((name, si) => {
    const span = el("span");
    const sw = el("i");
    sw.style.background = PALETTE[si % PALETTE.length];
    span.appendChild(sw);
    span.appendChild(document.createTextNode(name));
    legEl.appendChild(span);
  });
  const ax = el("span");
  ax.textContent = `x-axis: ${def.g === "pde" || def.g === "gridnum" || def.g === "eigen" ? "grid index" : tr("plot-x")}`;
  legEl.appendChild(ax);
}

/* ============================= Free-form equation ============================= */
function classifyFree(text) {
  return api("/analyze", { text, language: LANG });
}

async function symbolicFree(equation, variable, independent) {
  return api("/solve/symbolic", { equation, variable, independent });
}

function renderFreeResult(items) {
  const pane = $("free-res");
  pane.classList.remove("hidden");
  pane.innerHTML = "";
  const wrap = el("div", "result-pane-inner");
  for (const [label, val, mono] of items) {
    const s = el("div", "stat");
    s.appendChild(el("div", "k", label));
    const v = el("div", "v" + (mono ? " small mono" : ""));
    v.textContent = val;
    s.appendChild(v);
    wrap.appendChild(s);
  }
  pane.appendChild(wrap);
}

/* ============================= Wiring ============================= */
function applyLang() {
  const isFa = LANG === "fa";
  document.documentElement.lang = LANG;
  document.documentElement.dir = isFa ? "rtl" : "ltr";
  document.querySelectorAll("[data-i18n]").forEach((n) => {
    n.textContent = tr(n.dataset.i18n);
  });
  $("lang-en").classList.toggle("active", !isFa);
  $("lang-fa").classList.toggle("active", isFa);
  const tabs = document.querySelectorAll(".tab");
  tabs[0].textContent = tr("tabs-model");
  tabs[1].textContent = tr("tabs-free");
  const mSel = $("model-select");
  const keep = mSel.value || currentModel;
  buildModelOptions();
  selectModel(keep || currentModel);
}

async function healthCheck() {
  try {
    const h = await api("/health");
    $("health-state").textContent = h.status || "ok";
    $("health-state").style.color = "var(--ok)";
    $("health-models").textContent = String(h.models);
  } catch (e) {
    $("health-state").textContent = "offline";
    $("health-state").style.color = "var(--err)";
    setBanner("warn", tr("api-down"));
  }
}

async function runSolve() {
  const btn = $("btn-solve");
  btn.disabled = true;
  btn.textContent = LANG === "fa" ? "در حال حل…" : "Solving…";
  setBanner("error", "");
  try {
    const body = readConfig();
    const data = await api("/solve", body);
    showResults(data, MODEL_DEFS[currentModel]);
    initAuthArea();
  } catch (err) {
    if (err.status === 402) {
      showUpgrade(err.detail || err.message);
    } else {
      setBanner("error", `✗ ${err.message}`);
    }
  } finally {
    btn.disabled = false;
    btn.textContent = tr("btn-solve");
  }
}

function showUpgrade(detail) {
  const d = detail && typeof detail === "object" ? detail : null;
  const code = d && d.code;
  const msg = code === "insufficient_tokens"
    ? tr("upgrade-tokens")
    : ((d && d.message) || String(detail || ""));
  const b = $("banner-error");
  b.innerHTML = "";
  b.appendChild(document.createTextNode("✗ " + msg + "  "));
  const link = document.createElement("a");
  link.href = "/pricing";
  link.className = "upgrade-link";
  link.textContent = tr("view-plans");
  b.appendChild(link);
  b.classList.remove("hidden");
}

async function loadCosts() {
  try {
    const data = await api("/models");
    TOKEN_COSTS = data.token_costs || {};
    const keep = $("model-select").value;
    buildModelOptions();
    if (keep) $("model-select").value = keep;
    updateCostHint();
  } catch (_) { /* costs are not critical */ }
}

async function initAuthArea() {
  const slot = $("auth-area");
  if (!slot) return;
  let me = null;
  try { me = await api("/api/me"); } catch (_) { /* offline */ }
  MY_ENTITLEMENT = me && me.entitlement ? me.entitlement : null;
  slot.innerHTML = "";
  if (me && me.user) {
    const chip = document.createElement("span");
    chip.className = "user-chip";
    const badge = document.createElement("span");
    const ent = me.entitlement;
    badge.className = "plan-badge " + (ent.unlimited ? "admin" : (ent.tokens > 0 ? "pro" : "free"));
    badge.textContent = ent.unlimited ? "∞" : `${fmtInt(ent.tokens)} ${tr("tokens")}`;
    badge.title = tr("tokens-left");
    const name = document.createElement("span");
    name.className = "user-name";
    name.textContent = me.user.name;
    chip.append(badge, name);
    const account = document.createElement("a");
    account.href = "/account";
    account.className = "btn btn-small";
    account.textContent = LANG === "fa" ? "حساب" : "Account";
    slot.append(chip, account);
    updateCostHint();
    if (me.user.role === "admin") {
      const adminLink = document.createElement("a");
      adminLink.href = "/admin";
      adminLink.className = "btn btn-small btn-primary";
      adminLink.textContent = "Admin";
      slot.appendChild(adminLink);
    }
    const logout = document.createElement("button");
    logout.className = "btn btn-small";
    logout.textContent = LANG === "fa" ? "خروج" : "Log out";
    logout.onclick = async () => {
      await api("/api/auth/logout", {});
      location.reload();
    };
    slot.appendChild(logout);
  } else {
    const pricing = document.createElement("a");
    pricing.href = "/pricing";
    pricing.className = "btn btn-small";
    pricing.textContent = LANG === "fa" ? "تعرفه‌ها" : "Pricing";
    const login = document.createElement("a");
    login.href = "/auth";
    login.className = "btn btn-small btn-primary";
    login.textContent = LANG === "fa" ? "ورود / ثبت‌نام" : "Sign in";
    slot.append(pricing, login);
    updateCostHint();
  }
}

function init() {
  document.querySelectorAll(".lang-btn").forEach((b) => {
    b.addEventListener("click", () => {
      LANG = b.dataset.lang;
      applyLang();
    });
  });

  document.querySelectorAll(".tab").forEach((t) => {
    t.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("active", x === t));
      document.getElementById("panel-" + t.dataset.tab).classList.toggle("hidden", false);
      document.querySelectorAll(".panel").forEach((p) => {
        p.classList.toggle("hidden", p.id !== "panel-" + t.dataset.tab);
      });
    });
  });

  $("model-select").addEventListener("change", (e) => selectModel(e.target.value));
  $("model-search").addEventListener("input", () => {
    const sel = $("model-select");
    const keep = sel.value;
    buildModelOptions();
    if (keep) sel.value = keep;
    selectModel(sel.value);
  });

  $("btn-solve").addEventListener("click", runSolve);

  $("btn-example").addEventListener("click", () => {
    exampleIdx = (exampleIdx + 1) % EXAMPLE_CYCLE.length;
    selectModel(EXAMPLE_CYCLE[exampleIdx]);
  });

  $("btn-free-solve").addEventListener("click", async () => {
    setBanner("error", "");
    const eq = $("free-eq").value.trim();
    if (!eq) { setBanner("error", tr("free-sym-empty")); return; }
    const btn = $("btn-free-solve");
    btn.disabled = true;
    try {
      const data = await symbolicFree(eq, $("free-dep").value.trim() || "y", $("free-ind").value.trim() || "t");
      renderFreeResult([[tr("sol-symbolic"), data.solution, true]]);
    } catch (err) {
      if (err.status === 402) showUpgrade(err.detail || err.message);
      else setBanner("error", `✗ ${err.message}`);
    } finally {
      btn.disabled = false;
      initAuthArea();
    }
  });

  $("btn-free-classify").addEventListener("click", async () => {
    setBanner("error", "");
    const text = $("free-eq").value.trim();
    if (!text) { setBanner("error", tr("free-sym-empty")); return; }
    const btn = $("btn-free-classify");
    btn.disabled = true;
    try {
      const data = await classifyFree(text);
      const d = data.data || {};
      const lines = [
        [tr("free-class-title") + " — model", d.model || "?", false],
        ["variables", (d.variables || []).join(", "), false],
        ["source", d.source || "local", false],
        ["requires_external_api", String(d.requires_external_api), false],
      ];
      renderFreeResult(lines);
    } catch (err) {
      if (err.status === 402) showUpgrade(err.detail || err.message);
      else setBanner("error", `✗ ${err.message}`);
    } finally {
      btn.disabled = false;
      initAuthArea();
    }
  });

  $("p-points").addEventListener("input", updateCostHint);
  modelNames = Object.keys(MODEL_DEFS);
  applyLang();
  loadCosts();
  healthCheck();
  initAuthArea();
}

document.addEventListener("DOMContentLoaded", init);
