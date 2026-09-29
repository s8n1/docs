/* Portal — auth, pricing (token packs), account, admin (no build step, no external deps) */
"use strict";

/* ---------- i18n (FA default, EN toggle) ---------- */
const PORTAL_I18N = {
  "nav-solver": { en: "Solver", fa: "حل‌کننده" },
  "nav-pricing": { en: "Token packs", fa: "پک‌های توکن" },
  "nav-account": { en: "Account", fa: "حساب کاربری" },
  "nav-admin": { en: "Admin", fa: "پنل مدیریت" },
  "nav-login": { en: "Sign in", fa: "ورود" },
  "nav-logout": { en: "Log out", fa: "خروج" },
  "tokens": { en: "tokens", fa: "توکن" },
  "unlimited": { en: "unlimited", fa: "نامحدود" },
};

let PLANG = "fa";

function pget(key) {
  const row = PORTAL_I18N[key];
  return row ? row[PLANG] : key;
}

function psetLang(lang) {
  PLANG = lang;
  try { localStorage.setItem("de_lang", lang); } catch (_) { /* ignore */ }
  document.documentElement.lang = lang;
  document.documentElement.dir = lang === "fa" ? "rtl" : "ltr";
  document.querySelectorAll("[data-plang]").forEach((n) => {
    n.textContent = pget(n.dataset.plang);
  });
}

