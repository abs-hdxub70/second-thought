"""Deterministic rules engine: the only caller allowed to run T3 actions.

It never interprets free text. It reacts to a scored purchase intent or to the user's own decision
(park / skip) and applies only the rules from the calm-state plan.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..engine.categories import ESSENTIAL_CATEGORIES

if TYPE_CHECKING:  # pragma: no cover
    from ..agent.tools import Toolbox


def _month_to_date(toolbox: "Toolbox", category: str) -> float:
    now = toolbox.state.now()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return sum(t.amount_base for t in toolbox.state.ledger.expenses(start, now) if t.category == category)


def evaluate_intent(toolbox: "Toolbox", check: dict) -> list[dict]:
    """Run after The Pause scored a purchase. Returns the rule outcomes."""
    plan = toolbox.state.plan
    intent, risk = check["intent"], check["risk"]
    outcomes: list[dict] = []
    category = intent["category"]
    if category in ESSENTIAL_CATEGORIES:
        return [{"rule": "essentials", "status": "skipped", "message": "Essentials are never held."}]

    why = []
    if category in plan.blocked_categories:
        why.append("blocked_category")
    when = toolbox.state.now()
    if plan.night_hold and plan.in_night_window(when) and intent["amount_base"] >= plan.night_hold_threshold:
        why.append("night_hold")
    cap = plan.category_caps.get(category)
    if cap is not None and _month_to_date(toolbox, category) + intent["amount_base"] > cap:
        why.append("category_cap")

    if why:
        hours = 72 if "blocked_category" in why else plan.hold_hours
        res = toolbox.gate.call("auto_hold", {
            "title": intent["title"], "amount": intent["amount"], "currency": intent["currency"],
            "merchant": intent["merchant"], "category": category, "hours": hours,
            "risk_score": risk["score"], "reason": "+".join(why),
        }, actor="rules")
        outcomes.append({"rule": "+".join(why), **res.to_dict()})
        if res.status == "ok":
            saved = on_urge_resisted(toolbox, intent["amount_base"], "auto: held by calm-state plan")
            outcomes.extend(saved)
            mark_saved(toolbox, res.result["id"], saved)

    if risk["band"] == "red" and plan.ally and plan.ally_auto_alert:
        res = toolbox.gate.call("auto_ally_alert", {"reason": "red_flag"}, actor="rules")
        outcomes.append({"rule": "ally_auto_alert", **res.to_dict()})
    return outcomes


def mark_saved(toolbox: "Toolbox", item_id: str, saved: list[dict]) -> None:
    if saved and saved[0].get("status") == "ok":
        for item in toolbox.state.parking:
            if item["id"] == item_id:
                item["auto_saved"] = saved[0]["result"]["amount"]
        toolbox.state.save()


def on_urge_resisted(toolbox: "Toolbox", amount_base: float, reason: str) -> list[dict]:
    """User parked or skipped a purchase: move the agreed share to savings, within the daily cap."""
    share = toolbox.state.plan.auto_save_share
    if share <= 0:
        return []
    amount = float(round(amount_base * share))
    if amount <= 0:
        return []
    res = toolbox.gate.call("auto_save", {"amount": amount, "reason": reason}, actor="rules")
    return [{"rule": "auto_save", **res.to_dict()}]
