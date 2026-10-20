"""Second Thought (再想想) - Streamlit app.

Run:  streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, time
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from second_thought.agent import Assistant, Toolbox  # noqa: E402
from second_thought.agent.router import money  # noqa: E402
from second_thought.connectors import REGISTRY  # noqa: E402
from second_thought.demo import load_demo  # noqa: E402
from second_thought.engine.categories import ESSENTIAL_CATEGORIES  # noqa: E402
from second_thought.policy import plan as plan_rules  # noqa: E402
from second_thought.policy.gate import TIER_LABELS  # noqa: E402
from second_thought.policy.plan import CalmPlan  # noqa: E402
from second_thought.state import DEFAULT_ROOT, AppState  # noqa: E402

st.set_page_config(page_title="Second Thought 再想想", page_icon="⏸", layout="wide")

# ---------------------------------------------------------------- i18n
T = {
    "en": {
        "tagline": "A pause between the urge and the payment.",
        "lang": "Language", "region": "Data region", "region_help": "Data is stored separately per region (data residency).",
        "demo": "Load demo persona (Mei)", "reset": "Reset this region", "clock": "Demo clock",
        "use_clock": "Use a simulated time (for demos)", "sources": "Connect data",
        "alipay": "Alipay bill (CSV)", "wechat": "WeChat Pay bill (CSV or XLSX)", "unionpay": "UnionPay statement (mock JSON)",
        "plaid": "Plaid sandbox fixture (JSON)", "plaid_live": "Pull from Plaid Sandbox (live)", "agent": "Assistant",
        "today": "Today", "bills": "Bills", "parking": "Parking & returns", "mirror": "Money mirror",
        "plan": "Plan & safety", "txns": "Transactions",
        "safe": "Safe to spend today", "payday": "next payday", "breakdown": "How this is calculated",
        "pause": "The Pause", "pause_help": "Thinking about buying something? Run it past us first.",
        "what": "What is it?", "amount": "Amount", "currency": "Currency", "category": "Category",
        "live": "Live stream", "flash": "Flash sale", "inst": "Instalments",
        "check": "Check it", "score": "Impulse score", "hours": "hours of your work", "days": "days of today's budget",
        "park": "Park it for 24h", "skip": "Skip it", "buy": "Buy anyway", "why_buy": "Reason (optional, just for you)",
        "chat": "Ask Second Thought", "chat_ph": "e.g. Should I buy a ¥899 jacket?  /  要不要买 899 元的外套？",
        "confirm": "Confirm", "dismiss": "Dismiss", "waiting": "Waiting for your confirmation",
        "subs": "Subscriptions", "per_month": "per month", "fees": "Fees in the last 90 days", "adhd_tax": "Avoidable costs (\"ADHD tax\"), 90 days",
        "draft_cancel": "Draft cancellation", "drafts": "Drafts (never sent automatically)", "instalments": "Open instalments",
        "returns": "Return windows", "draft_return": "Draft return request", "parked": "Parked purchases",
        "review": "Ready to review", "bought": "I bought it", "skipped": "Skip it", "extend": "+24h",
        "mood": "Mood check-in", "mood_l": "Mood (1 low - 5 good)", "stress_l": "Stress (1 calm - 5 high)", "note": "Note (optional)",
        "save": "Save", "rec": "This week's suggestion",
        "calm_plan": "Calm-state plan", "calm_help": "Rules you set while calm. Safer changes apply now; riskier ones wait 24 hours.",
        "apply": "Save changes", "queued": "Queued changes (24-hour cooldown)", "cancel": "Cancel",
        "ally": "Trusted ally", "unsafe": "I feel unsafe - remove my ally now", "tiers": "Permission tiers",
        "audit": "Audit log", "verify": "Verify hash chain", "download": "Download audit log",
        "sandbox_ops": "Sandbox operations", "outbox": "Ally outbox (sandbox, nothing is sent)",
        "onboard": "Set up", "onboard_help": "Pick what sounds like you. We never ask for a diagnosis.",
        "consent_fin": "I agree that Second Thought processes my imported financial data (separate consent, PIPL / GDPR).",
        "consent_llm": "Allow sending redacted data to a language model (optional; offline agent otherwise).",
        "start": "Start", "or_demo": "Or load the demo persona from the sidebar.",
        "no_data": "No transactions yet. Import a bill export in the sidebar or load the demo persona.",
    },
    "zh": {
        "tagline": "在冲动和付款之间，留一个停顿。",
        "lang": "语言", "region": "数据区域", "region_help": "不同区域的数据分开存储（数据本地化）。",
        "demo": "加载演示用户（小梅）", "reset": "重置本区域", "clock": "演示时钟",
        "use_clock": "使用模拟时间（演示用）", "sources": "连接数据",
        "alipay": "支付宝账单（CSV）", "wechat": "微信支付账单（CSV 或 XLSX）", "unionpay": "银联对账单（模拟 JSON）",
        "plaid": "Plaid 沙箱数据（JSON）", "plaid_live": "从 Plaid 沙箱拉取（实时）", "agent": "助手",
        "today": "今天", "bills": "账单", "parking": "等待区与退货", "mirror": "消费复盘",
        "plan": "计划与安全", "txns": "交易明细",
        "safe": "今天可安心花费", "payday": "下次发薪", "breakdown": "计算方式",
        "pause": "停一下", "pause_help": "想买东西？先让我们一起想一想。",
        "what": "买什么？", "amount": "金额", "currency": "币种", "category": "类别",
        "live": "直播间", "flash": "限时秒杀", "inst": "分期",
        "check": "看一看", "score": "冲动指数", "hours": "小时的工作", "days": "天的今日预算",
        "park": "放进等待区 24 小时", "skip": "不买了", "buy": "还是要买", "why_buy": "原因（可选，只给你自己看）",
        "chat": "问问再想想", "chat_ph": "例如：要不要买 899 元的外套？",
        "confirm": "确认", "dismiss": "忽略", "waiting": "等待你确认",
        "subs": "订阅", "per_month": "每月", "fees": "过去 90 天的手续费", "adhd_tax": "可避免的额外花费，90 天",
        "draft_cancel": "生成取消草稿", "drafts": "草稿（不会自动发送）", "instalments": "未还完的分期",
        "returns": "可退货订单", "draft_return": "生成退货申请", "parked": "等待区",
        "review": "可以重新决定了", "bought": "我买了", "skipped": "不买了", "extend": "再等 24 小时",
        "mood": "心情记录", "mood_l": "心情（1 低落 - 5 很好）", "stress_l": "压力（1 平静 - 5 很大）", "note": "备注（可选）",
        "save": "保存", "rec": "本周建议",
        "calm_plan": "冷静计划", "calm_help": "你在冷静时定下的规则。更安全的修改立即生效；放松保护的修改要等 24 小时。",
        "apply": "保存修改", "queued": "冷静期中的修改（24 小时）", "cancel": "取消",
        "ally": "信任的人", "unsafe": "我感到不安全，立即移除", "tiers": "权限分级",
        "audit": "审计日志", "verify": "校验哈希链", "download": "下载审计日志",
        "sandbox_ops": "沙箱操作", "outbox": "提醒发件箱（沙箱，不会真的发送）",
        "onboard": "开始设置", "onboard_help": "选出像你的描述。我们从不询问诊断。",
        "consent_fin": "我同意「再想想」处理我导入的财务数据（单独同意，符合 PIPL / GDPR）。",
        "consent_llm": "允许把脱敏后的数据发送给大模型（可选；否则使用离线助手）。",
        "start": "开始", "or_demo": "也可以在侧边栏加载演示用户。",
        "no_data": "还没有交易。请在侧边栏导入账单，或加载演示用户。",
    },
}

PATTERNS = {
    "late_night_impulse": ("I buy on impulse late at night", "我常在深夜冲动消费"),
    "forgets_subscriptions": ("I forget subscriptions and due dates", "我常忘记订阅和还款日"),
    "livestream_shopping": ("Live streams and countdowns get me", "直播和倒计时很容易让我下单"),
    "mood_spending": ("I shop to feel better", "心情不好时我会买东西"),
    "spending_sprees": ("I sometimes have spending sprees I regret", "我有时会大手大脚，事后后悔"),
    "festival_splurges": ("Big sales festivals (Double 11, 618, Black Friday) blow my budget", "双十一、618、黑五这类购物节常让我超支"),
}
CATEGORIES = ["clothing", "beauty", "electronics", "household", "food", "entertainment", "gaming", "travel",
              "subscriptions", "groceries", "health", "transport", "other"]
BAND_COLOR = {"green": "#2e7d5b", "amber": "#b7791f", "red": "#c0392b"}
CHARTS = os.getenv("ST_NO_CHARTS") != "1"
TIME_SLOTS = [f"{h:02d}:{m:02d}" for h in range(24) for m in range(0, 60, 5)]
AVATARS = {"user": ":material/person:", "assistant": ":material/pause_circle:"}
LABELS_ZH = {"Automated reply": "自动回复", "AI-generated": "AI 生成", "Safety message": "安全提示",
             "Automated reply (offline fallback)": "自动回复（离线）"}
SUGGESTIONS = {
    "en": ["What's safe to spend today?", "Check my subscriptions and fees", "Can I still return something?", "How was my week?"],
    "zh": ["今天还能花多少？", "检查我的订阅和账单", "有什么还能退货吗？", "这周复盘一下"],
}  # the headless test harness cannot render Vega charts

st.markdown("""
<style>
.block-container {padding-top: 3.4rem;}
.st-big {font-size: 2.6rem; font-weight: 700; line-height: 1.1;}
.st-sub {color: #6b7280; font-size: 0.9rem;}
.chip {display:inline-block; padding:2px 10px; margin:2px 4px 2px 0; border-radius:12px; font-size:0.8rem;
       background: rgba(127,127,127,0.12);}
.riskbar {height:10px; border-radius:6px; background: rgba(127,127,127,0.15); overflow:hidden; margin:6px 0 10px;}
.riskbar > div {height:100%;}
.label {font-size:0.72rem; color:#6b7280; text-transform:uppercase; letter-spacing:0.04em;}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------- session + state
ss = st.session_state
ss.setdefault("lang", "en")
ss.setdefault("region", "CN")
ss.setdefault("chat", [])
ss.setdefault("pause_result", None)


def t(key: str) -> str:
    return T[ss.lang].get(key, T["en"].get(key, key))


def L(en: str, zh: str) -> str:
    return zh if ss.lang == "zh" else en


with st.sidebar:
    st.markdown("### :material/pause_circle: Second Thought · 再想想")
    st.caption(t("tagline"))
    ss.lang = "zh" if st.radio("Language / 语言", ["English", "中文"], horizontal=True, key="lang_choice") == "中文" else "en"
    ss.region = st.selectbox(t("region"), ["CN", "EU"], key="region_choice", help=t("region_help"))

state = AppState.for_region(ss.region, DEFAULT_ROOT)
tb = Toolbox(state)
svc = tb.svc
assistant = Assistant(tb, use_llm=bool(state.profile.get("consents", {}).get("llm_processing", False)))

# queued plan changes whose cooldown passed
if state.pending_changes:
    state.plan, applied = plan_rules.apply_due(state.plan, state.pending_changes, state.now())
    for change in applied:
        state.audit.append(actor="rules", tool="apply_queued_change", tier="T3 Act within pre-set limits", decision="executed",
                           args=change, scenario_time=state.now(), note="24-hour cooldown passed")
    if applied:
        state.save()

base = state.profile.get("base_currency", "CNY")

with st.sidebar:
    if st.button(t("demo"), width="stretch", type="primary"):
        load_demo(state)
        ss.chat, ss.pause_result = [], None
        st.rerun()
    if st.button(t("reset"), width="stretch"):
        state.reset()
        ss.chat, ss.pause_result = [], None
        st.rerun()

    st.markdown(f"**{t('clock')}**")
    use_clock = st.checkbox(t("use_clock"), value=state.clock is not None)
    if use_clock:
        cur = state.now()
        d = st.date_input("date", cur.date(), label_visibility="collapsed")
        cur_slot = f"{cur.hour:02d}:{cur.minute // 5 * 5:02d}"
        tm = st.selectbox("time", TIME_SLOTS, index=TIME_SLOTS.index(cur_slot), label_visibility="collapsed")
        new = datetime.combine(d, time.fromisoformat(tm))
        if state.clock != new.isoformat(timespec="minutes"):
            state.set_clock(new)
            state.save()
            st.rerun()
    elif state.clock is not None:
        state.set_clock(None)
        state.save()
        st.rerun()
    st.caption(f"{state.now():%Y-%m-%d %H:%M}")

    with st.expander(t("sources"), expanded=False):
        for key, label, types in (("alipay", t("alipay"), ["csv"]), ("wechat", t("wechat"), ["csv", "xlsx"]),
                                  ("unionpay", t("unionpay"), ["json"]), ("plaid", t("plaid"), ["json"])):
            up = st.file_uploader(label, type=types, key=f"up_{key}")
            if up is not None and st.button(L("Import", "导入") + f" · {key}", key=f"imp_{key}"):
                try:
                    n = state.import_file(key, up.getvalue(), up.name)
                    state.save()
                    state.audit.append(actor="user", tool=f"import_{key}", tier="T0 Observe", decision="executed",
                                       args={"file": up.name}, result={"new_transactions": n}, scenario_time=state.now())
                    st.success(L(f"{n} new transactions", f"新增 {n} 笔交易"))
                except Exception as exc:  # show parser problems to the user
                    st.error(str(exc))
        live_ok = bool(os.getenv("PLAID_CLIENT_ID") and os.getenv("PLAID_SECRET"))
        if st.button(t("plaid_live"), disabled=not live_ok, help=None if live_ok else "Set PLAID_CLIENT_ID / PLAID_SECRET"):
            try:
                n = state.import_plaid_live()
                state.save()
                st.success(L(f"{n} sandbox transactions", f"{n} 笔沙箱交易"))
            except Exception as exc:
                st.error(str(exc))
        st.dataframe(pd.DataFrame([{"source": k, **v} for k, v in REGISTRY.items()]), hide_index=True, width="stretch")

    st.markdown(f"**{t('agent')}**: `{assistant.mode}`")
    if state.profile:
        consents = state.profile.setdefault("consents", {})
        llm_ok = st.checkbox(t("consent_llm"), value=bool(consents.get("llm_processing")),
                             help=None if os.getenv("LLM_API_KEY") else "Set LLM_API_KEY / LLM_PROVIDER to use a model.")
        if llm_ok != bool(consents.get("llm_processing")):
            consents["llm_processing"] = llm_ok
            state.save()
            state.audit.append(actor="user", tool="consent_change", tier="T0 Observe", decision="executed",
                               args={"llm_processing": llm_ok}, scenario_time=state.now())
            st.rerun()
    if assistant.notice:
        st.caption(assistant.notice)
    st.caption(L("Not a medical service and not financial advice.", "不提供医疗服务，也不构成投资建议。"))


# ---------------------------------------------------------------- onboarding
if not state.profile:
    st.title(t("onboard"))
    st.write(t("onboard_help"))
    with st.form("onboarding"):
        c1, c2, c3 = st.columns(3)
        name = c1.text_input(L("First name (optional)", "名字（可选）"))
        currency = c2.selectbox(L("Base currency", "基础币种"), ["CNY", "EUR", "USD"], index=0 if ss.region == "CN" else 1)
        payday = c3.number_input(L("Payday (day of month)", "发薪日（每月几号）"), 1, 28, 10)
        c1, c2, c3 = st.columns(3)
        income = c1.number_input(L("Monthly income", "月收入"), 0.0, 1e7, 15000.0, step=500.0)
        balance = c2.number_input(L("Main account balance", "主账户余额"), 0.0, 1e8, 8000.0, step=100.0)
        goal = c3.text_input(L("Savings goal", "储蓄目标"), L("Trip", "旅行"))
        patterns = st.multiselect(L("What sounds like you?", "哪些描述像你？"), list(PATTERNS),
                                  format_func=lambda k: PATTERNS[k][1 if ss.lang == "zh" else 0])
        triggers = st.multiselect(L("Categories that get you", "容易冲动的类别"), CATEGORIES, ["clothing"])
        st.markdown(f"**{t('calm_plan')}**")
        c1, c2, c3 = st.columns(3)
        night = c1.toggle(L("Night hold 23:00-06:00", "夜间暂缓 23:00-06:00"), True)
        threshold = c2.number_input(L("Hold purchases over", "暂缓超过此金额的消费"), 0.0, 1e6, 300.0, step=50.0)
        hold = c3.number_input(L("Hold for (hours)", "暂缓时长（小时）"), 1, 72, 12)
        ally = st.text_input(L("Trusted ally (optional, name)", "信任的人（可选，名字）"))
        fin = st.checkbox(t("consent_fin"))
        llm = st.checkbox(t("consent_llm"))
        if st.form_submit_button(t("start"), type="primary"):
            if not fin:
                st.error(L("We need your consent to process financial data.", "需要你同意处理财务数据。"))
            else:
                state.profile = {
                    "name": name, "region": ss.region, "base_currency": currency, "language": ss.lang,
                    "patterns": patterns, "trigger_categories": triggers, "payday": int(payday),
                    "monthly_income": income, "work_hours_per_month": 174,
                    "accounts": [{"name": L("Main account", "主账户"), "currency": currency, "balance": balance}],
                    "fixed_bills": [], "credit_due": [], "savings_goal": {"name": goal, "target": 0, "monthly": 0},
                    "buffer_share": 0.10, "consents": {"financial_data": True, "llm_processing": llm, "ally_alerts": bool(ally)},
                }
                state.plan = CalmPlan(night_hold=night, night_hold_threshold=threshold, hold_hours=int(hold),
                                      ally={"name": ally, "channel": "SMS", "alerts": ["red_flag"]} if ally else None)
                state.save()
                state.audit.append(actor="user", tool="onboarding", tier="T0 Observe", decision="executed",
                                   args={"patterns": patterns, "consents": state.profile["consents"]}, scenario_time=state.now())
                st.rerun()
    st.info(t("or_demo"))
    st.stop()


# ---------------------------------------------------------------- helpers
REASONS = {
    "night_hold": ("held by your night rule", "夜间规则暂缓"),
    "category_cap": ("over your monthly cap", "超过每月上限"),
    "blocked_category": ("blocked category", "已屏蔽的类别"),
    "parked by you": ("parked by you", "你自己放进来的"),
}


def reason_text(code: str) -> str:
    parts = [REASONS.get(c, (c, c))[1 if ss.lang == "zh" else 0] for c in code.split("+")]
    return ", ".join(parts)


def describe(p: dict) -> str:
    """Plain-language description of a pending proposal."""
    a = p["args"]
    tool = p["tool"]
    if tool == "request_rule_change":
        setting, value = a.get("setting"), a.get("value")
        if setting == "night_hold" and value is False:
            return L("Turn off the night hold. Takes effect 24 hours after you confirm.", "关闭夜间暂缓。确认 24 小时后生效。")
        return L(f"Change rule {setting} to {value}.", f"把规则 {setting} 改为 {value}。")
    if tool == "draft_cancellation":
        return L(f"Draft a cancellation for {a.get('subscription_key')}.", f"为「{a.get('subscription_key')}」生成取消草稿。")
    if tool == "draft_return":
        txn = state.ledger.by_id(a.get("transaction_id", ""))
        item = (txn.description or txn.merchant) if txn else a.get("transaction_id")
        return L(f"Draft a return request for {item}.", f"为「{item}」生成退货申请。")
    if tool == "park_item":
        return L(f"Park {a.get('title')} for {a.get('hours', 24)} hours.", f"把「{a.get('title')}」放进等待区 {a.get('hours', 24)} 小时。")
    if tool == "save_to_pot":
        return L(f"Move {money(float(a.get('amount', 0)), base)} to your savings pot.", f"把 {money(float(a.get('amount', 0)), base)} 存进储蓄。")
    if tool == "set_category_cap":
        return L(f"Monthly cap of {money(float(a.get('monthly_cap', 0)), base)} for {a.get('category')}.",
                 f"为 {a.get('category')} 设置每月上限 {money(float(a.get('monthly_cap', 0)), base)}。")
    if tool == "notify_ally":
        return L("Send your trusted ally a short heads-up (no amounts).", "给信任的人发一条简短提醒（不含金额）。")
    return f"{tool} {a}"


def render_pending() -> None:
    if not state.pending_actions:
        return
    st.markdown(f"**{t('waiting')}**")
    for aid, p in list(state.pending_actions.items()):
        c1, c2, c3 = st.columns([5, 1.6, 1.6], vertical_alignment="center")
        c1.markdown(describe(p))
        if c2.button(t("confirm"), key=f"ok_{aid}", type="primary", width="stretch"):
            res = tb.confirm(aid)
            st.toast(L("Done", "已完成") if res.status == "ok" else res.message)
            if res.status == "ok" and res.result and res.result.get("status") == "queued":
                st.toast(L(f"Queued until {res.result['effective_at'].replace('T', ' ')}",
                           f"已排队，{res.result['effective_at'].replace('T', ' ')} 生效"))
            st.rerun()
        if c3.button(t("dismiss"), key=f"no_{aid}", width="stretch"):
            tb.gate.reject(aid)
            st.rerun()


def risk_card(r: dict) -> None:
    risk = r["risk"]
    color = BAND_COLOR[risk["band"]]
    st.markdown(f"<div class='label'>{t('score')}</div><div class='st-big' style='color:{color}'>{risk['score']}"
                f"<span class='st-sub'> / 100</span></div><div class='riskbar'><div style='width:{risk['score']}%;"
                f"background:{color}'></div></div>", unsafe_allow_html=True)
    chips = "".join(f"<span class='chip'>+{x['points']} {x['zh' if ss.lang == 'zh' else 'en']}</span>" for x in risk["reasons"])
    st.markdown(chips or f"<span class='chip'>{L('Nothing unusual', '没有异常')}</span>", unsafe_allow_html=True)
    bits = []
    if r.get("hours_of_work"):
        bits.append(f"**{r['hours_of_work']:g}** {t('hours')}")
    if r.get("days_of_budget"):
        bits.append(f"**{r['days_of_budget']:g}** {t('days')}")
    if bits:
        st.markdown(" · ".join(bits))
    for o in r.get("rules", []):
        if o.get("status") != "ok":
            continue
        if o.get("tool") == "auto_hold":
            st.warning(L(f"Your calm-state plan put this on hold until {o['result']['hold_until'].replace('T', ' ')}.",
                         f"你的冷静计划已把它暂缓到 {o['result']['hold_until'].replace('T', ' ')}。"))
        if o.get("tool") == "auto_save":
            st.success(L(f"{money(o['result']['amount'], base)} moved to {o['result']['to'][4:]} (sandbox).",
                         f"{money(o['result']['amount'], base)} 已转入「{o['result']['to'][4:]}」（沙箱）。"))
    if r["halt"]:
        st.caption(" · ".join(q["zh" if ss.lang == "zh" else "en"] for q in r["halt"]))


if not state.ledger.transactions:
    st.info(t("no_data"))

tabs = st.tabs([t("today"), t("bills"), t("parking"), t("mirror"), t("plan"), t("txns")])

# ---------------------------------------------------------------- Today
with tabs[0]:
    left, right = st.columns([1, 1.25], gap="large")
    with left:
        s = svc.get_safe_to_spend()
        st.markdown(f"<div class='label'>{t('safe')}</div><div class='st-big'>{money(s['safe_to_spend_today'], base)}</div>"
                    f"<div class='st-sub'>{t('payday')} {s['next_payday']} · {s['d_days_to_payday']} "
                    f"{L('days', '天')}</div>", unsafe_allow_html=True)
        with st.expander(t("breakdown")):
            st.latex(r"S = \frac{B + I - F - G - R}{d}")
            st.markdown(
                f"B {money(s['B_balances'], base)} · I {money(s['I_income_expected'], base)} · F {money(s['F_due_before_payday'], base)} · "
                f"G {money(s['G_savings_share'], base)} · R {money(s['R_buffer'], base)} · d {s['d_days_to_payday']}")
            if s["upcoming"]:
                st.dataframe(pd.DataFrame(s["upcoming"]), hide_index=True, width="stretch")
        st.divider()
        st.subheader(t("pause"))
        st.caption(t("pause_help"))
        with st.form("pause"):
            what = st.text_input(t("what"), placeholder=L("Cashmere jacket", "羊绒外套"))
            c1, c2, c3 = st.columns([1.2, 1, 1.3])
            amount = c1.number_input(t("amount"), 0.0, 1e7, 0.0, step=10.0)
            cur = c2.selectbox(t("currency"), [base] + [c for c in ("CNY", "EUR", "USD") if c != base])
            cat = c3.selectbox(t("category"), CATEGORIES)
            c1, c2, c3 = st.columns(3)
            live = c1.checkbox(t("live"))
            flash = c2.checkbox(t("flash"))
            inst = c3.checkbox(t("inst"))
            if st.form_submit_button(t("check"), type="primary") and amount > 0:
                res = tb.call("pause_check", {"amount": amount, "title": what, "category": cat, "currency": cur,
                                              "livestream": live, "flash_sale": flash, "instalment": inst}, actor="user")
                ss.pause_result = res.result if res.status == "ok" else None
                if res.status != "ok":
                    st.error(res.message)
        r = ss.pause_result
        if r:
            risk_card(r)
            held = any(o.get("tool") == "auto_hold" and o.get("status") == "ok" for o in r.get("rules", []))
            intent = r["intent"]
            if not held:
                c1, c2, c3 = st.columns(3)
                if c1.button(t("park"), type="primary", width="stretch"):
                    res = tb.call("park_item", {"title": intent["title"] or intent["category"], "amount": intent["amount"],
                                                "currency": intent["currency"], "category": intent["category"],
                                                "risk_score": r["risk"]["score"], "hours": 24}, actor="user", confirmed=True)
                    ss.pause_result = None
                    st.toast(L("Parked for 24 hours", "已放进等待区 24 小时"))
                    st.rerun()
                if c2.button(t("skip"), width="stretch"):
                    tb.call("record_decision", {"title": intent["title"] or intent["category"], "amount": intent["amount"],
                                                "currency": intent["currency"], "category": intent["category"],
                                                "risk_score": r["risk"]["score"], "decision": "skipped"}, actor="user", confirmed=True)
                    ss.pause_result = None
                    st.toast(L("Skipped. Nice one.", "不买了，做得好。"))
                    st.rerun()
                with c3.popover(t("buy"), width="stretch"):
                    note = st.text_input(t("why_buy"), key="buy_note")
                    if st.button(t("confirm"), key="buy_ok"):
                        tb.call("record_decision", {"title": intent["title"] or intent["category"], "amount": intent["amount"],
                                                    "currency": intent["currency"], "category": intent["category"],
                                                    "risk_score": r["risk"]["score"], "decision": "bought", "note": note},
                                actor="user", confirmed=True)
                        ss.pause_result = None
                        st.rerun()
    with right:
        st.subheader(t("chat"))
        box = st.container(height=520)
        suggestion = None
        with box:
            if not ss.chat:
                st.caption(L("Try one of these, or type your own question below.", "试试下面这些，或者在下方输入你的问题。"))
                for i, q in enumerate(SUGGESTIONS[ss.lang]):
                    if st.button(q, key=f"sugg_{i}"):
                        suggestion = q
            for m in ss.chat:
                with st.chat_message(m["role"], avatar=AVATARS[m["role"]]):
                    st.markdown(m["content"])
                    if m.get("label"):
                        st.caption(LABELS_ZH.get(m["label"], m["label"]) if ss.lang == "zh" else m["label"])
        render_pending()
        prompt = st.chat_input(t("chat_ph")) or suggestion
        if prompt:
            history = [{"role": m["role"], "content": m["content"]} for m in ss.chat]
            out = assistant.respond(prompt, history, ss.lang)
            ss.chat.append({"role": "user", "content": prompt})
            ss.chat.append({"role": "assistant", "content": out["text"], "label": out.get("label")})
            st.rerun()

# ---------------------------------------------------------------- Bills
with tabs[1]:
    b = svc.get_bill_check()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(t("subs"), f"{money(b['subscriptions_monthly_total'], base)}", help=f"{len(b['subscriptions'])}")
    c1.caption(L(f"{len(b['subscriptions'])} subscriptions, per month", f"{len(b['subscriptions'])} 个订阅，每月"))
    c2.metric(t("fees"), money(b["fees_total"], base))
    c3.metric(t("adhd_tax"), money(b["avoidable_estimate_90d"], base))
    c4.metric(L("Bought with BNPL, 90 days", "90 天内先买后付"), money(b["bnpl_spend"], base))
    flag_names = {"price_increase": L("price went up", "涨价了"), "trial_converted": L("free trial turned paid", "试用转付费"),
                  "foreign_account": L("old foreign account", "旧的海外账户"), "duplicate_service": L("overlaps", "功能重复"),
                  "cancel_candidate": L("cancel candidate", "建议取消")}
    st.markdown(f"#### {t('subs')}")
    for sub in b["subscriptions"]:
        c1, c2, c3, c4 = st.columns([2.2, 1.2, 3.4, 1.4])
        c1.markdown(f"**{sub['merchant']}**  \n<span class='st-sub'>{sub['source']} · {sub['cadence']} · "
                    f"{L('next', '下次')} {sub['next_expected']}</span>", unsafe_allow_html=True)
        c2.markdown(f"{money(sub['monthly_cost_base'], base)}  \n<span class='st-sub'>{t('per_month')}</span>", unsafe_allow_html=True)
        c3.markdown("".join(f"<span class='chip'>{flag_names.get(f, f)}</span>" for f in sub["flags"]) or "&nbsp;",
                    unsafe_allow_html=True)
        if c4.button(t("draft_cancel"), key=f"dc_{sub['key']}", width="stretch"):
            tb.call("draft_cancellation", {"subscription_key": sub["key"]}, actor="user", confirmed=True)
            st.rerun()
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"#### {L('Fees', '手续费')}")
        if b["fees"]:
            st.dataframe(pd.DataFrame(b["fees"])[["timestamp", "source", "merchant", "description", "amount", "currency"]],
                         hide_index=True, width="stretch")
    with c2:
        st.markdown(f"#### {t('instalments')}")
        if b["open_instalments"]:
            st.dataframe(pd.DataFrame(b["open_instalments"])[["date", "description", "total", "count", "monthly", "remaining"]],
                         hide_index=True, width="stretch")
    drafts = [d for d in state.drafts if d["type"] == "cancellation"]
    if drafts:
        st.markdown(f"#### {t('drafts')}")
        for d in reversed(drafts):
            with st.expander(f"{d['target']} · {L('saves', '每月省')} {money(d['monthly_saving'], base)}"):
                st.code(d["zh" if ss.lang == "zh" else "en"], language=None)
                st.caption(d["where_zh" if ss.lang == "zh" else "where_en"])

# ---------------------------------------------------------------- Parking & returns
with tabs[2]:
    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown(f"#### {t('parked')}")
        items = svc.get_parking_lot()
        open_items = [i for i in items if i["status"] == "parked"]
        if not open_items:
            st.caption(L("Nothing parked.", "等待区是空的。"))
        for i in open_items:
            with st.container(border=True):
                ready = i.get("ready_to_review")
                st.markdown(f"**{i['title']}** · {money(i['amount_base'], base)}  \n<span class='st-sub'>"
                            f"{L('until', '等到')} {i['hold_until'].replace('T', ' ')} · {reason_text(i['reason'])}"
                            + (f" · {L('saved', '已存')} {money(i['auto_saved'], base)}" if i.get("auto_saved") else "")
                            + "</span>", unsafe_allow_html=True)
                if ready:
                    st.success(t("review"))
                b1, b2, b3 = st.columns(3)
                if b1.button(t("bought"), key=f"pb_{i['id']}", width="stretch"):
                    tb.call("resolve_parked", {"item_id": i["id"], "decision": "bought"}, actor="user", confirmed=True)
                    st.rerun()
                if b2.button(t("skipped"), key=f"ps_{i['id']}", width="stretch"):
                    tb.call("resolve_parked", {"item_id": i["id"], "decision": "skipped"}, actor="user", confirmed=True)
                    st.rerun()
                if b3.button(t("extend"), key=f"pe_{i['id']}", width="stretch"):
                    tb.call("resolve_parked", {"item_id": i["id"], "decision": "extend"}, actor="user", confirmed=True)
                    st.rerun()
        done = [i for i in items if i["status"] != "parked"]
        if done:
            st.caption(L(f"Decided: {sum(1 for i in done if i['status'] == 'skipped')} skipped, "
                         f"{sum(1 for i in done if i['status'] == 'bought')} bought.",
                         f"已决定：不买 {sum(1 for i in done if i['status'] == 'skipped')} 件，买了 {sum(1 for i in done if i['status'] == 'bought')} 件。"))
        if state.pots:
            st.markdown(f"#### {L('Savings pots', '储蓄')}")
            for name, value in state.pots.items():
                st.metric(name, money(value, base))
    with c2:
        st.markdown(f"#### {t('returns')}")
        rets = svc.get_return_windows()
        if not rets:
            st.caption(L("No open return windows.", "目前没有可退货的订单。"))
        for rt in rets:
            with st.container(border=True):
                st.markdown(f"**{rt['description'] or rt['merchant']}** · {money(rt['amount_base'], base)}  \n"
                            f"<span class='st-sub'>{rt['purchased'].replace('T', ' ')} · {rt['days_left']} "
                            f"{L('days left', '天后截止')} ({rt['window_days']}-{L('day window', '天退货期')})"
                            f" · {L('impulse score', '冲动指数')} {rt.get('risk_score', 0)}</span>", unsafe_allow_html=True)
                if st.button(t("draft_return"), key=f"dr_{rt['id']}"):
                    tb.call("draft_return", {"transaction_id": rt["id"]}, actor="user", confirmed=True)
                    st.rerun()
        rdrafts = [d for d in state.drafts if d["type"] == "return"]
        for d in reversed(rdrafts):
            with st.expander(f"{d['target']} · {L('deadline', '截止')} {d['deadline']}"):
                st.code(d["zh" if ss.lang == "zh" else "en"], language=None)

# ---------------------------------------------------------------- Money mirror
with tabs[3]:
    window = st.radio(L("Window", "时间范围"), [L("7 days", "7 天"), L("30 days", "30 天")], horizontal=True)
    days = 30 if window.startswith("30") else 7
    m = svc.get_money_mirror(days)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(L("Non-essential spending", "非必需消费"), money(m["discretionary_total"], base))
    c2.metric(L("Impulse-flagged", "冲动消费占比"), f"{m['impulse_share']:.0%}")
    c3.metric(L("After 23:00", "23 点后"), f"{m['night_share']:.0%}")
    c4.metric(L("From live streams", "来自直播"), f"{m['livestream_share']:.0%}")
    st.info(f"**{t('rec')}**  \n{m['recommendation']['zh' if ss.lang == 'zh' else 'en']}")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"**{L('Spending by hour', '按小时的消费')}**")
        if CHARTS:
            st.bar_chart(pd.DataFrame({base: m["by_hour"]}, index=[f"{h:02d}" for h in range(24)]), height=260)
    with c2:
        st.markdown(f"**{L('By category', '按类别')}**")
        if m["by_category"] and CHARTS:
            st.bar_chart(pd.Series(m["by_category"], name=base), height=260, horizontal=True)
    if m["rough_day_avg"] is not None and m["calm_day_avg"] is not None:
        st.markdown(L(f"On days you logged stress you spent **{money(m['rough_day_avg'], base)}** on average, versus "
                      f"**{money(m['calm_day_avg'], base)}** on other days.",
                      f"记录压力的日子平均花 **{money(m['rough_day_avg'], base)}**，其他日子平均 **{money(m['calm_day_avg'], base)}**。"))
    with st.form("mood"):
        st.markdown(f"**{t('mood')}**")
        c1, c2 = st.columns(2)
        mood = c1.slider(t("mood_l"), 1, 5, 3)
        stress = c2.slider(t("stress_l"), 1, 5, 2)
        note = st.text_input(t("note"))
        if st.form_submit_button(t("save")):
            tb.call("log_mood", {"mood": mood, "stress": stress, "note": note}, actor="user", confirmed=True)
            st.toast(L("Saved", "已保存"))