/* ---------- API ---------- */
async function papi(path, body, method) {
  const res = await fetch(path, {
    method: method || (body === undefined ? "GET" : "POST"),
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let data = null;
  try { data = await res.json(); } catch (_) { /* empty */ }
  if (!res.ok) {
    const err = new Error(typeof data === "object" && data && data.detail
      ? (typeof data.detail === "string" ? data.detail : (data.detail.message || JSON.stringify(data.detail)))
      : `HTTP ${res.status}`);
    err.status = res.status;
    err.detail = data && data.detail;
    throw err;
  }
  return data;
}

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
}

function fmtNum(n) {
  if (n === null || n === undefined) return "–";
  return Number(n).toLocaleString(PLANG === "fa" ? "fa-IR" : "en-US");
}

function fmtTokens(ent) {
  if (!ent) return "–";
  if (ent.unlimited) return "∞";
  return fmtNum(ent.tokens);
}

function fmtDate(iso) {
  if (!iso) return "–";
  const d = new Date(iso);
  return d.toLocaleString(PLANG === "fa" ? "fa-IR" : "en-US", { dateStyle: "medium" });
}

function tokenBadge(ent) {
  if (!ent) return el("span", "plan-badge free", "–");
  if (ent.unlimited) {
    const b = el("span", "plan-badge admin", "∞ " + (PLANG === "fa" ? "مدیر" : "ADMIN"));
    b.title = pget("unlimited");
    return b;
  }
  const b = el("span", "plan-badge " + (ent.tokens > 0 ? "pro" : "free"),
    `${fmtNum(ent.tokens)} ${pget("tokens")}`);
  return b;
}

/* ---------- Shared topbar ---------- */
async function renderTopbar() {
  const slot = document.getElementById("topbar");
  if (!slot) return;
  let me = null;
  try { me = await papi("/api/me"); } catch (_) { /* offline */ }

  const isFa = PLANG === "fa";
  const brand = el("a", "brand portal-brand");
  brand.href = "/";
  brand.innerHTML = '<span class="brand-mark">∫</span><span class="portal-brand-name">DiffEQ Engine</span>';

  const nav = el("nav", "portal-nav");
  const links = [
    ["/", "nav-solver"], ["/pricing", "nav-pricing"],
  ];
  if (me && me.user) {
    links.push(["/account", "nav-account"]);
    if (me.user.role === "admin") links.push(["/admin", "nav-admin"]);
  }
  links.forEach(([href, key]) => {
    const a = el("a", "portal-link", pget(key));
    a.href = href;
    if (location.pathname === href) a.classList.add("active");
    nav.appendChild(a);
  });

  const lang = el("div", "lang-toggle");
  const bEn = el("button", "lang-btn" + (isFa ? "" : " active"), "EN");
  const bFa = el("button", "lang-btn" + (isFa ? " active" : ""), "فارسی");
  bEn.onclick = () => psetLang("en");
  bFa.onclick = () => psetLang("fa");
  lang.append(bEn, bFa);

  const authArea = el("div", "auth-area");
  if (me && me.user) {
    const chip = el("div", "user-chip");
    chip.append(tokenBadge(me.entitlement), el("span", "user-name", me.user.name));
    const logout = el("button", "btn btn-small", pget("nav-logout"));
    logout.onclick = async () => {
      await papi("/api/auth/logout", {});
      location.href = "/";
    };
    authArea.append(chip, logout);
  } else {
    const login = el("a", "btn btn-small btn-primary", pget("nav-login"));
    login.href = "/auth";
    authArea.appendChild(login);
  }

  slot.append(brand, nav, lang, authArea);
}

/* ---------- Auth page ---------- */
async function initAuthPage() {
  const form = document.getElementById("auth-form");
  const title = document.getElementById("auth-title");
  const submit = document.getElementById("auth-submit");
  const errBox = document.getElementById("auth-error");
  const label = document.getElementById("in-identifier-label");
  let mode = "login";

  function setMode(m) {
    mode = m;
    title.textContent = m === "login"
      ? (PLANG === "fa" ? "ورود به حساب" : "Sign in")
      : (PLANG === "fa" ? "ساخت حساب جدید" : "Create account");
    submit.textContent = m === "login"
      ? (PLANG === "fa" ? "ورود" : "Sign in")
      : (PLANG === "fa" ? "ثبت‌نام" : "Sign up");
    if (label) label.textContent = m === "login"
      ? (PLANG === "fa" ? "ایمیل یا نام کاربری" : "Email or username")
      : (PLANG === "fa" ? "ایمیل" : "Email");
    document.getElementById("field-name").classList.toggle("hidden", m === "login");
    document.getElementById("field-username").classList.toggle("hidden", m === "login");
    errBox.classList.add("hidden");
  }
  document.getElementById("tab-login").onclick = () => setMode("login");
  document.getElementById("tab-register").onclick = () => setMode("register");

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    errBox.classList.add("hidden");
    const identifier = document.getElementById("in-identifier").value.trim();
    const password = document.getElementById("in-password").value;
    const name = document.getElementById("in-name").value.trim();
    const username = document.getElementById("in-username").value.trim();
    const body = mode === "login"
      ? { identifier, password }
      : { email: identifier, password, name, username: username || null };
    submit.disabled = true;
    try {
      await papi("/api/auth/" + (mode === "login" ? "login" : "register"), body);
      const ret = new URLSearchParams(location.search).get("returnTo");
      location.href = ret && ret.startsWith("/") ? ret : "/account";
    } catch (err) {
      errBox.textContent = `✗ ${err.message}`;
      errBox.classList.remove("hidden");
      submit.disabled = false;
    }
  });
  setMode("login");
}

