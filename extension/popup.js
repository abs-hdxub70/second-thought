const ZH = { "Safe to spend today": "今天可安心花费", "Left until payday": "到发薪日还剩", "Parked purchases": "等待区",
  "Checkout buttons on shopping sites now ask once more before you pay.": "购物网站的结账按钮会在付款前再问你一次。",
  "Settings and pairing": "设置与配对" };
const fmt = (v, sym) => (v < 0 ? "−" : "") + (sym || "") + Math.abs(Number(v)).toLocaleString(undefined, { maximumFractionDigits: 0 });
chrome.runtime.sendMessage({ type: "summary" }).then((s) => {
  const zh = s.lang === "zh" || (s.lang !== "en" && navigator.language.startsWith("zh"));
  if (zh) for (const id of ["l-today", "l-left", "l-parked", "hint", "opts"]) {
    const el = document.getElementById(id); el.textContent = ZH[el.textContent] || el.textContent;
  }
  const st = document.getElementById("status");
  if (s.connected && s.ready) {
    st.innerHTML = `<span class="ok">● ${zh ? "已连接应用" : "Connected to the app"}</span> · ${s.name || ""}`;
  } else if (s.connected) {
    st.textContent = s.message;
  } else {
    st.innerHTML = `<span class="warn">● ${zh ? "离线模式" : "Offline mode"}</span> · ${zh ? "使用扩展设置里的数字" : "using the numbers in settings"}`;
  }
  document.getElementById("today").textContent = fmt(s.safe_to_spend_today ?? 0, s.symbol);
  document.getElementById("left").textContent = fmt(s.left_until_payday ?? 0, s.symbol);
  document.getElementById("parked").textContent = String((s.parked || 0) + (s.parkedOffline || 0));
});
