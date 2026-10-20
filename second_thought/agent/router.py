"""Offline agent: keyword intents (English and Chinese) mapped to the same gated tools.

It runs without any API key, so the demo always works, and it never reads instructions from data:
it only looks at what the user typed.
"""

from __future__ import annotations

import re
from typing import Any

from ..engine.categories import categorize
from ..models import Transaction
from .tools import Toolbox

SYMBOL = {"CNY": "¥", "EUR": "€", "USD": "$", "GBP": "£"}


def money(amount: float, currency: str = "CNY") -> str:
    return f"{SYMBOL.get(currency, currency + ' ')}{amount:,.0f}"


INTENTS: list[tuple[str, tuple[str, ...]]] = [
    ("transfer_out", ("transfer", "send money", "wire ", "pay someone", "转账", "转给", "汇款", "打钱", "überweis")),
    ("loosen", ("remove my", "turn off", "switch off", "disable", "remove the limit", "raise my limit", "no limit",
                "取消夜间", "关闭夜间", "取消限制", "关掉", "提高限额", "解除")),
    ("pause", ("should i buy", "can i buy", "want to buy", "thinking of buying", "worth it", "buy this", "buy a",
               "想买", "要不要买", "买不买", "能买吗", "该不该买", "下单")),
    ("bills", ("subscription", "subscriptions", "bill", "fees", "late fee", "adhd tax", "订阅", "会员", "账单", "滞纳金", "扣费")),
    ("returns", ("return", "refund", "regret", "退货", "退款", "后悔")),
    ("safe", ("safe to spend", "how much can i spend", "budget", "left to spend", "还能花", "今天能花", "预算", "还剩多少")),
    ("mirror", ("week", "insight", "mirror", "pattern", "how am i doing", "周报", "复盘", "这周", "规律")),
    ("plan", ("my plan", "rules", "limits", "calm", "计划", "规则", "限制")),
    ("parking", ("parked", "parking", "wishlist", "等待区", "心愿单")),
    ("mood", ("stressed", "sad", "anxious", "lonely", "bored", "upset", "压力", "难过", "焦虑", "孤单", "无聊", "心情不好")),
]

AMOUNT = re.compile(r"(¥|￥|€|\$|rmb|cny|eur|usd)?\s*(\d+(?:[.,]\d{1,2})?)\s*(元|块|rmb|yuan|cny|€|eur|euros?|usd|dollars?)?", re.I)


def detect_intent(text: str) -> str:
    t = text.lower()
    for name, words in INTENTS:
        if any(w in t for w in words):
            return name
    return "help"


def parse_amount(text: str, base: str) -> tuple[float | None, str]:
    best: tuple[float, str] | None = None
    fallback: list[float] = []
    for m in AMOUNT.finditer(text):
        pre, num, post = m.group(1), m.group(2), m.group(3)
        value = float(num.replace(",", "."))
        marker = (pre or post or "").lower()
        if marker:
            cur = "EUR" if marker in ("€", "eur", "euro", "euros") else "USD" if marker in ("$", "usd", "dollar", "dollars") else "CNY"
            if best is None:
                best = (value, cur)
        else:
            fallback.append(value)
    if best:
        return best
    if fallback:
        return max(fallback), base
    return None, base


def guess_title(text: str) -> str:
    t = re.sub(AMOUNT, " ", text)
    t = re.sub(r"(?i)should i buy|can i buy|i want to buy|want to buy|thinking of buying|worth it|buy this|"
               r"我想买|我要买|想买|要不要买|买不买|能买吗|该不该买|一个|一件|一款|这个|[?？!！。,，]", " ", t)
    t = re.sub(r"(?i)^\s*(this|a|an|the)\s+", " ", t)
    t = re.sub(r"\s+", " ", t).strip(" -:的")
    return t[:60] or "this"