/* ---------- Pricing page (token packs) ---------- */
async function initPricingPage() {
  const grid = document.getElementById("plans-grid");
  const modal = document.getElementById("pay-modal");
  const modalBody = document.getElementById("pay-modal-body");
  const closeBtn = document.getElementById("pay-modal-close");
  const balanceBox = document.getElementById("pricing-balance");

  let me = null;
  try { me = await papi("/api/me"); } catch (_) { /* */ }

  if (balanceBox) {
    if (me && me.user) {
      balanceBox.textContent = `${PLANG === "fa" ? "موجودی فعلی" : "Current balance"}: ${fmtTokens(me.entitlement)} ${pget("tokens")}`;
    } else {
      balanceBox.textContent = PLANG === "fa"
        ? "بدون ثبت‌نام هم می‌توانید با توکن‌های آزمایشی حل‌کننده را امتحان کنید."
        : "You can try the solver with trial tokens before signing up.";
    }
  }

  function closeModal() {
    modal.classList.add("hidden");
    modalBody.innerHTML = "";
  }
  closeBtn.onclick = closeModal;
  modal.addEventListener("click", (e) => { if (e.target === modal) closeModal(); });

  const plansData = await papi("/api/plans");
  const paidPlans = (plansData.plans || []).filter((p) => p.slug !== "free");
  paidPlans.forEach((plan) => {
    const card = el("div", "plan-card");
    card.appendChild(el("div", "plan-name", PLANG === "fa" ? plan.name_fa : plan.name_en));
    card.appendChild(el("div", "plan-desc", plan.description));
    const price = el("div", "plan-price");
    price.innerHTML = `${fmtNum(plan.price_toman)} <small>${PLANG === "fa" ? "تومان" : "Toman"}</small>`;
    card.appendChild(price);
    card.appendChild(el("div", "plan-usdt", `≈ ${fmtNum(plan.price_usdt)} USDT`));
    const list = el("ul", "plan-features");
    [
      `${fmtNum(plan.tokens)} ${PLANG === "fa" ? "توکن" : "tokens"}`,
      PLANG === "fa" ? "بدون انقضا — زمان مهم نیست" : "Never expires — time plays no role",
      PLANG === "fa" ? "پرداخت با زرین‌پال یا USDT (TRC20)" : "Pay with ZarinPal or USDT (TRC20)",
      PLANG === "fa" ? "شارژ فوری روی همین حساب" : "Credited to this account instantly",
    ].forEach((f) => list.appendChild(el("li", "", f)));
    card.appendChild(list);
    const buy = el("button", "btn btn-primary", PLANG === "fa" ? "خرید پک" : "Buy pack");
    buy.onclick = () => {
      if (!me || !me.user) {
        location.href = "/auth?returnTo=/pricing";
        return;
      }
      modalBody.innerHTML = "";
      modalBody.appendChild(el("h3", "", PLANG === "fa" ? "روش پرداخت" : "Payment method"));
      modalBody.appendChild(el("p", "hint",
        `${plan.tokens} ${pget("tokens")} · ${fmtNum(plan.price_toman)} ${PLANG === "fa" ? "تومان" : "Toman"}`));
      const choose = (gateway, label2) => {
        const b = el("button", "btn gateway-btn", label2);
        b.onclick = async () => {
          b.disabled = true;
          try {
            const res = await papi("/api/payment/start", { plan_slug: plan.slug, gateway });
            if (res.redirect_url) {
              location.href = res.redirect_url;
            } else if (res.wallet) {
              modalBody.innerHTML = "";
              modalBody.appendChild(el("h3", "", "USDT (TRC20)"));
              modalBody.appendChild(el("p", "hint",
                `${PLANG === "fa" ? "مبلغ" : "Amount"}: ${res.amount_usdt} USDT — TRC20`));
              const addr = el("div", "crypto-addr", res.wallet);
              const copy = el("button", "btn btn-small", PLANG === "fa" ? "کپی آدرس" : "Copy address");
              copy.onclick = () => {
                navigator.clipboard && navigator.clipboard.writeText(res.wallet);
                copy.textContent = "✓";
              };
              modalBody.append(addr, copy);
              modalBody.appendChild(el("p", "hint",
                PLANG === "fa"
                  ? `پس از واریز، TXID را ثبت کنید. با تأیید ادمین ${res.tokens} توکن اضافه می‌شود.`
                  : `After sending, submit the TXID. Once an admin verifies it, ${res.tokens} tokens are credited.`));
              const tx = el("input", "");
              tx.type = "text";
              tx.placeholder = "Transaction ID (TXID)";
              const send = el("button", "btn btn-primary", PLANG === "fa" ? "ثبت تراکنش" : "Submit TXID");
              const msg = el("div", "hint");
              send.onclick = async () => {
                if (!tx.value.trim()) {
                  msg.textContent = PLANG === "fa" ? "TXID را وارد کنید" : "Enter the TXID";
                  return;
                }
                send.disabled = true;
                try {
                  const out = await papi("/api/payment/crypto/tx", { order_id: res.order_id, txid: tx.value.trim() });
                  msg.textContent = "✓ " + (PLANG === "fa" ? "ثبت شد — در انتظار تأیید ادمین" : (out.message || "Awaiting admin verification"));
                } catch (err) {
                  msg.textContent = `✗ ${err.message}`;
                  send.disabled = false;
                }
              };
              modalBody.append(tx, send, msg);
            }
          } catch (err) {
            modalBody.innerHTML = "";
            modalBody.appendChild(el("p", "hint err-text", `✗ ${err.message}`));
          }
        };
        return b;
      };
      modalBody.append(
        choose("zarinpal", PLANG === "fa" ? "زرین‌پال (کارت بانکی)" : "ZarinPal (bank card)"),
        choose("crypto", "USDT — TRC20"),
        choose("idpay", PLANG === "fa" ? "آیدی‌پی (درگاه بانکی)" : "IDPay (bank gateway)"),
      );
      modal.classList.remove("hidden");
    };
    card.appendChild(buy);
    grid.appendChild(card);
  });
}

