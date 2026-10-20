// Service worker: talks to the local Second Thought app (127.0.0.1 only) and falls back to an
// offline estimate from the extension settings when the app is not running or not paired.
const DEFAULTS = {
  lang: "auto", api: "http://127.0.0.1:8765", code: "", mode: "always",
  currency: "CNY", leftUntilPayday: 3000, payday: 10, income: 15000, hours: 174,
  triggers: "外套, 大衣, 口红, 美妆, coat, jacket, lipstick, sneakers, Jacke",
  nightStart: "23:00", nightEnd: "06:00", nightHold: true, nightThreshold: 300, holdHours: 12,
  goalName: "Savings goal", goalMonthly: 1500,
};
const SYMBOLS = { CNY: "¥", EUR: "€", USD: "$", GBP: "£" };
const PASS_MINUTES = 10;

async function settings() {
  const { settings: s } = await chrome.storage.local.get("settings");
  return { ...DEFAULTS, ...(s || {}) };
}
async function local() {
  const d = await chrome.storage.local.get(["history", "parked", "passed", "skippedTotal"]);
  return { history: d.history || [], parked: d.parked || [], passed: d.passed || {}, skippedTotal: d.skippedTotal || 0 };
}

async function api(s, path, body) {
  if (!s.code) throw new Error("not paired");
  const base = s.api.replace(/\/+$/, "");
  if (!/^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/.test(base)) throw new Error("the app address must be on this computer");
  const ctrl = new AbortController();
  const timeout = setTimeout(() => ctrl.abort(), 4000);
  try {
    const res = await fetch(base + path, {
      method: body ? "POST" : "GET", signal: ctrl.signal,
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${s.code}` },
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    return data;
  } finally {
    clearTimeout(timeout);
  }
}

// ---- offline estimate (same signals as the app, fewer inputs) -------------------------
const toMin = (hm) => { const [h, m] = String(hm).split(":").map(Number); return h * 60 + (m || 0); };
function inWindow(now, start, end) {
  const m = now.getHours() * 60 + now.getMinutes(), a = toMin(start), b = toMin(end);
  return a > b ? m >= a || m < b : m >= a && m < b;
}
function nextPayday(now, day) {
  const d = new Date(now.getFullYear(), now.getMonth(), Math.min(day, 28));
  if (now.getDate() >= day) d.setMonth(d.getMonth() + 1);
  return d;
}
function iso(d) {
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

function offlineCheck(info, s, store) {
  const now = new Date();
  const hm = now.toTimeString().slice(0, 5);
  const amount = Number(info.amount);
  const reasons = [];
  const night = inWindow(now, s.nightStart, s.nightEnd);
  if (night) reasons.push({ code: "night", points: 20, en: `Late at night (${hm})`, zh: `深夜消费（${hm}）` });
  const recent = store.history.filter((h) => now - new Date(h.at) < 3600e3).length;
  if (recent >= 2) reasons.push({ code: "burst", points: 20, en: `Purchase number ${recent + 1} within an hour`, zh: `一小时内第 ${recent + 1} 笔` });
  if (info.livestream || info.flash_sale) {
    reasons.push({ code: "livestream", points: 15, en: info.livestream ? "Live-stream shopping" : "Flash sale or countdown",
      zh: info.livestream ? "直播间购物" : "限时秒杀或倒计时" });
  }
  const triggers = String(s.triggers).split(/[,，]/).map((x) => x.trim().toLowerCase()).filter(Boolean);
  const hit = triggers.find((w) => String(info.title).toLowerCase().includes(w));
  if (hit) reasons.push({ code: "trigger", points: 15, en: `'${hit}' is on your trigger list`, zh: `「${hit}」在你的触发清单上` });
  if (info.instalment) reasons.push({ code: "instalment", points: 10, en: "Paid in instalments / buy now pay later", zh: "分期或先买后付" });
  const pay = nextPayday(now, Number(s.payday));
  const days = Math.max(1, Math.ceil((pay - new Date(now.getFullYear(), now.getMonth(), now.getDate())) / 864e5));
  const left = Number(s.leftUntilPayday);
  const today = Math.round((left / days) * 100) / 100;
  if (today > 0 && amount > today * 3) reasons.push({ code: "budget", points: 15, en: "More than three days of your budget", zh: "超过三天的预算" });
  const score = Math.min(100, reasons.reduce((a, r) => a + r.points, 0));
  const band = score >= 70 ? "red" : score >= 40 ? "amber" : "green";
  const hold = s.nightHold && night && amount >= Number(s.nightThreshold)
    ? { item_id: null, until: iso(new Date(now.getTime() + Number(s.holdHours) * 3600e3)), rule: "night_hold", auto_saved: 0 } : null;
  const perGoalDay = Number(s.goalMonthly) / 30;
  return {
    offline: true, check_id: "off-" + Date.now().toString(36), title: info.title || "Online purchase", site: info.site,
    amount, currency: s.currency, base_currency: s.currency, symbol: SYMBOLS[s.currency] || "", amount_base: amount,
    category: "other", essential: false, risk: { score, band, reasons },
    hours_of_work: s.income > 0 ? Math.round((amount / (s.income / s.hours)) * 10) / 10 : null,
    days_of_budget: today > 0 ? Math.round((amount / today) * 10) / 10 : null,
    money: {
      safe_today_before: today, safe_today_after: Math.round((today - amount) * 100) / 100,
      left_until_payday_before: left, left_until_payday_after: Math.round((left - amount) * 100) / 100,
      per_day_after: Math.round(((left - amount) / days) * 100) / 100, days_to_payday: days,
      next_payday: iso(pay).slice(0, 10), goal_name: s.goalName,
      goal_delay_days: perGoalDay > 0 ? Math.round(amount / perGoalDay) : null, category_cap: null,
    },
    hold, countdown_seconds: hold ? 20 : band === "red" ? 10 : band === "amber" ? 5 : 3,
  };
}

async function offlineDecide(check, decision) {
  const store = await local();
  const s = await settings();
  if (decision === "bought") {
    store.history.push({ at: new Date().toISOString(), amount: check.amount });
    s.leftUntilPayday = Math.round((Number(s.leftUntilPayday) - check.amount) * 100) / 100;
    await chrome.storage.local.set({ settings: s });
  } else if (decision === "park") {
    const until = check.hold ? check.hold.until : iso(new Date(Date.now() + 24 * 3600e3));
    store.parked.push({ title: check.title, amount: check.amount, site: check.site, until });
    await chrome.storage.local.set({ parked: store.parked.slice(-50) });
    return { status: "ok", decision, hold_until: until, saved: 0, symbol: check.symbol };
  } else {
    await chrome.storage.local.set({ skippedTotal: store.skippedTotal + check.amount });
  }
  await chrome.storage.local.set({ history: store.history.slice(-50) });
  return { status: "ok", decision, saved: 0, symbol: check.symbol };
}

// ---- messages ---------------------------------------------------------------------------
async function handle(msg) {
  const s = await settings();
  if (msg.type === "settings") return { lang: s.lang, currency: s.currency, mode: s.mode };

  if (msg.type === "check") {
    const store = await local();
    const passedAt = store.passed[msg.info.siteKey];
    if (passedAt && Date.now() - passedAt < PASS_MINUTES * 60e3) return { pass: true };
    let result;
    try {
      result = await api(s, "/v1/checkout", {
        amount: msg.info.amount, currency: msg.info.currency, title: msg.info.title, site: msg.info.site,
        merchant: msg.info.shop || msg.info.site,
        livestream: msg.info.livestream, flash_sale: msg.info.flash_sale, instalment: msg.info.instalment,
        signals: msg.info.signals,
      });
    } catch (e) {
      result = { ...offlineCheck(msg.info, s, store), offline_reason: String(e.message || e) };
    }
    result.siteKey = msg.info.siteKey;
    if (s.mode === "risky" && result.risk.band === "green" && !result.hold) return { pass: true };
    return result;
  }

  if (msg.type === "decision") {
    const { check, decision } = msg;
    let out;
    if (check.offline) out = await offlineDecide(check, decision);
    else {
      try { out = await api(s, "/v1/decision", { check_id: check.check_id, decision }); }
      catch (e) { out = { status: "error", error: String(e.message || e) }; }
    }
    if (decision === "bought" && check.siteKey) {
      const store = await local();
      store.passed[check.siteKey] = Date.now();
      await chrome.storage.local.set({ passed: store.passed });
    }
    return out;
  }

  if (msg.type === "summary") {
    const store = await local();
    try {
      return { connected: true, ...(await api(s, "/v1/summary")), parkedOffline: store.parked.length, lang: s.lang };
    } catch (e) {
      const now = new Date();
      const pay = nextPayday(now, Number(s.payday));
      const days = Math.max(1, Math.ceil((pay - now) / 864e5));
      return { connected: false, reason: String(e.message || e), currency: s.currency, symbol: SYMBOLS[s.currency] || "",
        safe_to_spend_today: Math.round((s.leftUntilPayday / days) * 100) / 100, left_until_payday: Number(s.leftUntilPayday),
        days_to_payday: days, parked: store.parked.length, skipped_total: store.skippedTotal, lang: s.lang };
    }
  }

  if (msg.type === "test") {
    const trial = { ...s, api: msg.api || s.api, code: (msg.code || "").trim().toUpperCase() };
    try { return { ok: true, ...(await api(trial, "/v1/summary")) }; }
    catch (e) { return { ok: false, error: String(e.message || e) }; }
  }
  return { error: "unknown message" };
}

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  handle(msg).then(reply, (e) => reply({ error: String(e) }));
  return true;
});

chrome.runtime.onInstalled.addListener(async ({ reason }) => {
  if (reason === "install") {
    const { settings: s } = await chrome.storage.local.get("settings");
    if (!s) await chrome.storage.local.set({ settings: DEFAULTS });
  }
});
