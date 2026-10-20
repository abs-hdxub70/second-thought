const FIELDS = ["lang", "api", "code", "mode", "currency", "leftUntilPayday", "payday", "income", "hours", "goalName",
  "goalMonthly", "nightThreshold", "nightStart", "nightEnd", "triggers"];
const NUM = new Set(["leftUntilPayday", "payday", "income", "hours", "goalMonthly", "nightThreshold"]);
const $ = (id) => document.getElementById(id);

async function load() {
  const { settings } = await chrome.storage.local.get("settings");
  for (const f of FIELDS) if (settings && settings[f] !== undefined) $(f).value = settings[f];
}
async function save() {
  const { settings } = await chrome.storage.local.get("settings");
  const next = { ...(settings || {}) };
  for (const f of FIELDS) next[f] = NUM.has(f) ? Number($(f).value) : $(f).value.trim();
  next.code = next.code.toUpperCase();
  await chrome.storage.local.set({ settings: next });
  $("saved").textContent = "Saved · 已保存";
  setTimeout(() => { $("saved").textContent = ""; }, 2000);
}
$("save").onclick = save;
$("test").onclick = async () => {
  $("result").textContent = "…";
  const r = await chrome.runtime.sendMessage({ type: "test", api: $("api").value.trim(), code: $("code").value });
  $("result").innerHTML = r.ok
    ? `<span class="ok">Connected · 已连接</span> – ${r.name || ""} · ${r.currency || ""} · ${r.symbol || ""}${Math.round(r.safe_to_spend_today || 0)} safe to spend today`
    : `<span class="warn">Not connected · 未连接</span> – ${r.error}`;
  if (r.ok) save();
};
load();
