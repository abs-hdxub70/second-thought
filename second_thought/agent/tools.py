"""Toolbox: registers every action on the gate with its tier, schema and safety check."""

from __future__ import annotations

from typing import Any

from ..engine.categories import ESSENTIAL_CATEGORIES
from ..policy import plan as plan_rules
from ..policy import rules_engine
from ..policy.gate import Gate, GateResult, Tier, ToolSpec
from ..services import Services
from ..state import AppState

CATEGORY_ENUM = ["food", "groceries", "household", "clothing", "beauty", "electronics", "transport",
                 "utilities", "housing", "entertainment", "education", "health", "travel", "services",
                 "sports", "gaming", "subscriptions", "gambling", "other"]


def _obj(props: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": props, "required": required or []}


class Toolbox:
    def __init__(self, state: AppState):
        self.state = state
        self.svc = Services(state)
        self.gate = Gate(state)
        self._register()

    # ---- checks ---------------------------------------------------------------
    def _positive_amount(self, args: dict) -> str | None:
        try:
            return None if float(args.get("amount", 0)) > 0 else "Amount must be positive."
        except (TypeError, ValueError):
            return "Amount must be a number."

    def _check_hold(self, args: dict) -> str | None:
        if args.get("category") in ESSENTIAL_CATEGORIES:
            return "Essentials are never held."
        if not args.get("reason"):
            return "A hold needs a rule from the calm-state plan."
        return self._positive_amount(args)

    def _check_auto_save(self, args: dict) -> str | None:
        bad = self._positive_amount(args)
        if bad:
            return bad
        cap = self.state.plan.daily_sweep_cap
        if self.svc.auto_save_today() + float(args["amount"]) > cap:
            return f"Daily auto-save cap of {cap:.0f} reached."
        return None

    def _check_ally(self, args: dict) -> str | None:
        return None if self.state.plan.ally else "No trusted ally set up."

    def _check_auto_ally(self, args: dict) -> str | None:
        if not self.state.plan.ally or not self.state.plan.ally_auto_alert:
            return "Automatic ally alerts are not switched on in the calm-state plan."
        return None

    def _check_rule_change(self, args: dict) -> str | None:
        try:
            plan_rules.classify(self.state.plan, args.get("setting", ""), args.get("value"))
        except (ValueError, TypeError, KeyError) as exc:
            return f"Invalid setting: {exc}"
        return None

    # ---- registration ---------------------------------------------------------
    def _register(self) -> None:
        s, g = self.svc, self.gate
        reg = g.register
        # T0 observe
        reg(ToolSpec("get_safe_to_spend", Tier.T0, s.get_safe_to_spend,
                     "How much the user can safely spend today, with the breakdown (balances, bills due before payday, savings share, buffer)."))
        reg(ToolSpec("get_bill_check", Tier.T0, s.get_bill_check,
                     "Bill analysis: subscriptions, duplicate services, converted free trials, price rises, late fees, open instalments ('ADHD tax' report)."))
        reg(ToolSpec("get_return_windows", Tier.T0, s.get_return_windows,
                     "Online purchases that can still be returned, with days left (7 days in China, 14 in the EU)."))
        reg(ToolSpec("get_money_mirror", Tier.T0, s.get_money_mirror,
                     "Weekly spending insights: impulse share, night share, live-stream share, mood link, one suggestion.",
                     _obj({"days": {"type": "integer", "minimum": 1, "maximum": 90}})))
        reg(ToolSpec("get_recent_transactions", Tier.T0, s.get_recent_transactions,
                     "Most recent transactions across all connected sources with their impulse risk score.",
                     _obj({"limit": {"type": "integer", "minimum": 1, "maximum": 50}})))
        reg(ToolSpec("get_plan", Tier.T0, s.get_plan,
                     "The user's calm-state plan (rules set while calm) and queued changes."))
        reg(ToolSpec("get_parking_lot", Tier.T0, s.get_parking_lot,
                     "Parked purchases and when each can be reviewed."))
        # T1 advise
        reg(ToolSpec("pause_check", Tier.T1, s.pause_check,
                     "The Pause: score a purchase the user is considering. Returns risk score with reasons, cost in hours of work, share of today's safe-to-spend, and options. Calm-state rules may apply automatically.",
                     _obj({
                         "amount": {"type": "number"},
                         "title": {"type": "string"},
                         "merchant": {"type": "string"},
                         "category": {"type": "string", "enum": CATEGORY_ENUM},
                         "currency": {"type": "string"},
                         "livestream": {"type": "boolean"},
                         "flash_sale": {"type": "boolean"},
                         "instalment": {"type": "boolean"},
                     }, ["amount"]), check=self._positive_amount))
        # T2 propose -> person confirms
        reg(ToolSpec("park_item", Tier.T2, s.park_item,
                     "Propose parking a purchase in the parking lot for a number of hours (default 24).",
                     _obj({"title": {"type": "string"}, "amount": {"type": "number"}, "currency": {"type": "string"},
                           "merchant": {"type": "string"}, "hours": {"type": "integer", "minimum": 1, "maximum": 168},
                           "risk_score": {"type": "integer"}, "category": {"type": "string", "enum": CATEGORY_ENUM}},
                          ["title", "amount"]), check=self._positive_amount))
        reg(ToolSpec("save_to_pot", Tier.T2, s.save_to_pot,
                     "Propose moving money from the main account to the user's own savings pot (sandbox).",
                     _obj({"amount": {"type": "number"}, "pot": {"type": "string"}, "reason": {"type": "string"}},
                          ["amount"]), check=self._positive_amount))
        reg(ToolSpec("draft_cancellation", Tier.T2, s.draft_cancellation,
                     "Propose drafting a cancellation message for a subscription (never sent automatically).",
                     _obj({"subscription_key": {"type": "string", "description": "subscription key or merchant name from get_bill_check"}},
                          ["subscription_key"])))
        reg(ToolSpec("draft_return", Tier.T2, s.draft_return,
                     "Propose drafting a return request for a purchase with an open return window.",
                     _obj({"transaction_id": {"type": "string"}}, ["transaction_id"])))
        reg(ToolSpec("set_category_cap", Tier.T2, s.set_category_cap,
                     "Propose a monthly spending cap for a category (a new or lower cap applies immediately).",
                     _obj({"category": {"type": "string", "enum": CATEGORY_ENUM}, "monthly_cap": {"type": "number"}},
                          ["category", "monthly_cap"])))
        reg(ToolSpec("request_rule_change", Tier.T2, s.request_rule_change,
                     "Propose changing a calm-state rule. Safer changes apply now; riskier ones (e.g. turning off the night hold) wait 24 hours. Settings: night_hold (bool), night_window ([start,end]), night_hold_threshold, hold_hours, category_caps.<cat>, blocked_categories.<cat> (bool), auto_save_share, daily_sweep_cap, ally_auto_alert.",
                     _obj({"setting": {"type": "string"}, "value": {}}, ["setting", "value"]),
                     check=self._check_rule_change))
        reg(ToolSpec("notify_ally", Tier.T2, s.notify_ally,
                     "Propose sending the trusted ally a short heads-up (no amounts or details).",
                     _obj({"reason": {"type": "string"}}, ["reason"]), check=self._check_ally))
        # UI-only actions (the person's own clicks)
        reg(ToolSpec("resolve_parked", Tier.T2, s.resolve_parked, "Buy, skip or extend a parked item.",
                     _obj({"item_id": {"type": "string"}, "decision": {"type": "string"}, "note": {"type": "string"}}),
                     agent_visible=False))
        reg(ToolSpec("log_mood", Tier.T2, s.log_mood, "Self-reported mood check-in.",
                     _obj({"mood": {"type": "integer"}, "stress": {"type": "integer"}, "note": {"type": "string"}}),
                     agent_visible=False))
        reg(ToolSpec("record_decision", Tier.T2, s.record_decision, "Record buying or skipping right after The Pause.",
                     agent_visible=False, check=self._positive_amount))
        reg(ToolSpec("cancel_pending_change", Tier.T2, s.cancel_pending_change, "Cancel a queued rule change.",
                     agent_visible=False))
        reg(ToolSpec("remove_ally_now", Tier.T2,
                     lambda: s.request_rule_change("ally", None, safety_exit=True),
                     "'I feel unsafe' exit: remove the trusted ally immediately.", agent_visible=False))
        # T3 rules engine only
        reg(ToolSpec("auto_hold", Tier.T3, s.park_item, "Hold a purchase under a calm-state rule.",
                     check=self._check_hold, agent_visible=False))
        reg(ToolSpec("auto_save", Tier.T3, s.save_to_pot, "Move the agreed share of a resisted purchase to savings.",
                     check=self._check_auto_save, agent_visible=False))
        reg(ToolSpec("auto_ally_alert", Tier.T3, s.notify_ally, "Heads-up to the ally under a calm-state rule.",
                     check=self._check_auto_ally, agent_visible=False))

    # ---- entry point used by UI, agent and scripts --------------------------------
    def call(self, name: str, args: dict | None = None, actor: str = "agent", confirmed: bool = False,
             via: str = "") -> GateResult:
        res = self.gate.call(name, args or {}, actor=actor, confirmed=confirmed, via=via)
        return self._after(name, res)

    def confirm(self, action_id: str) -> GateResult:
        pending = self.state.pending_actions.get(action_id)
        res = self.gate.confirm(action_id)
        return self._after(pending["tool"] if pending else "", res)

    def _after(self, name: str, res: GateResult) -> GateResult:
        """Hooks that run after an action succeeded: calm-state rules and save-the-urge."""
        if res.status != "ok":
            return res
        if name == "pause_check":
            res.result["rules"] = rules_engine.evaluate_intent(self, res.result)
        elif name == "park_item":
            saved = rules_engine.on_urge_resisted(self, res.result["amount_base"], "auto: you parked it")
            rules_engine.mark_saved(self, res.result["id"], saved)
            res.result["rules"] = saved
        elif name in ("resolve_parked", "record_decision") and res.result.get("status") == "skipped" \
                and not res.result.get("auto_saved"):
            saved = rules_engine.on_urge_resisted(self, res.result["amount_base"], "auto: you skipped it")
            rules_engine.mark_saved(self, res.result["id"], saved)
            res.result["rules"] = saved
        return res

    def openai_tools(self) -> list[dict]:
        return [{"type": "function", "function": {"name": t.name, "description": f"[{t.tier.name}] {t.description}",
                                                  "parameters": t.params}}
                for t in self.gate.agent_tools()]
