/* Portal — auth, pricing, account, admin (no build step, no external deps) */
"use strict";

/* ---------- i18n (FA default, EN toggle) ---------- */
const PORTAL_I18N = {
  "nav-solver": { en: "Solver", fa: "حل‌کننده" },
  "nav-pricing": { en: "Pricing", fa: "تعرفه‌ها" },
  "nav-account": { en: "Account", fa: "حساب کاربری" },
  "nav-admin": { en: "Admin", fa: "پنل مدیریت" },
  "nav-login": { en: "Sign in", fa: "ورود" },
  "nav-logout": { en: "Log out", fa: "خروج" },
  "tier-free": { en: "Free", fa: "رایگان" },
  "tier-pro": { en: "Pro", fa: "حرفه‌ای" },
  "tier-expired": { en: "Expired", fa: "منقضی شده" },
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
  const en = document.getElementById("plang-en");
  const fa = document.getElementById("plang-fa");
  if (en) en.classList.toggle("active", lang === "en");
  if (fa) fa.classList.toggle("active", lang === "fa");
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

function fmtDate(iso) {
  if (!iso) return "–";
  const d = new Date(iso);
  return d.toLocaleString(PLANG === "fa" ? "fa-IR" : "en-US", { dateStyle: "medium" });
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
    const badge = el("span", "plan-badge " + (me.entitlement.tier === "pro" ? "pro" : "free"),
      me.entitlement.tier === "pro" ? "PRO" : pget("tier-free"));
    chip.append(badge, el("span", "user-name", me.user.name));
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

function planBadge(ent) {
  if (!ent) return el("span", "plan-badge free", pget("tier-free"));
  const tier = ent.tier;
  const expired = tier === "free" && ent.ends_at && new Date(ent.ends_at) < new Date();
  const cls = tier === "pro" ? "pro" : "free";
  const label = tier === "pro" ? "PRO" : (expired ? pget("tier-expired") : pget("tier-free"));
  return el("span", "plan-badge " + cls, label);
}

/* ---------- Auth page ---------- */
async function initAuthPage() {
  const form = document.getElementById("auth-form");
  const title = document.getElementById("auth-title");
  const submit = document.getElementById("auth-submit");
  const errBox = document.getElementById("auth-error");
  let mode = "login";

  function setMode(m) {
    mode = m;
    title.textContent = m === "login" ? (PLANG === "fa" ? "ورود به حساب" : "Sign in") : (PLANG === "fa" ? "ساخت حساب جدید" : "Create account");
    submit.textContent = m === "login" ? (PLANG === "fa" ? "ورود" : "Sign in") : (PLANG === "fa" ? "ثبت‌نام" : "Sign up");
    document.getElementById("field-name").classList.toggle("hidden", m === "login");
    errBox.classList.add("hidden");
  }
  document.getElementById("tab-login").onclick = () => setMode("login");
  document.getElementById("tab-register").onclick = () => setMode("register");

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    errBox.classList.add("hidden");
    const email = document.getElementById("in-email").value.trim();
    const password = document.getElementById("in-password").value;
    const name = document.getElementById("in-name").value.trim();
    const body = mode === "login" ? { email, password } : { email, password, name };
    submit.disabled = true;
    try {
      await papi("/api/auth/" + (mode === "login" ? "login" : "register"), body);
      const ret = new URLSearchParams(location.search).get("returnTo");
      location.href = ret && ret.startsWith("/") ? ret : "/";
    } catch (err) {
      errBox.textContent = `✗ ${err.message}`;
      errBox.classList.remove("hidden");
      submit.disabled = false;
    }
  });
  setMode("login");
}