# ---------------------------------------------------------------- Plan & safety
with tabs[4]:
    p = state.plan
    c1, c2 = st.columns([1.1, 1], gap="large")
    with c1:
        st.markdown(f"#### {t('calm_plan')}")
        st.caption(t("calm_help"))
        with st.form("plan"):
            night = st.toggle(L("Night hold", "夜间暂缓"), p.night_hold)
            a, b2 = st.columns(2)
            start = time.fromisoformat(a.selectbox(L("From", "从"), TIME_SLOTS, index=TIME_SLOTS.index(p.night_start)))
            end = time.fromisoformat(b2.selectbox(L("Until", "到"), TIME_SLOTS, index=TIME_SLOTS.index(p.night_end)))
            a, b2 = st.columns(2)
            threshold = a.number_input(L("Hold purchases over", "暂缓超过此金额"), 0.0, 1e6, float(p.night_hold_threshold), step=50.0)
            hours = b2.number_input(L("Hold for (hours)", "暂缓（小时）"), 1, 72, int(p.hold_hours))
            a, b2 = st.columns(2)
            share = a.slider(L("Auto-save share of resisted buys", "忍住时自动存入比例"), 0.0, 0.5, float(p.auto_save_share), 0.05)
            cap = b2.number_input(L("Daily auto-save cap", "每日自动存入上限"), 0.0, 1e5, float(p.daily_sweep_cap), step=10.0)
            blocked_gambling = st.checkbox(L("Block gambling merchants", "屏蔽博彩类商户"), "gambling" in p.blocked_categories)
            if st.form_submit_button(t("apply"), type="primary"):
                changes = []
                if night != p.night_hold:
                    changes.append(("night_hold", night))
                if (start.strftime("%H:%M"), end.strftime("%H:%M")) != (p.night_start, p.night_end):
                    changes.append(("night_window", [start.strftime("%H:%M"), end.strftime("%H:%M")]))
                if threshold != p.night_hold_threshold:
                    changes.append(("night_hold_threshold", threshold))
                if hours != p.hold_hours:
                    changes.append(("hold_hours", int(hours)))
                if abs(share - p.auto_save_share) > 1e-9:
                    changes.append(("auto_save_share", share))
                if cap != p.daily_sweep_cap:
                    changes.append(("daily_sweep_cap", cap))
                if blocked_gambling != ("gambling" in p.blocked_categories):
                    changes.append(("blocked_categories.gambling", blocked_gambling))
                for setting, value in changes:
                    res = tb.call("request_rule_change", {"setting": setting, "value": value}, actor="user", confirmed=True)
                    if res.status == "ok":
                        outcome = res.result
                        if outcome["status"] == "applied":
                            st.success(L(f"{setting}: applied now (safer).", f"{setting}：已立即生效（更安全）。"))
                        else:
                            st.warning(L(f"{setting}: queued until {outcome['effective_at'].replace('T', ' ')} (removes protection).",
                                         f"{setting}：将于 {outcome['effective_at'].replace('T', ' ')} 生效（放松保护）。"))
        if state.pending_changes:
            st.markdown(f"**{t('queued')}**")
            for ch in state.pending_changes:
                a, b2 = st.columns([4, 1])
                a.markdown(f"`{ch['path']}` → `{ch['value']}` · {L('from', '生效于')} {ch['effective_at'].replace('T', ' ')}")
                if b2.button(t("cancel"), key=f"cx_{ch['id']}"):
                    tb.call("cancel_pending_change", {"change_id": ch["id"]}, actor="user", confirmed=True)
                    st.rerun()
        st.markdown(f"#### {t('ally')}")
        if p.ally:
            st.markdown(f"**{p.ally['name']}** · {p.ally.get('channel', 'SMS')} · "
                        f"{L('only gets a heads-up, never balances or transactions', '只会收到提醒，看不到余额和交易')}")
            if st.button(t("unsafe")):
                tb.call("remove_ally_now", {}, actor="user", confirmed=True)
                st.rerun()
        else:
            st.caption(L("No trusted ally set.", "未设置信任的人。"))
    with c2:
        st.markdown(f"#### {t('tiers')}")
        rows = [{"tool": spec.name, "tier": TIER_LABELS[spec.tier],
                 "agent": "propose" if spec.tier.value == 2 and spec.agent_visible else ("yes" if spec.agent_visible else "no")}
                for spec in tb.gate.tools.values()]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", height=300)
        st.caption(L("Never: pay third parties, borrow, trade, change credentials. These tools do not exist.",
                     "永远不会：向第三方付款、借贷、交易、修改密码。这些工具根本不存在。"))
        st.markdown(f"#### {t('audit')}")
        entries = state.audit.entries()
        if st.button(t("verify")):
            ok, bad = state.audit.verify()
            (st.success if ok else st.error)(L(f"Chain intact, {len(entries)} entries." if ok else f"Broken at entry {bad}.",
                                               f"哈希链完整，共 {len(entries)} 条。" if ok else f"第 {bad} 条被篡改。"))
        if entries:
            df = pd.DataFrame(entries[-60:][::-1])[["seq", "scenario_time", "actor", "tool", "tier", "decision", "note", "hash"]]
            df["hash"] = df["hash"].str[:12]
            st.dataframe(df, hide_index=True, width="stretch", height=280)
            st.download_button(t("download"), state.audit.path.read_bytes(), "audit_log.jsonl", "application/json")
        if state.sandbox_ops:
            st.markdown(f"**{t('sandbox_ops')}**")
            st.dataframe(pd.DataFrame(state.sandbox_ops[::-1]), hide_index=True, width="stretch")
        if state.outbox:
            st.markdown(f"**{t('outbox')}**")
            st.dataframe(pd.DataFrame(state.outbox[::-1])[["ts", "to", "channel", "reason_code", "status"]],
                         hide_index=True, width="stretch")

# ---------------------------------------------------------------- Transactions
with tabs[5]:
    if state.ledger.transactions:
        rows = svc.get_recent_transactions(limit=len(state.ledger.transactions))
        df = pd.DataFrame(rows)
        sources = st.multiselect(L("Sources", "来源"), sorted(df["source"].unique()), sorted(df["source"].unique()))
        df = df[df["source"].isin(sources)]
        df["essential"] = df["category"].isin(ESSENTIAL_CATEGORIES)
        st.dataframe(df[["when", "source", "merchant", "description", "amount", "currency", "amount_base", "direction",
                         "category", "tags", "risk"]], hide_index=True, width="stretch", height=560)