/* ---------- Account page ---------- */
async function initAccountPage() {
  const box = document.getElementById("account-box");
  let me = null;
  try { me = await papi("/api/me"); } catch (_) { /* */ }
  if (!me || !me.user) {
    box.innerHTML = "";
    const a = el("a", "btn btn-primary", "ورود / ثبت‌نام");
    a.href = "/auth?returnTo=/account";
    box.append(el("p", "hint", "برای مشاهده حساب وارد شوید."), a);
    return;
  }
  const ent = me.entitlement;
  const card = el("div", "card");
  card.appendChild(el("h2", "", PLANG === "fa" ? "توکن‌های من" : "My tokens"));
  const row = el("div", "res-grid");
  const stat = (k, v) => {
    const s = el("div", "stat");
    s.append(el("div", "k", k), el("div", "v", v));
    row.appendChild(s);
  };
  stat(PLANG === "fa" ? "موجودی" : "Balance", ent.unlimited ? "∞" : fmtNum(ent.tokens));
  stat(PLANG === "fa" ? "مصرف کل" : "Spent", fmtNum(ent.tokens_spent));
  stat(PLANG === "fa" ? "حل امروز" : "Solves today", fmtNum(ent.solves_used));
  stat(PLANG === "fa" ? "نقاط امروز" : "Points today", fmtNum(ent.points_used));
  card.appendChild(row);
  if (ent.unlimited) {
    card.appendChild(el("p", "hint", PLANG === "fa"
      ? "حساب مدیر: دسترسی نامحدود و بدون کسر توکن."
      : "Admin account: unlimited access, tokens are never deducted."));
  }
  const buy = el("a", "btn btn-primary", PLANG === "fa" ? "خرید پک توکن" : "Buy a token pack");
  buy.href = "/pricing";
  if (!ent.unlimited) card.appendChild(buy);

  const adminLink = el("a", "btn", PLANG === "fa" ? "پنل مدیریت" : "Admin panel");
  adminLink.href = "/admin";
  if (me.user.role === "admin") card.appendChild(adminLink);

  /* Password rotation — the seeded admin password should be replaced. */
  const passCard = el("div", "card");
  passCard.appendChild(el("h2", "", PLANG === "fa" ? "تغییر رمز عبور" : "Change password"));
  if (me.user.role === "admin") {
    passCard.appendChild(el("div", "admin-note", PLANG === "fa"
      ? "شما با دسترسی مدیر وارد شده‌اید. اگر هنوز از رمز پیش‌فرض استفاده می‌کنید، همین حالا آن را عوض کنید."
      : "You are signed in as an admin. If you still use the default password, replace it now."));
  }
  const curField = el("label", "field");
  curField.appendChild(el("span", "lbl", PLANG === "fa" ? "رمز عبور فعلی" : "Current password"));
  const curInput = el("input");
  curInput.type = "password";
  curInput.autocomplete = "current-password";
  curField.appendChild(curInput);
  const newField = el("label", "field");
  newField.appendChild(el("span", "lbl", PLANG === "fa" ? "رمز عبور جدید (حداقل ۸ کاراکتر)" : "New password (min 8 characters)"));
  const newInput = el("input");
  newInput.type = "password";
  newInput.autocomplete = "new-password";
  newField.appendChild(newInput);
  const passMsg = el("div", "hint");
  const passBtn = el("button", "btn btn-primary", PLANG === "fa" ? "ذخیرهٔ رمز جدید" : "Save new password");
  passBtn.onclick = async () => {
    passMsg.textContent = "";
    passBtn.disabled = true;
    try {
      await papi("/api/account/password", {
        current_password: curInput.value,
        new_password: newInput.value,
      });
      passMsg.textContent = PLANG === "fa" ? "✓ رمز عبور به‌روز شد" : "✓ Password updated";
      curInput.value = "";
      newInput.value = "";
    } catch (err) {
      passMsg.textContent = `✗ ${err.message}`;
    } finally {
      passBtn.disabled = false;
    }
  };
  const passActions = el("div", "actions");
  passActions.append(passBtn, passMsg);
  passCard.append(curField, newField, passActions);

  /* Token costs by difficulty */
  const costCard = el("div", "card");
  costCard.appendChild(el("h2", "", PLANG === "fa" ? "هزینهٔ ابزارها و مدل‌ها" : "Tool & model costs"));
  const costs = ent.model_costs || {};
  const toolCosts = ent.tool_costs || {};
  const buildCostTable = (entries) => {
    const table = el("table", "portal-table");
    const head = el("tr", "");
    [PLANG === "fa" ? "ابزار" : "Tool", PLANG === "fa" ? "توکن" : "Tokens"].forEach((h) => head.appendChild(el("th", "", h)));
    table.appendChild(head);
    entries.sort((a, b) => a[1] - b[1] || a[0].localeCompare(b[0]));
    entries.forEach(([name, cost]) => {
      const tr = el("tr", "");
      tr.append(el("td", "", name.replace(/_/g, " ")), el("td", "", fmtNum(cost)));
      table.appendChild(tr);
    });
    return table;
  };
  if (Object.keys(toolCosts).length) {
    costCard.appendChild(el("h3", "", PLANG === "fa" ? "ابزارها" : "Tools"));
    costCard.appendChild(buildCostTable(Object.entries(toolCosts)));
  }
  costCard.appendChild(el("h3", "", PLANG === "fa" ? "مدل‌ها (بر اساس سختی)" : "Models (by difficulty)"));
  costCard.appendChild(buildCostTable(Object.entries(costs)));

  /* Token history */
  const ledgerCard = el("div", "card");
  ledgerCard.appendChild(el("h2", "", PLANG === "fa" ? "تاریخچهٔ توکن" : "Token history"));
  try {
    const data = await papi("/api/my-tokens");
    const entries = data.entries || [];
    if (!entries.length) {
      ledgerCard.appendChild(el("p", "hint", PLANG === "fa" ? "حرکتی ثبت نشده است." : "No movements yet."));
    } else {
      const table = el("table", "portal-table");
      const head = el("tr", "");
      [PLANG === "fa" ? "تغییر" : "Delta", PLANG === "fa" ? "دلیل" : "Reason",
        PLANG === "fa" ? "موجودی" : "Balance", PLANG === "fa" ? "تاریخ" : "Date"]
        .forEach((h) => head.appendChild(el("th", "", h)));
      table.appendChild(head);
      entries.forEach((e) => {
        const tr = el("tr", "");
        const deltaCell = el("td", e.delta > 0 ? "delta-pos" : "delta-neg", (e.delta > 0 ? "+" : "") + fmtNum(e.delta));
        tr.append(deltaCell, el("td", "", e.reason), el("td", "", fmtNum(e.balance_after)), el("td", "", fmtDate(e.created_at)));
        table.appendChild(tr);
      });
      ledgerCard.appendChild(table);
    }
  } catch (_) { /* history not critical */ }

  /* Orders */
  const ordersCard = el("div", "card");
  ordersCard.appendChild(el("h2", "", PLANG === "fa" ? "سفارش‌های من" : "My orders"));
  try {
    const orders = await papi("/api/my-orders");
    if (!orders.length) ordersCard.appendChild(el("p", "hint", "سفارشی وجود ندارد."));
    const table = el("table", "portal-table");
    const head = el("tr", "");
    ["#", PLANG === "fa" ? "پک" : "Pack", PLANG === "fa" ? "درگاه" : "Gateway",
      PLANG === "fa" ? "مبلغ" : "Amount", PLANG === "fa" ? "وضعیت" : "Status",
      PLANG === "fa" ? "تاریخ" : "Date"].forEach((h) => head.appendChild(el("th", "", h)));
    table.appendChild(head);
    orders.forEach((o) => {
      const tr = el("tr", "");
      [o.id, o.plan_slug, o.gateway, fmtNum(o.amount) + " " + o.currency, o.status, fmtDate(o.created_at)]
        .forEach((v) => tr.appendChild(el("td", "", v)));
      table.appendChild(tr);
    });
    ordersCard.appendChild(table);
  } catch (_) { /* orders not critical */ }

  const result = new URLSearchParams(location.search).get("result");
  if (result === "success") {
    const b = el("div", "banner banner-warn");
    b.textContent = "✓ پرداخت موفق — توکن‌ها به حساب شما اضافه شد.";
    box.prepend(b);
  } else if (result === "failed") {
    const b = el("div", "banner banner-error");
    b.textContent = "✗ پرداخت ناموفق بود.";
    box.prepend(b);
  }

  box.append(card, passCard, costCard, ledgerCard, ordersCard);
}

