"""Business actions. Plain functions over AppState; the gate decides who may call which."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from .engine import insights, returns, safe_to_spend, subscriptions
from .engine.categories import ESSENTIAL_CATEGORIES
from .engine.ledger import convert
from .engine.risk_score import PurchaseIntent, score, score_transaction
from .models import RiskResult, Transaction
from .policy import plan as plan_rules
from .state import AppState

HALT_QUESTIONS = [
    {"en": "Are you hungry?", "zh": "你饿了吗？"},
    {"en": "Are you angry or frustrated?", "zh": "你在生气或烦躁吗？"},
    {"en": "Are you lonely?", "zh": "你感到孤单吗？"},
    {"en": "Are you tired?", "zh": "你累了吗？"},
]


class Services:
    def __init__(self, state: AppState):
        self.state = state

    # ---- context ----------------------------------------------------------------
    @property
    def profile(self) -> dict:
        return self.state.profile

    @property
    def base(self) -> str:
        return self.profile.get("base_currency", "CNY")

    def now(self) -> datetime:
        return self.state.now()

    def risk_kwargs(self) -> dict:
        return {
            "trigger_categories": self.profile.get("trigger_categories", []),
            "payday": int(self.profile.get("payday", 0)),
            "mood_log": self.state.mood_log,
        }

    def risk_for(self, t: Transaction) -> RiskResult:
        return score_transaction(t, self.state.ledger, **self.risk_kwargs())

    def subs(self) -> list[subscriptions.Subscription]:
        return subscriptions.detect(self.state.ledger, self.now())

    def main_account(self) -> dict:
        accounts = self.profile.get("accounts", [])
        if not accounts:
            raise ValueError("No account set up.")
        return accounts[0]

    # ---- T0 observe --------------------------------------------------------------
    def get_safe_to_spend(self) -> dict:
        return safe_to_spend.compute(self.profile, self.state.ledger, self.now(), self.subs())

    def get_bill_check(self) -> dict:
        return subscriptions.bill_check(self.state.ledger, self.now())

    def get_return_windows(self) -> list[dict]:
        return returns.candidates(self.state.ledger, self.now(), self.profile.get("region", "CN"), self.risk_for)

    def get_money_mirror(self, days: int = 7) -> dict:
        bills = self.get_bill_check()
        plan = self.state.plan
        return insights.money_mirror(self.state.ledger, self.now(), self.risk_for, self.state.mood_log, int(days),
                                     bills["duplicates_avoidable_monthly"], plan.night_hold, plan.night_hold_threshold,
                                     {"CNY": "¥", "EUR": "€", "USD": "$", "GBP": "£"}.get(self.base, ""))

    def get_recent_transactions(self, limit: int = 15) -> list[dict]:
        out = []
        for t in reversed(self.state.ledger.transactions[-limit:]):
            r = self.risk_for(t) if t.is_expense else None
            out.append({
                "id": t.id, "when": t.timestamp.isoformat(timespec="minutes"), "source": t.source,
                "merchant": t.merchant, "description": t.description, "amount": t.amount,
                "currency": t.currency, "amount_base": t.amount_base, "direction": t.direction,
                "category": t.category, "tags": t.tags, "risk": r.score if r else None,
            })
        return out

    def get_plan(self) -> dict:
        return {"plan": self.state.plan.to_dict(), "pending_changes": self.state.pending_changes,
                "now_in_night_window": self.state.plan.in_night_window(self.now())}

    def get_parking_lot(self) -> list[dict]:
        now = self.now()
        out = []
        for item in self.state.parking:
            if item["status"] == "parked" and datetime.fromisoformat(item["hold_until"]) <= now:
                item = {**item, "ready_to_review": True}
            out.append(item)
        return out

    def is_hot(self) -> bool:
        now = self.now()
        recent_red = self.state.last_red and now - datetime.fromisoformat(self.state.last_red) <= timedelta(hours=2)
        return bool(recent_red) or self.state.plan.in_night_window(now)

    # ---- T1 advise ---------------------------------------------------------------
    def pause_check(self, amount: float, title: str = "", merchant: str = "", category: str = "other",
                    currency: str | None = None, livestream: bool = False, flash_sale: bool = False,
                    instalment: bool = False) -> dict:
        amount = float(amount)
        if amount <= 0:
            raise ValueError("Amount must be positive.")
        cur = currency or self.base
        amount_base = convert(amount, cur, self.base)
        tags = (["livestream", "online"] if livestream else []) + (["flash_sale"] if flash_sale else [])
        intent = PurchaseIntent(amount_base, self.now(), category, merchant, title, tags, instalment)
        risk = score(intent, self.state.ledger, **self.risk_kwargs())
        if risk.band == "red":
            self.state.last_red = self.now().isoformat(timespec="minutes")
        sts = self.get_safe_to_spend()
        daily = sts["safe_to_spend_today"]
        return {
            "intent": {"title": title, "merchant": merchant, "amount": amount, "currency": cur,
                       "amount_base": amount_base, "category": category, "tags": tags,
                       "instalment": instalment, "when": intent.when.isoformat(timespec="minutes")},
            "risk": risk.to_dict(),
            "hours_of_work": safe_to_spend.hours_of_work(amount_base, self.profile),
            "safe_to_spend_today": daily,
            "days_of_budget": round(amount_base / daily, 1) if daily > 0 else None,
            "essential": category in ESSENTIAL_CATEGORIES,
            "halt": HALT_QUESTIONS if risk.band != "green" else [],
            "goal": (self.profile.get("savings_goal") or {}).get("name"),
            "options": ["buy", "park_24h", "skip_and_save"] if risk.band != "green" else ["buy"],
        }

    # ---- T2 actions ----------------------------------------------------------------
    def park_item(self, title: str, amount: float, currency: str | None = None, merchant: str = "",
                  hours: int = 24, risk_score: int = 0, category: str = "other", reason: str = "parked by you") -> dict:
        now = self.now()
        cur = currency or self.base
        item = {
            "id": uuid.uuid4().hex[:8], "title": title or merchant or "Purchase", "merchant": merchant,
            "amount": float(amount), "currency": cur, "amount_base": convert(float(amount), cur, self.base),
            "category": category, "risk_score": int(risk_score), "created_at": now.isoformat(timespec="minutes"),
            "hold_until": (now + timedelta(hours=int(hours))).isoformat(timespec="minutes"),
            "status": "parked", "reason": reason,
        }
        self.state.parking.append(item)
        return item

    def resolve_parked(self, item_id: str, decision: str, note: str = "") -> dict:
        item = next((i for i in self.state.parking if i["id"] == item_id), None)
        if item is None:
            raise ValueError("Parked item not found.")
        if decision not in ("bought", "skipped", "extend"):
            raise ValueError("Decision must be bought, skipped or extend.")
        if decision == "extend":
            item["hold_until"] = (self.now() + timedelta(hours=24)).isoformat(timespec="minutes")
        else:
            item["status"] = decision
            item["resolved_at"] = self.now().isoformat(timespec="minutes")
            if note:
                item["note"] = note
        return item

    def record_decision(self, title: str, amount: float, decision: str, currency: str | None = None,
                        category: str = "other", risk_score: int = 0, note: str = "") -> dict:
        """The person decided right away after The Pause: bought (an override, no judgement) or skipped."""
        if decision not in ("bought", "skipped"):
            raise ValueError("Decision must be bought or skipped.")
        item = self.park_item(title, amount, currency, hours=0, risk_score=risk_score, category=category,
                              reason="decided right away")
        item["status"] = decision
        item["resolved_at"] = item["created_at"]
        if note:
            item["note"] = note[:200]
        return item

    def cancel_pending_change(self, change_id: str) -> dict:
        """Cancelling a queued (riskier) change is always safe, so it applies immediately."""
        change = next((c for c in self.state.pending_changes if c["id"] == change_id), None)
        if change is None:
            raise ValueError("No queued change with that id.")
        self.state.pending_changes.remove(change)
        return {"cancelled": change_id, "path": change["path"]}

    def save_to_pot(self, amount: float, pot: str | None = None, reason: str = "") -> dict:
        amount = round(float(amount), 2)
        acct = self.main_account()
        pot_name = pot or (self.profile.get("savings_goal") or {}).get("name") or "Savings"
        balance_base = convert(float(acct["balance"]), acct.get("currency", self.base), self.base)
        if amount <= 0 or amount > balance_base:
            raise ValueError("Amount must be positive and not more than the main balance.")
        acct["balance"] = round(float(acct["balance"]) - convert(amount, self.base, acct.get("currency", self.base)), 2)
        self.state.pots[pot_name] = round(self.state.pots.get(pot_name, 0.0) + amount, 2)
        op = {
            "op_id": "sbx-" + uuid.uuid4().hex[:10], "ts": self.now().isoformat(timespec="minutes"),
            "type": "internal_transfer", "from": acct["name"], "to": f"pot:{pot_name}",
            "amount": amount, "currency": self.base, "reason": reason, "status": "settled (sandbox)",
        }
        self.state.sandbox_ops.append(op)
        return op

    def draft_cancellation(self, subscription_key: str) -> dict:
        sub = next((s for s in self.subs() if s.key == subscription_key or s.merchant == subscription_key), None)
        if sub is None:
            raise ValueError("Subscription not found.")
        where = {
            "alipay": ("In Alipay this is usually under 我的 > 设置 > 支付设置 > 免密支付/自动扣款.",
                       "支付宝通常在：我的 > 设置 > 支付设置 > 免密支付/自动扣款。"),
            "wechat": ("In WeChat this is usually under 我 > 服务 > 钱包 > 支付设置 > 自动续费.",
                       "微信通常在：我 > 服务 > 钱包 > 支付设置 > 自动续费。"),
        }.get(sub.source, ("Usually under Account > Subscription or Manage plan on the provider's website.",
                           "通常在服务商网站的 账户 > 订阅/管理套餐 中。"))
        draft = {
            "id": uuid.uuid4().hex[:8], "type": "cancellation", "target": sub.merchant,
            "created_at": self.now().isoformat(timespec="minutes"),
            "en": (f"Hello,\n\nPlease cancel my {sub.merchant} subscription and turn off automatic renewal "
                   f"from today. Please confirm by email that no further charges will be made.\n\nThank you."),
            "zh": f"您好：\n\n请取消我的「{sub.merchant}」会员并关闭自动续费，从今天起不再扣款，并请回复确认。\n\n谢谢！",
            "where_en": where[0], "where_zh": where[1],
            "monthly_saving": sub.monthly_cost_base, "status": "drafted (not sent)",
        }
        self.state.drafts.append(draft)
        return draft

    def draft_return(self, transaction_id: str) -> dict:
        cand = next((c for c in self.get_return_windows() if c["id"] == transaction_id), None)
        if cand is None:
            raise ValueError("No open return window for that purchase.")
        text = returns.draft_return_request(cand, self.profile.get("region", "CN"))
        draft = {"id": uuid.uuid4().hex[:8], "type": "return", "target": cand["description"] or cand["merchant"],
                 "created_at": self.now().isoformat(timespec="minutes"), "deadline": cand["deadline"],
                 "days_left": cand["days_left"], "refund": cand["amount_base"], "status": "drafted (not sent)",
                 **text}
        self.state.drafts.append(draft)
        return draft

    def request_rule_change(self, setting: str, value: Any, safety_exit: bool = False) -> dict:
        new_plan, outcome = plan_rules.request_change(self.state.plan, self.state.pending_changes, setting, value,
                                                      self.now(), safety_exit=safety_exit)
        self.state.plan = new_plan
        outcome["hot_state"] = self.is_hot()
        return outcome

    def set_category_cap(self, category: str, monthly_cap: float) -> dict:
        return self.request_rule_change(f"category_caps.{category}", float(monthly_cap))

    def notify_ally(self, reason: str) -> dict:
        ally = self.state.plan.ally
        if not ally:
            raise ValueError("No trusted ally set up.")
        msg = {
            "id": uuid.uuid4().hex[:8], "to": ally["name"], "channel": ally.get("channel", "SMS"),
            "ts": self.now().isoformat(timespec="minutes"),
            "text_en": f"Hi {ally['name']}, a quick heads-up from Second Thought: {self.profile.get('name', 'your friend')} "
                       f"asked us to let you know when spending gets intense. Maybe check in? No details are shared.",
            "text_zh": f"{ally['name']}你好，这是「再想想」的提醒：{self.profile.get('name', '你的朋友')} 请我们在消费比较冲动时告诉你。"
                       f"方便的话问候一下？我们不会分享任何具体信息。",
            "reason_code": reason, "status": "queued (sandbox, not sent)",
        }
        self.state.outbox.append(msg)
        return msg

    def log_mood(self, mood: int, stress: int, note: str = "") -> dict:
        entry = {"ts": self.now().isoformat(timespec="minutes"), "mood": int(mood), "stress": int(stress)}
        if note:
            entry["note"] = note[:200]
        self.state.mood_log.append(entry)
        return entry

    def auto_save_today(self) -> float:
        today = self.now().date().isoformat()
        return round(sum(op["amount"] for op in self.state.sandbox_ops
                         if op["ts"].startswith(today) and op.get("reason", "").startswith("auto")), 2)
