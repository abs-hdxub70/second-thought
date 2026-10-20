// Checkout Pause: intercepts the click on a checkout button and asks twice before letting it through.
// Step 1: "Do you really want to buy this?" with the reasons to wait.
// Step 2: the second warning, how much money is left afterwards, with a short countdown.
(() => {
  if (globalThis.__secondThoughtLoaded) return;
  globalThis.__secondThoughtLoaded = true;
  const D = globalThis.STDetect;

  const T = {
    en: {
      brand: "Second Thought", ask: "Do you really want to buy this now?", checking: "Checking with your plan…",
      noAmount: "How much is it?", amountHint: "We could not read the price on this page.", go: "Check",
      risk: "impulse risk", band: { red: "High", amber: "Medium", green: "Low" }, why: "Why it may be worth waiting",
      noReasons: "Nothing unusual. Still, a short pause never hurts.",
      hours: (h) => `That is about ${h} hours of your work.`,
      days: (d) => `Or ${d} days of today's safe-to-spend.`,
      hold: (until, saved, pot) => `Your own night rule holds this until ${until}.` + (saved ? ` ${saved} went to ${pot}.` : ""),
      holdRule: "Your rule", park: "Park it for 24 h", keep: "Keep it parked", skip: "Don't buy",
      next: "Yes, continue", second: "Second check: what is left after this",
      today: "Safe to spend today", untilPayday: (date, d) => `Until payday (${date}, ${d} days)`,
      perDay: (a, b) => `${a} a day instead of ${b}`, cap: (c) => `Your ${c} cap this month`, left: "left",
      goal: (g) => `${g}`, delay: (n) => `pushes it back by ${n} days`,
      halt: "Are you hungry, angry, lonely or tired right now?", buy: "Buy anyway", override: "Override my rule",
      parked: (until) => `Parked. Look at it again ${until}.`, saved: (a, p) => `${a} moved to ${p}.`,
      skipped: "Good call. Nothing was bought.", bought: "OK, your call. Logged, no judgement.",
      offline: "Offline: not connected to the app, using the numbers in the extension settings.",
      close: "Close", edit: "edit", essential: "Looks like an essential. No hold.",
    },
    zh: {
      brand: "再想想", ask: "真的现在就要买吗？", checking: "正在对照你的计划…",
      noAmount: "这件多少钱？", amountHint: "这个页面上没读到价格。", go: "检查",
      risk: "冲动风险", band: { red: "高", amber: "中", green: "低" }, why: "为什么值得等一等",
      noReasons: "没有异常。不过停一下总没坏处。",
      hours: (h) => `大约相当于你 ${h} 小时的工作。`,
      days: (d) => `或者今天可安心花费的 ${d} 天。`,
      hold: (until, saved, pot) => `你自己设的夜间规则把它暂缓到 ${until}。` + (saved ? `已把 ${saved} 存进「${pot}」。` : ""),
      holdRule: "你的规则", park: "放进等待区 24 小时", keep: "继续放着", skip: "不买了",
      next: "是的，继续", second: "第二次确认：买完还剩多少",
      today: "今天可安心花费", untilPayday: (date, d) => `到发薪日（${date}，还有 ${d} 天）`,
      perDay: (a, b) => `每天 ${a}，原本 ${b}`, cap: (c) => `本月「${c}」上限`, left: "剩余",
      goal: (g) => `「${g}」`, delay: (n) => `推迟 ${n} 天`,
      halt: "你现在是不是饿了、生气、孤单或累了？", buy: "还是要买", override: "忽略我的规则",
      parked: (until) => `已放进等待区，${until} 再看。`, saved: (a, p) => `已把 ${a} 存进「${p}」。`,
      skipped: "好决定，什么都没买。", bought: "好的，你说了算。已记录，不评判。",
      offline: "离线：未连接应用，使用扩展设置里的数字。",
      close: "关闭", edit: "修改", essential: "看起来是必需品，不暂缓。",
    },
  };
  const CATEGORY_ZH = { clothing: "服饰", beauty: "美妆", electronics: "数码", food: "餐饮", household: "日用", other: "其他" };

  let host = null, root = null, open = false, bypass = false, lang = "en", timer = null;

  function money(v, sym, l) {
    if (v === null || v === undefined || Number.isNaN(v)) return "–";
    const n = Math.abs(v).toLocaleString(l === "zh" ? "zh-CN" : "en-US", { maximumFractionDigits: Math.abs(v) >= 100 ? 0 : 2 });
    return (v < 0 ? "−" : "") + (sym || "") + n;
  }
  function when(iso, l) {
    if (!iso) return "";
    const d = new Date(iso);
    const t = d.toLocaleTimeString(l === "zh" ? "zh-CN" : "en-GB", { hour: "2-digit", minute: "2-digit" });
    const day = d.toLocaleDateString(l === "zh" ? "zh-CN" : "en-GB", { month: "short", day: "numeric" });
    return `${day} ${t}`;
  }
  function esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  }
  function isOwn(el) { return host && (el === host || host.contains(el)); }

  async function send(msg) {
    try { return await chrome.runtime.sendMessage(msg); } catch (e) { return { error: String(e) }; }
  }

  // ---- interception ---------------------------------------------------------------------
  function intercept(e, el, replay) {
    e.preventDefault();
    e.stopPropagation();
    e.stopImmediatePropagation();
    if (!open) start(el, replay);
  }
  window.addEventListener("click", (e) => {
    if (bypass || !e.isTrusted || open && isOwn(e.target)) return;
    const path = e.composedPath ? e.composedPath() : [];
    if (path.includes(host)) return;
    const el = D.findCheckoutElement(e.target, isOwn);
    if (!el) return;
    intercept(e, el, () => { bypass = true; try { el.click(); } finally { setTimeout(() => { bypass = false; }, 0); } });
  }, true);
  document.addEventListener("submit", (e) => {
    if (bypass) return;
    const sub = e.submitter;
    if (!sub || !D.isCheckoutLabel(sub.value || sub.innerText || "")) return;
    const form = e.target;
    intercept(e, sub, () => { bypass = true; try { form.requestSubmit(sub); } finally { setTimeout(() => { bypass = false; }, 0); } });
  }, true);

  // ---- overlay -----------------------------------------------------------------------------
  const CSS = `
  :host { all: initial; }
  .back { position: fixed; inset: 0; background: rgba(16,32,43,.55); display: flex; align-items: center; justify-content: center;
    z-index: 2147483647; font-family: -apple-system, "Segoe UI", "PingFang SC", "Microsoft YaHei", "Noto Sans SC", Roboto, Arial, sans-serif; }
  .card { width: min(460px, calc(100vw - 32px)); max-height: calc(100vh - 32px); overflow: auto; background: #F6F4EF; color: #1E2B33;
    border-radius: 18px; box-shadow: 0 24px 64px rgba(0,0,0,.35); padding: 22px 24px 20px; box-sizing: border-box; }
  .top { display: flex; align-items: center; gap: 10px; font-size: 13px; letter-spacing: .08em; text-transform: uppercase; color: #2F6F68; font-weight: 700; }
  .top .x { margin-left: auto; background: none; border: 0; font-size: 22px; line-height: 1; color: #7A8A94; cursor: pointer; padding: 0 4px; }
  .logo { width: 22px; height: 22px; border-radius: 50%; background: #2F6F68; display: inline-flex; align-items: center; justify-content: center; gap: 3px; }
  .logo i { width: 3px; height: 9px; background: #F6F4EF; border-radius: 2px; display: block; }
  h2 { font-family: Georgia, "Songti SC", "Noto Serif SC", serif; font-size: 25px; line-height: 1.2; margin: 14px 0 6px; color: #10202B; font-weight: 600; }
  .item { font-size: 14px; color: #3E4C59; margin-bottom: 14px; }
  .item b { color: #10202B; }
  .item button { background: none; border: 0; color: #2F6F68; text-decoration: underline; cursor: pointer; font-size: 13px; padding: 0 0 0 6px; }
  .score { display: flex; align-items: center; gap: 14px; background: #FDFCF9; border: 1px solid #E2E4DE; border-radius: 14px; padding: 12px 14px; }
  .ring { --c: #2F6F68; width: 58px; height: 58px; border-radius: 50%; flex: none; display: flex; align-items: center; justify-content: center;
    background: conic-gradient(var(--c) calc(var(--p) * 1%), #E2E4DE 0); }
  .ring span { width: 44px; height: 44px; border-radius: 50%; background: #FDFCF9; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 17px; color: #10202B; }
  .red { --c: #B4432F; } .amber { --c: #C98A1B; } .green { --c: #2F6F68; }
  .score p { margin: 0; font-size: 15px; font-weight: 700; color: #10202B; }
  .score small { font-size: 13px; color: #5A6872; font-weight: 400; }
  h3 { font-size: 14px; margin: 16px 0 6px; color: #10202B; }
  ul { margin: 0; padding: 0; list-style: none; }
  li { display: flex; justify-content: space-between; gap: 10px; font-size: 14px; line-height: 1.35; padding: 6px 0; border-bottom: 1px solid #E8E6E0; color: #1E2B33; }
  li em { font-style: normal; color: #B4432F; font-weight: 700; white-space: nowrap; }
  .note { font-size: 14px; color: #3E4C59; margin: 10px 0 0; line-height: 1.4; }
  .rule { margin-top: 12px; background: #EAF1EE; border-left: 4px solid #2F6F68; padding: 10px 12px; border-radius: 8px; font-size: 14px; line-height: 1.4; }
  .rule b { color: #2F6F68; }
  .off { margin-top: 10px; font-size: 12px; color: #7A5A12; background: #FBF1DC; border-radius: 8px; padding: 6px 10px; }
  .rows { display: grid; gap: 10px; margin-top: 4px; }
  .row { background: #FDFCF9; border: 1px solid #E2E4DE; border-radius: 12px; padding: 10px 14px; }
  .row .k { font-size: 13px; color: #5A6872; }
  .row .v { font-size: 20px; font-weight: 700; color: #10202B; margin-top: 2px; }
  .row .v .arrow { color: #7A8A94; font-weight: 400; padding: 0 6px; }
  .row .v .neg { color: #B4432F; }
  .row .s { font-size: 13px; color: #3E4C59; margin-top: 2px; }
  .halt { margin-top: 12px; font-size: 14px; color: #3E4C59; font-style: italic; }
  .btns { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 18px; }
  .btns button { font: inherit; font-size: 15px; border-radius: 999px; padding: 10px 16px; cursor: pointer; border: 1px solid #2F6F68; }
  .primary { background: #2F6F68; color: #fff; font-weight: 700; flex: 1 1 100%; }
  .secondary { background: #FDFCF9; color: #2F6F68; flex: 1 1 40%; }
  .ghost { background: transparent; color: #5A6872; border-color: #C9CDC6 !important; flex: 1 1 40%; }
  .ghost:disabled { color: #A3ADB3; cursor: not-allowed; }
  input.amt { font: inherit; font-size: 18px; padding: 8px 10px; border-radius: 10px; border: 1px solid #C9CDC6; width: 160px; }
  .done { font-size: 16px; line-height: 1.45; margin: 16px 0 4px; color: #10202B; }
  .spin { width: 28px; height: 28px; border: 3px solid #D5E2DC; border-top-color: #2F6F68; border-radius: 50%; animation: s 1s linear infinite; margin: 18px auto; }
  @keyframes s { to { transform: rotate(360deg); } }
  `;

  function mount() {
    host = document.createElement("second-thought-pause");
    root = host.attachShadow({ mode: "open" });
    root.innerHTML = `<style>${CSS}</style><div class="back" role="dialog" aria-modal="true" aria-labelledby="st-h"><div class="card"></div></div>`;
    (document.body || document.documentElement).appendChild(host);
    root.addEventListener("keydown", (e) => { if (e.key === "Escape") close(); });
    open = true;
  }
  function close() {
    clearInterval(timer);
    if (host) host.remove();
    host = root = null;
    open = false;
  }
  function card(html) {
    const c = root.querySelector(".card");
    const t = T[lang];
    c.innerHTML = `<div class="top"><span class="logo"><i></i><i></i></span>${esc(lang === "zh" ? "再想想 · Second Thought" : "Second Thought · 再想想")}<button class="x" data-a="close" aria-label="${esc(t.close)}">×</button></div>${html}`;
    c.querySelector('[data-a="close"]').onclick = close;
    const first = c.querySelector(".primary");
    if (first) first.focus();
    return c;
  }

  async function start(el, replay) {
    const settings = (await send({ type: "settings" })) || {};
    const info = {
      site: location.hostname.replace(/^www\./, ""), siteKey: D.siteKey(location.hostname),
      title: D.findTitle(document), shop: D.findShopName(document), ...D.findAmount(document, el),
    };
    const sig = D.findSignals(document);
    info.livestream = sig.livestream; info.flash_sale = sig.flash_sale; info.instalment = sig.instalment; info.signals = sig.words.join(" ");
    info.currency = info.currency || D.currencyForHost(location.hostname) || settings.currency || "CNY";
    lang = settings.lang && settings.lang !== "auto" ? settings.lang : D.pageLanguage(document, location.hostname, navigator.language);
    mount();
    if (!info.amount) return askAmount(info, replay);
    check(info, replay);
  }

  function askAmount(info, replay) {
    const t = T[lang];
    const c = card(`<h2 id="st-h">${esc(t.noAmount)}</h2><p class="item">${esc(info.title)}<br>${esc(t.amountHint)}</p>
      <input class="amt" type="number" min="0" step="0.01" inputmode="decimal" aria-label="${esc(t.noAmount)}"> ${esc(info.currency)}
      <div class="btns"><button class="primary" data-a="go">${esc(t.go)}</button></div>`);
    const input = c.querySelector("input");
    input.focus();
    const go = () => { const v = parseFloat(input.value); if (v > 0) { info.amount = v; check(info, replay); } };
    c.querySelector('[data-a="go"]').onclick = go;
    input.onkeydown = (e) => { if (e.key === "Enter") go(); };
  }

  async function check(info, replay) {
    const t = T[lang];
    card(`<h2 id="st-h">${esc(t.ask)}</h2><div class="spin"></div><p class="note" style="text-align:center">${esc(t.checking)}</p>`);
    const res = await send({ type: "check", info });
    if (!res || res.error) {
      // the extension itself is unavailable: still ask once, without numbers
      const c = card(`<h2 id="st-h">${esc(t.ask)}</h2><p class="item"><b>${esc(info.title)}</b> · ${esc(money(info.amount, "", lang))} ${esc(info.currency)}</p>
        <div class="btns"><button class="primary" data-a="skip">${esc(t.skip)}</button><button class="ghost" data-a="buy">${esc(t.buy)}</button></div>`);
      c.querySelector('[data-a="skip"]').onclick = close;
      c.querySelector('[data-a="buy"]').onclick = () => { close(); replay(); };
      return;
    }
    if (res.pass) { close(); replay(); return; }
    step1(info, res, replay);
  }

  function step1(info, r, replay) {
    const t = T[lang];
    const sym = r.symbol || "";
    const band = r.risk.band;
    const reasons = r.risk.reasons.map((x) => `<li><span>${esc(lang === "zh" ? x.zh : x.en)}</span><em>+${x.points}</em></li>`).join("");
    const extra = [r.hours_of_work ? t.hours(r.hours_of_work) : "", r.days_of_budget ? t.days(r.days_of_budget) : ""].filter(Boolean).join(" ");
    const hold = r.hold ? `<div class="rule"><b>${esc(t.holdRule)}:</b> ${esc(t.hold(when(r.hold.until, lang), r.hold.auto_saved ? money(r.hold.auto_saved, sym, lang) : "", r.money.goal_name || ""))}</div>` : "";
    const shown = r.currency !== r.base_currency ? `${money(r.amount, "", lang)} ${r.currency} (${money(r.amount_base, sym, lang)})` : money(r.amount, sym, lang);
    const c = card(`
      <h2 id="st-h">${esc(t.ask)}</h2>
      <p class="item"><b>${esc(r.title)}</b> · ${esc(shown)}<button data-a="edit">${esc(t.edit)}</button></p>
      <div class="score"><div class="ring ${band}" style="--p:${r.risk.score}"><span>${r.risk.score}</span></div>
        <div><p>${esc(t.band[band])} ${esc(t.risk)} <small>· ${r.risk.score}/100</small></p><small>${esc(info.shop || r.site || "")}</small></div></div>
      <h3>${esc(t.why)}</h3>
      ${reasons ? `<ul>${reasons}</ul>` : `<p class="note">${esc(r.essential ? t.essential : t.noReasons)}</p>`}
      ${extra ? `<p class="note">${esc(extra)}</p>` : ""}
      ${hold}
      ${r.offline ? `<div class="off">${esc(t.offline)}</div>` : ""}
      <div class="btns">
        <button class="primary" data-a="park">${esc(r.hold ? t.keep : t.park)}</button>
        <button class="secondary" data-a="skip">${esc(t.skip)}</button>
        <button class="ghost" data-a="next">${esc(t.next)} →</button>
      </div>`);
    c.querySelector('[data-a="edit"]').onclick = () => askAmount({ ...info, amount: null }, replay);
    c.querySelector('[data-a="park"]').onclick = () => decide(r, "park", replay);
    c.querySelector('[data-a="skip"]').onclick = () => decide(r, "skip", replay);
    c.querySelector('[data-a="next"]').onclick = () => step2(info, r, replay);
  }

  function step2(info, r, replay) {
    const t = T[lang];
    const sym = r.symbol || "";
    const m = r.money;
    const v = (a, b) => `${esc(money(a, sym, lang))}<span class="arrow">→</span><span class="${b < 0 ? "neg" : ""}">${esc(money(b, sym, lang))}</span>`;
    const cap = m.category_cap ? `<div class="row"><div class="k">${esc(t.cap(lang === "zh" ? CATEGORY_ZH[m.category_cap.category] || m.category_cap.category : m.category_cap.category))} · ${esc(money(m.category_cap.cap, sym, lang))}</div>
      <div class="v">${v(m.category_cap.left, m.category_cap.left_after)} <small style="font-size:13px;font-weight:400;color:#5A6872">${esc(t.left)}</small></div></div>` : "";
    const goal = m.goal_name && m.goal_delay_days ? `<div class="row"><div class="k">${esc(t.goal(m.goal_name))}</div><div class="v">${esc(t.delay(m.goal_delay_days))}</div></div>` : "";
    const c = card(`
      <h2 id="st-h">${esc(t.second)}</h2>
      <p class="item"><b>${esc(r.title)}</b> · ${esc(money(r.amount_base, sym, lang))}</p>
      <div class="rows">
        <div class="row"><div class="k">${esc(t.today)}</div><div class="v">${v(m.safe_today_before, m.safe_today_after)}</div></div>
        <div class="row"><div class="k">${esc(t.untilPayday(m.next_payday, m.days_to_payday))}</div><div class="v">${v(m.left_until_payday_before, m.left_until_payday_after)}</div>
          <div class="s">${esc(t.perDay(money(m.per_day_after, sym, lang), money(m.safe_today_before, sym, lang)))}</div></div>
        ${cap}${goal}
      </div>
      ${r.risk.band !== "green" ? `<p class="halt">${esc(t.halt)}</p>` : ""}
      ${r.offline ? `<div class="off">${esc(t.offline)}</div>` : ""}
      <div class="btns">
        <button class="primary" data-a="park">${esc(r.hold ? t.keep : t.park)}</button>
        <button class="secondary" data-a="skip">${esc(t.skip)}</button>
        <button class="ghost" data-a="buy" disabled>${esc(r.hold ? t.override : t.buy)}</button>
      </div>`);
    c.querySelector('[data-a="park"]').onclick = () => decide(r, "park", replay);
    c.querySelector('[data-a="skip"]').onclick = () => decide(r, "skip", replay);
    const buy = c.querySelector('[data-a="buy"]');
    const label = r.hold ? t.override : t.buy;
    let left = Math.max(0, r.countdown_seconds | 0);
    const tick = () => {
      if (left <= 0) { clearInterval(timer); buy.disabled = false; buy.textContent = label; return; }
      buy.textContent = `${label} (${left})`;
      left -= 1;
    };
    tick();
    clearInterval(timer);
    timer = setInterval(tick, 1000);
    buy.onclick = () => decide(r, "bought", replay);
  }

  async function decide(r, decision, replay) {
    const t = T[lang];
    clearInterval(timer);
    const out = (await send({ type: "decision", check: r, decision })) || {};
    if (decision === "bought") {
      card(`<p class="done">${esc(t.bought)}</p>`);
      setTimeout(() => { close(); replay(); }, 900);
      return;
    }
    const sym = out.symbol || r.symbol || "";
    const saved = out.saved ? " " + t.saved(money(out.saved, sym, lang), out.pot || r.money.goal_name || "") : "";
    const msg = decision === "park" ? t.parked(when(out.hold_until || (r.hold && r.hold.until), lang)) + saved : t.skipped + saved;
    const c = card(`<p class="done">${esc(msg)}</p><div class="btns"><button class="primary" data-a="close2">${esc(t.close)}</button></div>`);
    c.querySelector('[data-a="close2"]').onclick = close;
  }
})();
