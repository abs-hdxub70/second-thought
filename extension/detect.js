// Finds checkout buttons, the order amount, the product title and shopping signals on a page.
// Pure functions on the DOM, no network. Exposed as globalThis.STDetect for content.js and tests.
(() => {
  const CHECKOUT_PATTERNS = [
    /^(立即购买|立即下单|提交订单|去结算|结算|立即支付|确认支付|确认付款|去支付|立即付款|立即抢购|马上抢|一键购买|领券购买|确认购买|去付款)$/,
    /^(buy now|buy it now|place (your )?order|pay now|check ?out|proceed to check ?out|complete (your )?(order|purchase)|confirm (and|&) pay|submit order|continue to payment|pay)$/i,
    /^(jetzt kaufen|zur kasse( gehen)?|weiter zur kasse|kaufen|zahlungspflichtig bestellen|jetzt bezahlen|bestellung abschicken|kauf abschlie(ß|ss)en|jetzt kaufen und bezahlen)$/i,
  ];
  const TOTAL_LABEL = /(实付款|实付|应付总额|应付金额|应付|合计|总计|订单总额|需付款|order total|grand total|estimated total|total due|amount due|you pay|^total|gesamtsumme|gesamtbetrag|gesamtpreis|zu zahlen|^summe)/i;
  const PRICE_RE = /([¥￥€$£])\s?(\d[\d.,\s]*\d|\d)|(\d[\d.,\s]*\d|\d)\s?(元|€|EUR|CNY|RMB|USD|GBP)/g;
  const SYMBOL_CURRENCY = { "¥": "CNY", "￥": "CNY", "元": "CNY", "CNY": "CNY", "RMB": "CNY", "€": "EUR", "EUR": "EUR",
    "$": "USD", "USD": "USD", "£": "GBP", "GBP": "GBP" };
  const SIGNALS = {
    livestream: ["直播", "直播间", "主播", "live shopping", "livestream", "live now", "LIVE"],
    flash: ["秒杀", "限时", "倒计时", "抢购", "flash sale", "ends in", "deal ends", "nur heute", "blitzangebot", "only today"],
    instalment: ["花呗", "分期", "白条", "klarna", "afterpay", "pay in 4", "pay later", "ratenzahlung", "ratenkauf", "später bezahlen"],
  };

  function normalise(text) {
    return String(text || "")
      .replace(/[¥￥€$£]\s?[\d.,\s]+/g, " ")
      .replace(/[\d.,]+\s?(元|€)/g, " ")
      .replace(/\d+/g, " ")
      .replace(/[()（）\[\]【】:：|·•>»›→←!！?？*]+/g, " ")
      .replace(/\s+/g, " ")
      .trim()
      .toLowerCase();
  }

  function labelOf(el) {
    if (!el || el.nodeType !== 1) return "";
    if (el.tagName === "INPUT") return el.value || el.getAttribute("aria-label") || "";
    const aria = el.getAttribute("aria-label");
    const text = (el.innerText !== undefined ? el.innerText : el.textContent) || "";
    return text.trim() ? text : aria || "";
  }

  function isCheckoutLabel(raw) {
    if (!raw || raw.length > 60) return false;
    const text = normalise(raw);
    if (!text || text.length > 30) return false;
    return CHECKOUT_PATTERNS.some((re) => re.test(text));
  }

  // Walk up from the clicked node to the element that carries a checkout label.
  function findCheckoutElement(start, isOwn) {
    let el = start && start.nodeType === 3 ? start.parentElement : start;
    for (let depth = 0; el && depth < 6; depth++, el = el.parentElement) {
      if (isOwn && isOwn(el)) return null;
      if (el.tagName === "BODY" || el.tagName === "HTML") return null;
      if (isCheckoutLabel(labelOf(el))) {
        // prefer the link or button that wraps the label, so the replayed click does what the shop expects
        const norm = normalise(labelOf(el));
        let best = el;
        for (let p = el.parentElement, k = 0; p && k < 3; p = p.parentElement, k++) {
          if (normalise(labelOf(p)) !== norm) break;
          if (p.tagName === "A" || p.tagName === "BUTTON" || p.getAttribute("role") === "button") best = p;
        }
        return best;
      }
    }
    return null;
  }

  function parseNumber(s) {
    s = String(s).replace(/\s/g, "");
    const dot = s.lastIndexOf("."), comma = s.lastIndexOf(",");
    let dec = -1;
    if (dot >= 0 && comma >= 0) dec = Math.max(dot, comma);
    else if (dot >= 0 || comma >= 0) {
      const i = Math.max(dot, comma);
      if (s.length - i - 1 <= 2) dec = i;
    }
    const intPart = (dec >= 0 ? s.slice(0, dec) : s).replace(/[.,]/g, "");
    const frac = dec >= 0 ? s.slice(dec + 1) : "";
    const n = parseFloat(intPart + (frac ? "." + frac : ""));
    return Number.isFinite(n) ? n : null;
  }

  function pricesIn(text) {
    const out = [];
    PRICE_RE.lastIndex = 0;
    let m;
    while ((m = PRICE_RE.exec(text)) !== null) {
      const sym = m[1] || m[4];
      const amount = parseNumber(m[2] || m[3]);
      if (amount && amount > 0 && amount < 10000000) out.push({ amount, currency: SYMBOL_CURRENCY[sym] || null });
    }
    return out;
  }

  function currencyForHost(host) {
    if (/\.cn$|taobao|tmall|jd\.com|pinduoduo|yangkeduo|vip\.com|suning|douyin|kuaishou|xiaohongshu/.test(host)) return "CNY";
    if (/\.co\.uk$/.test(host)) return "GBP";
    if (/\.(de|fr|it|es|nl|at|be|ie|pt|fi)$/.test(host)) return "EUR";
    return null;
  }

  function isStruck(el) {
    for (let e = el; e && e.nodeType === 1; e = e.parentElement) {
      if (e.tagName === "DEL" || e.tagName === "S") return true;
      if (/original|old-price|was-price|strike|line-through/i.test(e.className || "")) return true;
    }
    return false;
  }

  function findAmount(doc, button) {
    const body = doc.body;
    // 1. a "total" label on checkout pages (last one wins, totals sit at the bottom)
    const lines = ((body && body.innerText) || "").split(/\n+/).map((l) => l.trim()).filter(Boolean);
    let fromTotal = null;
    for (let i = 0; i < lines.length; i++) {
      if (TOTAL_LABEL.test(lines[i])) {
        const p = pricesIn(lines[i])[0] || (lines[i + 1] ? pricesIn(lines[i + 1])[0] : null);
        if (p) fromTotal = { ...p, how: "total" };
      }
    }
    if (fromTotal) return fromTotal;
    // 2. structured product data
    const meta = doc.querySelector('[itemprop="price"][content], meta[property="product:price:amount"], meta[property="og:price:amount"]');
    if (meta) {
      const amount = parseNumber(meta.getAttribute("content"));
      const curEl = doc.querySelector('[itemprop="priceCurrency"][content], meta[property="product:price:currency"]');
      if (amount) return { amount, currency: curEl ? curEl.getAttribute("content") : null, how: "structured" };
    }
    // 3. price elements near the button, skipping crossed-out prices
    for (let el = button, depth = 0; el && depth < 8; depth++, el = el.parentElement) {
      const nodes = el.querySelectorAll ? el.querySelectorAll('[class*="price" i], [id*="price" i], [data-price]') : [];
      for (const n of nodes) {
        if (isStruck(n)) continue;
        const p = pricesIn(n.innerText || n.getAttribute("data-price") || "")[0];
        if (p) return { ...p, how: "near" };
      }
      const p = pricesIn((el.innerText || "").slice(0, 3000))[0];
      if (p && depth >= 1) return { ...p, how: "text" };
    }
    return { amount: null, currency: null, how: "none" };
  }

  function findTitle(doc) {
    const og = doc.querySelector('meta[property="og:title"]');
    const named = doc.querySelector('[itemprop="name"]');
    const h1 = doc.querySelector("h1");
    let t = (og && og.getAttribute("content")) || (named && named.textContent) || (h1 && h1.innerText) || doc.title || "";
    t = t.split(/\s[-–|]\s|-淘宝网|-tmall|【.*?】/i)[0];
    return t.replace(/\s+/g, " ").trim().slice(0, 120);
  }

  function findShopName(doc) {
    const m = doc.querySelector('meta[property="og:site_name"], meta[name="application-name"]');
    return m ? String(m.getAttribute("content") || "").trim().slice(0, 60) : "";
  }

  function findSignals(doc) {
    const text = (((doc.body && doc.body.innerText) || "") + " " + doc.title).slice(0, 30000);
    const low = text.toLowerCase();
    const found = { livestream: false, flash_sale: false, instalment: false, words: [] };
    for (const [kind, words] of Object.entries(SIGNALS)) {
      for (const w of words) {
        const hit = w === "LIVE" ? /\bLIVE\b/.test(text) : low.includes(w.toLowerCase());
        if (hit) {
          found[kind === "flash" ? "flash_sale" : kind] = true;
          if (!found.words.includes(w)) found.words.push(w);
        }
      }
    }
    return found;
  }

  function pageLanguage(doc, host, nav) {
    const lang = (doc.documentElement.getAttribute("lang") || "").toLowerCase();
    if (lang.startsWith("zh")) return "zh";
    if (currencyForHost(host) === "CNY") return "zh";
    if (lang) return "en";
    return String(nav || "").toLowerCase().startsWith("zh") ? "zh" : "en";
  }

  function siteKey(host) {
    const parts = host.replace(/^www\./, "").split(".");
    const two = parts.slice(-2).join(".");
    return /^(co|com|org|net)\.(uk|cn|jp|au)$/.test(two) ? parts.slice(-3).join(".") : two;
  }

  globalThis.STDetect = { normalise, isCheckoutLabel, findCheckoutElement, parseNumber, pricesIn, findAmount,
    findTitle, findShopName, findSignals, currencyForHost, pageLanguage, siteKey };
})();