/* ---------- Pricing page ---------- */
async function initPricingPage() {
  const grid = document.getElementById("plans-grid");
  const modal = document.getElementById("pay-modal");
  const modalBody = document.getElementById("pay-modal-body");
  const closeBtn = document.getElementById("pay-modal-close");

  let me = null;
  try { me = await papi("/api/me"); } catch (_) { /* */ }

  function closeModal() {
    modal.classList.add("hidden");
    modalBody.innerHTML = "";
  }
  closeBtn.onclick = closeModal;
  modal.addEventListener("click", (e) => { if (e.target === modal) closeModal(); });

  const { plans } = await papi("/api/plans");
  plans.forEach((plan) => {
    if (plan.slug === "free") return;
    const card = el("div", "plan-card");
    card.appendChild(el("div", "plan-name", PLANG === "fa" ? plan.name_fa : plan.name_en));
    card.appendChild(el("div", "plan-desc", plan.description));
    card.appendChild(el("div", "plan-price", fmtNum(plan.price_toman) + " <small>تومان / ماه</small>"));
    const list = el("ul", "plan-features");
    [
      `${fmtNum(plan.solves_per_day)} حل در روز`,
      `حداکثر ${fmtNum(plan.max_points)} نقطه خروجی`,
      "دسترسی به مدل‌های ویژه",
      `${plan.duration_days} روز اعتبار`,
    ].forEach((f) => list.appendChild(el("li", "", f)));
    card.appendChild(list);
    const buy = el("button", "btn btn-primary", PLANG === "fa" ? "خرید اشتراک" : "Buy");
    buy.onclick = () => {
      if (!me || !me.user) {
        location.href = "/auth?returnTo=/pricing";
        return;
      }
      modalBody.innerHTML = "";
      modalBody.appendChild(el("h3", "", PLANG === "fa" ? "روش پرداخت" : "Payment method"));
      const choose = (gateway, label) => {
        const b = el("button", "btn gateway-btn", label);
        b.onclick = async () => {
          b.disabled = true;
          try {
            const res = await papi("/api/payment/start", { plan_slug: plan.slug, gateway });
            if (res.redirect_url) {
              location.href = res.redirect_url;
            } else if (res.wallet) {
              modalBody.innerHTML = "";
              modalBody.appendChild(el("h3", "", "USDT (TRC20)"));
              modalBody.appendChild(el("p", "hint", `مبلغ: ${res.amount_usdt} USDT — شبکه TRC20`));
              const addr = el("div", "crypto-addr", res.wallet);
              const copy = el("button", "btn btn-small", "کپی آدرس");
              copy.onclick = () => {
                navigator.clipboard && navigator.clipboard.writeText(res.wallet);
                copy.textContent = "✓";
              };
              modalBody.append(addr, copy);
              const orderId = res.order_id;
              modalBody.appendChild(el("p", "hint", `شماره سفارش: ${orderId} — پس از واریز، TXID را وارد کنید.`));
              const tx = el("input", "");
              tx.type = "text";
              tx.placeholder = "Transaction ID (TXID)";
              tx.style.marginTop = "8px";
              const send = el("button", "btn btn-primary", "ثبت تراکنش");
              const msg = el("div", "hint");
              send.onclick = async () => {
                if (!tx.value.trim()) { msg.textContent = "TXID را وارد کنید"; return; }
                send.disabled = true;
                try {
                  const out = await papi("/api/payment/crypto/tx", { order_id: orderId, txid: tx.value.trim() });
                  msg.textContent = "✓ " + (out.message || "در انتظار تأیید ادمین");
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
        choose("zarinpal", "زرین‌پال (کارت بانکی)"),
        choose("idpay", "آیدی‌پی (درگاه بانکی)"),
        choose("crypto", "USDT — TRC20"),
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
  card.appendChild(el("h2", "", PLANG === "fa" ? "وضعیت اشتراک" : "Subscription"));
  const row = el("div", "res-grid");
  const stat = (k, v) => {
    const s = el("div", "stat");
    s.append(el("div", "k", k), el("div", "v", v));
    row.appendChild(s);
  };
  stat("پلن", ent.tier === "pro" ? (PLANG === "fa" ? ent.plan_name_fa : ent.plan_name_en) : "Free");
  stat("اعتبار تا", fmtDate(ent.ends_at));
  stat("حل امروز", `${fmtNum(ent.solves_used)} / ${fmtNum(ent.solves_per_day)}`);
  stat("نقاط امروز", `${fmtNum(ent.points_used)} / ${fmtNum(ent.max_points)}`);
  card.appendChild(row);

  const ordersCard = el("div", "card");
  ordersCard.appendChild(el("h2", "", "سفارش‌های من"));
  try {
    const orders = await papi("/api/my-orders");
    if (!orders.length) ordersCard.appendChild(el("p", "hint", "سفارشی وجود ندارد."));
    const table = el("table", "portal-table");
    const head = el("tr", "");
    ["#", "پلن", "درگاه", "مبلغ", "وضعیت", "تاریخ"].forEach((h) => head.appendChild(el("th", "", h)));
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
    b.textContent = "✓ پرداخت موفق — اشتراک شما فعال شد.";
    box.prepend(b);
  } else if (result === "failed") {
    const b = el("div", "banner banner-error");
    b.textContent = "✗ پرداخت ناموفق بود.";
    box.prepend(b);
  }

  box.append(card, ordersCard);
}

/* ---------- Admin page ---------- */
async function initAdminPage() {
  const box = document.getElementById("admin-box");
  const tabs = document.querySelectorAll(".admin-tab");
  const sections = { stats: document.getElementById("sec-stats"), users: document.getElementById("sec-users"), orders: document.getElementById("sec-orders"), settings: document.getElementById("sec-settings") };
  const show = (name) => {
    tabs.forEach((t) => t.classList.toggle("active", t.dataset.sec === name));
    Object.entries(sections).forEach(([k, v]) => v.classList.toggle("hidden", k !== name));
  };
  tabs.forEach((t) => (t.onclick = () => show(t.dataset.sec)));

  /* stats */
  async function loadStats() {
    const s = await papi("/api/admin/stats");
    const grid = document.getElementById("stats-grid");
    grid.innerHTML = "";
    const items = [
      ["کاربران", s.users_total], ["ادمین‌ها", s.admins], ["مسدود", s.banned],
      ["اشتراک فعال", s.active_subscriptions], ["سفارش کل", s.orders_total],
      ["پرداخت موفق", s.paid_orders], ["حل امروز", s.solves_today],
    ];
    items.forEach(([k, v]) => {
      const d = el("div", "stat");
      d.append(el("div", "k", k), el("div", "v", fmtNum(v)));
      grid.appendChild(d);
    });
    const rev = Object.entries(s.revenue || {});
    if (rev.length) {
      const d = el("div", "stat");
      d.append(el("div", "k", "درآمد"), el("div", "v small", rev.map(([c, v]) => `${fmtNum(v)} ${c}`).join(" · ")));
      grid.appendChild(d);
    }
  }

  /* users */
  async function loadUsers() {
    const users = await papi("/api/admin/users");
    const tb = document.getElementById("users-body");
    tb.innerHTML = "";
    users.forEach((u) => {
      const tr = el("tr", "");
      const name = el("td", "", u.name);
      const mail = el("td", "", u.email);
      const roleTd = el("td", "");
      const roleBtn = el("button", "btn btn-small" + (u.role === "admin" ? " btn-primary" : ""), u.role);
      roleBtn.onclick = async () => {
        await papi(`/api/admin/users/${u.id}/role`, { role: u.role === "admin" ? "user" : "admin" }, "PATCH");
        loadUsers();
      };
      roleTd.appendChild(roleBtn);
      const subTd = el("td", "", u.subscription_plan ? `${u.subscription_plan} — ${fmtDate(u.subscription_ends_at)}` : "—");
      const grantTd = el("td", "");
      const sel = el("select", "");
      sel.innerHTML = '<option value="pro_monthly">pro_monthly</option><option value="pro_yearly">pro_yearly</option>';
      const days = el("input", "");
      days.type = "number"; days.min = 1; days.placeholder = "days";
      const grantBtn = el("button", "btn btn-small btn-primary", "اعطا");
      grantBtn.onclick = async () => {
        await papi("/api/admin/subscriptions/grant", { user_id: u.id, plan_slug: sel.value, days: days.value ? Number(days.value) : null });
        loadUsers();
      };
      grantTd.append(sel, days, grantBtn);
      const banTd = el("td", "");
      const banBtn = el("button", "btn btn-small" + (u.banned ? " btn-primary" : ""), u.banned ? "unban" : "ban");
      banBtn.onclick = async () => {
        await papi(`/api/admin/users/${u.id}/ban`, { banned: !u.banned }, "PATCH");
        loadUsers();
      };
      banTd.appendChild(banBtn);
      tr.append(name, mail, roleTd, subTd, grantTd, banTd);
      tb.appendChild(tr);
    });
  }

  /* orders */
  async function loadOrders() {
    const orders = await papi("/api/admin/orders");
    const tb = document.getElementById("orders-body");
    tb.innerHTML = "";
    orders.forEach((o) => {
      const tr = el("tr", "");
      tr.append(
        el("td", "", String(o.id)),
        el("td", "", o.email || "—"),
        el("td", "", o.plan_slug),
        el("td", "", o.gateway),
        el("td", "", `${fmtNum(o.amount)} ${o.currency}`),
        el("td", "", o.status),
        el("td", "", o.txid ? o.txid.slice(0, 16) + "…" : "—"),
      );
      const act = el("td", "");
      if (o.gateway === "crypto" && o.status === "pending_confirm") {
        const b = el("button", "btn btn-small btn-primary", "تأیید پرداخت");
        b.onclick = async () => {
          await papi(`/api/admin/orders/${o.id}/confirm`, {});
          loadOrders();
        };
        act.appendChild(b);
      }
      tr.appendChild(act);
      tb.appendChild(tr);
    });
  }

  /* settings */
  const settings = await papi("/api/admin/settings");
  document.getElementById("set-usdt").value = settings.usdt_wallet || "";
  document.getElementById("set-premium").value = settings.premium_models || "[]";
  document.getElementById("save-settings").onclick = async () => {
    const msg = document.getElementById("settings-msg");
    try {
      await papi("/api/admin/settings", { key: "usdt_wallet", value: document.getElementById("set-usdt").value.trim() });
      await papi("/api/admin/settings", { key: "premium_models", value: document.getElementById("set-premium").value.trim() });
      msg.textContent = "✓ ذخیره شد";
    } catch (err) {
      msg.textContent = `✗ ${err.message}`;
    }
  };

  await loadStats();
  await loadUsers();
  await loadOrders();
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