class OfflineAgent:
    def __init__(self, toolbox: Toolbox):
        self.tb = toolbox

    def _t(self, lang: str, en: str, zh: str) -> str:
        return zh if lang == "zh" else en

    def respond(self, text: str, lang: str = "en") -> dict[str, Any]:
        intent = detect_intent(text)
        handler = getattr(self, f"_{intent}")
        return handler(text, lang)

    # ---- intents --------------------------------------------------------------
    def _pause(self, text: str, lang: str) -> dict:
        base = self.tb.svc.base
        amount, cur = parse_amount(text, base)
        if not amount:
            return {"text": self._t(lang, "Happy to pause on it with you. How much is it, and what is it?",
                                    "好，我们一起想一想。多少钱？买的是什么？"), "events": []}
        low = text.lower()
        probe = Transaction(id="probe", source="chat", timestamp=self.tb.state.now(), amount=amount, currency=cur,
                            direction="expense", merchant="", description=text)
        args = {"amount": amount, "currency": cur, "title": guess_title(text), "category": categorize(probe),
                "livestream": any(w in low for w in ("live", "stream", "直播", "主播")),
                "flash_sale": any(w in low for w in ("flash", "countdown", "秒杀", "限时", "倒计时")),
                "instalment": any(w in low for w in ("instal", "bnpl", "klarna", "花呗", "分期", "白条"))}
        res = self.tb.call("pause_check", args, actor="agent")
        events = [res.to_dict()]
        if res.status != "ok":
            return {"text": res.message, "events": events}
        r = res.result
        risk = r["risk"]
        sep = "；" if lang == "zh" else "; "
        reasons = sep.join(x["zh" if lang == "zh" else "en"] for x in risk["reasons"]) or self._t(lang, "nothing unusual", "没有异常")
        hours = r["hours_of_work"]
        held = next((o for o in r.get("rules", []) if o.get("tool") == "auto_hold" and o["status"] == "ok"), None)
        saved = next((o for o in r.get("rules", []) if o.get("tool") == "auto_save" and o["status"] == "ok"), None)
        lines = [self._t(lang, f"Impulse score {risk['score']}/100 ({risk['band']}). Why: {reasons}.",
                         f"冲动指数 {risk['score']}/100（{ {'green': '绿', 'amber': '黄', 'red': '红'}[risk['band']] }）。原因：{reasons}。")]
        if hours:
            lines.append(self._t(lang, f"{money(r['intent']['amount_base'], base)} is about {hours:g} hours of your work"
                                 + (f", or {r['days_of_budget']:g} days of today's safe-to-spend." if r["days_of_budget"] else "."),
                                 f"{money(r['intent']['amount_base'], base)} 大约是你 {hours:g} 小时的工作"
                                 + (f"，相当于 {r['days_of_budget']:g} 天的可安心花费。" if r["days_of_budget"] else "。")))
        if held:
            until = held["result"]["hold_until"].replace("T", " ")
            lines.append(self._t(lang, f"Your calm-state plan put this on hold until {until}. It's waiting in your parking lot.",
                                 f"你的冷静计划已把它暂缓到 {until}，已放进等待区。"))
            if saved:
                lines.append(self._t(lang, f"As agreed, {money(saved['result']['amount'], base)} moved to your {saved['result']['to'][4:]} pot.",
                                     f"按你的约定，{money(saved['result']['amount'], base)} 已转入「{saved['result']['to'][4:]}」储蓄。"))
        elif risk["band"] != "green":
            prop = self.tb.call("park_item", {"title": r["intent"]["title"], "amount": amount, "currency": cur,
                                              "category": r["intent"]["category"], "risk_score": risk["score"],
                                              "hours": 24}, actor="agent")
            events.append(prop.to_dict())
            if r["halt"]:
                lines.append(self._t(lang, "Quick check: hungry, angry, lonely or tired right now?", "先问一句：现在饿吗？生气吗？孤单吗？累吗？"))
            lines.append(self._t(lang, "I've prepared parking it for 24 hours, tap confirm if you want that.",
                                 "我已准备好把它放进等待区 24 小时，确认即可。"))
        else:
            lines.append(self._t(lang, "Looks fine to me. Enjoy it.", "看起来没问题，安心买吧。"))
        return {"text": " ".join(lines), "events": events, "data": {"pause": r}}

    def _transfer_out(self, text: str, lang: str) -> dict:
        self.tb.state.audit.append(actor="agent", tool="transfer_request", tier="Never", decision="denied",
                                   args={}, scenario_time=self.tb.state.now(), note="no tool can pay third parties")
        return {"text": self._t(lang, "I can't send money to anyone. That ability doesn't exist in Second Thought, on purpose. "
                                      "I can move money into your own savings pot, or help you pause on a purchase.",
                                "我不能把钱转给任何人，「再想想」故意没有这个功能。我可以帮你把钱存进自己的储蓄，或者陪你想想要不要买。"),
                "events": []}

    def _loosen(self, text: str, lang: str) -> dict:
        low = text.lower()
        m = re.search(r"(\d+)", text)
        if m and any(w in low for w in ("threshold", "limit to", "raise", "限额", "提高")):
            setting, value = "night_hold_threshold", float(m.group(1))
        else:
            setting, value = "night_hold", False
        res = self.tb.call("request_rule_change", {"setting": setting, "value": value}, actor="agent")
        hot = self.tb.svc.is_hot()
        text_en = ("I hear you. I've prepared that change for you to confirm. Because it removes a protection, it only "
                   "takes effect 24 hours after you confirm. That's the deal you made with yourself while calm.")
        text_zh = "明白。我已准备好这项修改，等你确认。因为它会取消一项保护，确认后要等 24 小时才生效。这是你冷静时和自己的约定。"
        if hot:
            text_en += " It's late, so tomorrow-you gets the final say."
            text_zh += " 现在已经很晚了，就让明天的你来做最终决定吧。"
        return {"text": self._t(lang, text_en, text_zh), "events": [res.to_dict()]}

    def _bills(self, text: str, lang: str) -> dict:
        res = self.tb.call("get_bill_check", actor="agent")
        b = res.result
        base = self.tb.svc.base
        events = [res.to_dict()]
        lines = [self._t(lang,
                         f"You have {len(b['subscriptions'])} subscriptions costing {money(b['subscriptions_monthly_total'], base)} a month. "
                         f"In the last {b['window_days']} days fees cost you {money(b['fees_total'], base)}.",
                         f"你有 {len(b['subscriptions'])} 个订阅，每月 {money(b['subscriptions_monthly_total'], base)}。"
                         f"过去 {b['window_days']} 天的滞纳金和手续费共 {money(b['fees_total'], base)}。")]
        groups: dict[str, list[str]] = {}
        for s in b["duplicate_services"]:
            groups.setdefault(s["group"], []).append(s["merchant"])
        if groups:
            overlap = "; ".join(f"{g} ({', '.join(m)})" for g, m in groups.items())
            lines.append(self._t(lang, f"Overlapping services: {overlap}.", f"功能重复的会员：{overlap}。"))
        # propose drafts: forgotten ones first (converted trials, old foreign account), then overlapping services
        targets: list[str] = []
        forgotten = b["trial_conversions"] + b["foreign_account_subscriptions"]
        for s in forgotten + [s for s in b["duplicate_services"] if "cancel_candidate" in s["flags"]]:
            if s["key"] not in targets:
                targets.append(s["key"])
        targets = targets[:5]
        for key in targets:
            events.append(self.tb.call("draft_cancellation", {"subscription_key": key}, actor="agent").to_dict())
        if forgotten:
            names = ", ".join(dict.fromkeys(s["merchant"] for s in forgotten))
            lines.append(self._t(lang, f"Probably forgotten: {names}.", f"可能已经忘了的：{names}。"))
        if targets:
            lines.append(self._t(lang, f"I've prepared {len(targets)} cancellation drafts. Confirm the ones you want.",
                                 f"我准备了 {len(targets)} 份取消草稿，确认你想要的即可。"))
        if b["avoidable_estimate_90d"]:
            lines.append(self._t(lang, f"Avoidable costs so far (the 'ADHD tax'): about {money(b['avoidable_estimate_90d'], base)} in {b['window_days']} days.",
                                 f"可避免的额外花费：{b['window_days']} 天约 {money(b['avoidable_estimate_90d'], base)}。"))
        return {"text": " ".join(lines), "events": events, "data": {"bills": b}}

    def _returns(self, text: str, lang: str) -> dict:
        res = self.tb.call("get_return_windows", actor="agent")
        items = res.result
        events = [res.to_dict()]
        if not items:
            return {"text": self._t(lang, "No open return windows right now.", "目前没有可退货的订单。"), "events": events}
        top = items[0]
        base = self.tb.svc.base
        events.append(self.tb.call("draft_return", {"transaction_id": top["id"]}, actor="agent").to_dict())
        lines = [self._t(lang, f"{len(items)} purchase(s) can still go back. Most urgent: {top['description'] or top['merchant']} "
                               f"({money(top['amount_base'], base)}), {top['days_left']} days left on the {top['window_days']}-day window.",
                         f"有 {len(items)} 笔订单还能退。最紧急：{top['description'] or top['merchant']}（{money(top['amount_base'], base)}），"
                         f"{top['window_days']} 天退货期还剩 {top['days_left']} 天。"),
                 self._t(lang, "I've prepared the return request, confirm to see the draft.", "退货申请已准备好，确认后查看草稿。")]
        return {"text": " ".join(lines), "events": events, "data": {"returns": items}}

    def _safe(self, text: str, lang: str) -> dict:
        res = self.tb.call("get_safe_to_spend", actor="agent")
        s = res.result
        base = s["currency"]
        due = money(s["F_due_before_payday"], base)
        text_en = (f"Safe to spend today: {money(s['safe_to_spend_today'], base)}. That keeps {due} for bills and repayments "
                   f"before payday ({s['next_payday']}, {s['d_days_to_payday']} days), {money(s['G_savings_share'], base)} for your goal "
                   f"and a {money(s['R_buffer'], base)} buffer.")
        text_zh = (f"今天可安心花费：{money(s['safe_to_spend_today'], base)}。已为发薪日（{s['next_payday']}，还有 {s['d_days_to_payday']} 天）前的"
                   f"账单和还款留出 {due}，为目标存 {money(s['G_savings_share'], base)}，并留 {money(s['R_buffer'], base)} 缓冲。")
        return {"text": self._t(lang, text_en, text_zh), "events": [res.to_dict()], "data": {"safe": s}}

    def _mirror(self, text: str, lang: str) -> dict:
        res = self.tb.call("get_money_mirror", {"days": 7}, actor="agent")
        m = res.result
        base = self.tb.svc.base
        lines = [self._t(lang, f"This week: {money(m['discretionary_total'], base)} on non-essentials, {m['impulse_share']:.0%} of it impulse-flagged.",
                         f"本周非必需消费 {money(m['discretionary_total'], base)}，其中 {m['impulse_share']:.0%} 被标记为冲动消费。")]
        if m["rough_day_avg"] is not None and m["calm_day_avg"] is not None:
            lines.append(self._t(lang, f"On days you logged stress you spent {money(m['rough_day_avg'], base)} on average, versus {money(m['calm_day_avg'], base)} on other days.",
                                 f"记录压力的日子平均花 {money(m['rough_day_avg'], base)}，其他日子平均 {money(m['calm_day_avg'], base)}。"))
        lines.append(m["recommendation"]["zh" if lang == "zh" else "en"])
        return {"text": " ".join(lines), "events": [res.to_dict()], "data": {"mirror": m}}

    def _plan(self, text: str, lang: str) -> dict:
        res = self.tb.call("get_plan", actor="agent")
        p = res.result["plan"]
        base = self.tb.svc.base
        caps = ", ".join(f"{k} {money(v, base)}" for k, v in p["category_caps"].items()) or self._t(lang, "none", "无")
        text_en = (f"Your calm-state plan: night hold {'on' if p['night_hold'] else 'off'} ({p['night_start']}-{p['night_end']}, over "
                   f"{money(p['night_hold_threshold'], base)}, {p['hold_hours']}h). Monthly caps: {caps}. Blocked: {', '.join(p['blocked_categories']) or 'none'}. "
                   f"Auto-save {p['auto_save_share']:.0%} of resisted buys, up to {money(p['daily_sweep_cap'], base)} a day.")
        text_zh = (f"你的冷静计划：夜间暂缓{'开启' if p['night_hold'] else '关闭'}（{p['night_start']}-{p['night_end']}，超过 "
                   f"{money(p['night_hold_threshold'], base)}，暂缓 {p['hold_hours']} 小时）。每月上限：{caps}。屏蔽：{', '.join(p['blocked_categories']) or '无'}。"
                   f"忍住的消费自动存 {p['auto_save_share']:.0%}，每天最多 {money(p['daily_sweep_cap'], base)}。")
        if res.result["pending_changes"]:
            text_en += f" {len(res.result['pending_changes'])} change(s) waiting out the 24-hour cooldown."
            text_zh += f" 有 {len(res.result['pending_changes'])} 项修改正在 24 小时冷静期中。"
        return {"text": self._t(lang, text_en, text_zh), "events": [res.to_dict()]}

    def _parking(self, text: str, lang: str) -> dict:
        res = self.tb.call("get_parking_lot", actor="agent")
        items = [i for i in res.result if i["status"] == "parked"]
        if not items:
            return {"text": self._t(lang, "Your parking lot is empty.", "等待区是空的。"), "events": [res.to_dict()]}
        base = self.tb.svc.base
        names = "; ".join(f"{i['title']} ({money(i['amount_base'], base)}, until {i['hold_until'].replace('T', ' ')})" for i in items)
        return {"text": self._t(lang, f"Parked: {names}.", f"等待区：{names}。"), "events": [res.to_dict()]}

    def _mood(self, text: str, lang: str) -> dict:
        return {"text": self._t(lang, "That sounds like a lot. Want to log it in the mood check-in? It helps the weekly mirror, "
                                      "and if you feel like buying something right now, run it past me first.",
                                "听起来不容易。要不要在心情记录里记一下？这会让每周复盘更准确。如果现在想买点什么，先跟我说一声。"),
                "events": []}

    def _help(self, text: str, lang: str) -> dict:
        return {"text": self._t(lang, "I can check what's safe to spend today, pause on a purchase with you ('should I buy a ¥899 jacket?'), "
                                      "go through your subscriptions and fees, find open return windows, or show your weekly money mirror.",
                                "我可以帮你看看今天能安心花多少、一起想想要不要买（“要不要买 899 元的外套？”）、检查订阅和手续费、"
                                "找到还能退的订单，或者看看本周消费复盘。"),
                "events": []}