/* ---------- Admin page ---------- */
async function initAdminPage() {
  const me = await papi("/api/me");
  if (!me.user) {
    location.href = "/auth?returnTo=/admin";
    return;
  }
  if (me.user.role !== "admin") {
    location.href = "/";
    return;
  }
  const tabs = document.querySelectorAll(".admin-tab");
  const sections = {
    stats: document.getElementById("sec-stats"),
    users: document.getElementById("sec-users"),
    orders: document.getElementById("sec-orders"),
    ledger: document.getElementById("sec-ledger"),
    settings: document.getElementById("sec-settings"),
  };
  const show = (name) => {
    tabs.forEach((t) => t.classList.toggle("active", t.dataset.sec === name));
    Object.entries(sections).forEach(([k, v]) => { if (v) v.classList.toggle("hidden", k !== name); });
  };
  tabs.forEach((t) => (t.onclick = () => show(t.dataset.sec)));

  /* stats */
  async function loadStats() {
    const s = await papi("/api/admin/stats");
    const grid = document.getElementById("stats-grid");
    grid.innerHTML = "";
    const items = [
      [PLANG === "fa" ? "کاربران" : "Users", s.users_total],
      [PLANG === "fa" ? "ادمین‌ها" : "Admins", s.admins],
      [PLANG === "fa" ? "مسدود" : "Banned", s.banned],
      [PLANG === "fa" ? "توکن در گردش" : "Tokens outstanding", s.tokens_outstanding],
      [PLANG === "fa" ? "توکن فروخته‌شده" : "Tokens added", s.tokens_sold],
      [PLANG === "fa" ? "توکن مصرف‌شده" : "Tokens spent", s.tokens_spent],
      [PLANG === "fa" ? "سفارش کل" : "Orders", s.orders_total],
      [PLANG === "fa" ? "پرداخت موفق" : "Paid", s.paid_orders],
      [PLANG === "fa" ? "در انتظار تأیید" : "Awaiting confirm", s.pending_orders],
      [PLANG === "fa" ? "حل امروز" : "Solves today", s.solves_today],
    ];
    items.forEach(([k, v]) => {
      const d = el("div", "stat");
      d.append(el("div", "k", k), el("div", "v", fmtNum(v)));
      grid.appendChild(d);
    });
    const rev = Object.entries(s.revenue || {});
    if (rev.length) {
      const d = el("div", "stat");
      d.append(el("div", "k", PLANG === "fa" ? "درآمد" : "Revenue"),
        el("div", "v small", rev.map(([c, v]) => `${fmtNum(v)} ${c}`).join(" · ")));
      grid.appendChild(d);
    }
  }

  /* users */
  let plans = [];
  try { plans = (await papi("/api/plans")).plans.filter((p) => p.slug !== "free"); } catch (_) { /* */ }

  async function loadUsers() {
    const users = await papi("/api/admin/users");
    const tb = document.getElementById("users-body");
    tb.innerHTML = "";
    users.forEach((u) => {
      const tr = el("tr", "");
      const idTd = el("td", "", "#" + u.id);
      const nameCell = el("td", "");
      nameCell.append(el("div", "", u.name), el("div", "hint", u.username ? "@" + u.username : u.email));
      const roleTd = el("td", "");
      const roleBtn = el("button", "btn btn-small" + (u.role === "admin" ? " btn-primary" : ""), u.role);
      roleBtn.onclick = async () => {
        try {
          await papi(`/api/admin/users/${u.id}/role`, { role: u.role === "admin" ? "user" : "admin" }, "PATCH");
          loadUsers();
        } catch (err) { alert(err.message); }
      };
      roleTd.appendChild(roleBtn);
      const tokenTd = el("td", "");
      tokenTd.append(
        el("div", "", `${fmtNum(u.tokens)} ${pget("tokens")}`),
        el("div", "hint", `${PLANG === "fa" ? "مصرف" : "spent"}: ${fmtNum(u.tokens_spent)}`),
      );
      const adjustTd = el("td", "");
      const amount = el("input", "");
      amount.type = "number";
      amount.placeholder = "±500";
      const applyBtn = el("button", "btn btn-small", PLANG === "fa" ? "اعمال" : "Apply");
      applyBtn.onclick = async () => {
        const delta = Number(amount.value);
        if (!delta) { alert(PLANG === "fa" ? "مقدار را وارد کنید" : "Enter an amount"); return; }
        try {
          await papi(`/api/admin/users/${u.id}/tokens`, { delta, reason: "admin panel" });
          loadUsers();
          loadStats();
        } catch (err) { alert(err.message); }
      };
      const plus = el("button", "btn btn-small", "+500");
      plus.onclick = async () => {
        await papi(`/api/admin/users/${u.id}/tokens`, { delta: 500, reason: "admin panel" });
        loadUsers();
        loadStats();
      };
      adjustTd.append(amount, applyBtn, plus);
      const grantTd = el("td", "");
      const sel = el("select", "");
      sel.innerHTML = plans.map((p) => `<option value="${p.slug}">${p.name_fa} (${p.tokens})</option>`).join("");
      const grantBtn = el("button", "btn btn-small btn-primary", PLANG === "fa" ? "اعطا" : "Grant");
      grantBtn.onclick = async () => {
        try {
          await papi("/api/admin/tokens/grant", { user_id: u.id, plan_slug: sel.value });
          loadUsers();
          loadStats();
        } catch (err) { alert(err.message); }
      };
      grantTd.append(sel, grantBtn);
      const banTd = el("td", "");
      const banBtn = el("button", "btn btn-small" + (u.banned ? " btn-primary" : ""), u.banned ? "unban" : "ban");
      banBtn.onclick = async () => {
        await papi(`/api/admin/users/${u.id}/ban`, { banned: !u.banned }, "PATCH");
        loadUsers();
      };
      banTd.appendChild(banBtn);
      tr.append(idTd, nameCell, roleTd, tokenTd, adjustTd, grantTd, banTd);
      tb.appendChild(tr);
    });
  }

  /* orders */
  async function loadOrders() {
    const orders = await papi("/api/admin/orders");
    const tb = document.getElementById("orders-body");
    tb.innerHTML = "";
    const EXPLORER = "https://tronscan.org/#/transaction/";
    orders.forEach((o) => {
      const tr = el("tr", "");
      tr.append(
        el("td", "", String(o.id)),
        el("td", "", o.username ? "@" + o.username : (o.email || "—")),
        el("td", "", o.plan_slug),
        el("td", "", o.gateway),
        el("td", "", `${fmtNum(o.amount)} ${o.currency}`),
        el("td", "", o.status),
      );
      const txTd = el("td", "");
      if (o.txid) {
        const a = el("a", "", o.txid.slice(0, 18) + (o.txid.length > 18 ? "…" : ""));
        a.href = EXPLORER + o.txid;
        a.target = "_blank";
        a.rel = "noopener";
        txTd.appendChild(a);
      } else {
        txTd.textContent = "—";
      }
      tr.appendChild(txTd);
      const act = el("td", "");
      if (o.gateway === "crypto" && (o.status === "pending" || o.status === "pending_confirm")) {
        const b = el("button", "btn btn-small btn-primary", PLANG === "fa" ? "تأیید پرداخت" : "Confirm");
        b.onclick = async () => {
          try {
            await papi(`/api/admin/orders/${o.id}/confirm`, {});
            loadOrders();
            loadStats();
          } catch (err) { alert(err.message); }
        };
        act.appendChild(b);
      }
      tr.appendChild(act);
      tb.appendChild(tr);
    });
  }

  /* token ledger */
  async function loadLedger() {
    const entries = await papi("/api/admin/tokens/ledger");
    const tb = document.getElementById("ledger-body");
    tb.innerHTML = "";
    entries.forEach((e) => {
      const tr = el("tr", "");
      const who = e.username ? "@" + e.username : (e.email || `${e.owner}:${String(e.owner_id).slice(0, 12)}`);
      tr.append(
        el("td", "", String(e.id)),
        el("td", "", who),
        el("td", e.delta > 0 ? "delta-pos" : "delta-neg", (e.delta > 0 ? "+" : "") + fmtNum(e.delta)),
        el("td", "", e.reason),
        el("td", "", fmtNum(e.balance_after)),
        el("td", "", fmtDate(e.created_at)),
      );
      tb.appendChild(tr);
    });
  }

  /* settings */
  const settings = await papi("/api/admin/settings");
  document.getElementById("set-usdt").value = settings.usdt_wallet || "";
  document.getElementById("set-costs").value = settings.model_token_costs || "{}";
  document.getElementById("save-settings").onclick = async () => {
    const msg = document.getElementById("settings-msg");
    try {
      await papi("/api/admin/settings", { key: "usdt_wallet", value: document.getElementById("set-usdt").value.trim() });
      await papi("/api/admin/settings", { key: "model_token_costs", value: document.getElementById("set-costs").value.trim() });
      msg.textContent = "✓ ذخیره شد";
    } catch (err) {
      msg.textContent = `✗ ${err.message}`;
    }
  };

  await loadStats();
  await loadUsers();
  await loadOrders();
  await loadLedger();
  show("stats");
}

/* ---------- Boot ---------- */
document.addEventListener("DOMContentLoaded", async () => {
  try { PLANG = localStorage.getItem("de_lang") || "fa"; } catch (_) { /* */ }
  psetLang(PLANG);
  await renderTopbar();

  const page = document.body.dataset.page;
  try {
    if (page === "auth") await initAuthPage();
    if (page === "pricing") await initPricingPage();
    if (page === "account") await initAccountPage();
    if (page === "admin") await initAdminPage();
  } catch (err) {
    const box = document.getElementById("page-error");
    if (box) {
      box.textContent = `✗ ${err.message}`;
      box.classList.remove("hidden");
    }
  }
});
