"""Safe to spend today.

S = (B + I - F - G - R) / d
  B  current balances (all accounts, base currency)
  I  other income expected before next payday
  F  fixed bills, credit/BNPL repayments and subscriptions due before next payday
  G  savings-goal share for the period (monthly contribution * d / 30)
  R  buffer (default 10% of monthly fixed costs)
  d  days until next payday (min 1)
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from .ledger import convert
from .subscriptions import Subscription, detect
from .ledger import Ledger


def next_payday(today: date, payday: int) -> date:
    if today.day < payday:
        return today.replace(day=payday)
    month = today.month % 12 + 1
    year = today.year + (1 if today.month == 12 else 0)
    return date(year, month, min(payday, 28))


def _due_in_window(due_day: int, start: date, end: date) -> date | None:
    """Next occurrence of a day-of-month in [start, end)."""
    d = start
    while d < end:
        if d.day == due_day:
            return d
        d += timedelta(days=1)
    return None


def compute(profile: dict, ledger: Ledger, now: datetime, subscriptions: list[Subscription] | None = None) -> dict:
    base = profile.get("base_currency", "CNY")
    today = now.date()
    payday = next_payday(today, int(profile.get("payday", 1)))
    d = max(1, (payday - today).days)

    balances = [
        {"name": a["name"], "amount": convert(float(a["balance"]), a.get("currency", base), base)}
        for a in profile.get("accounts", [])
    ]
    B = round(sum(b["amount"] for b in balances), 2)
    I = round(sum(convert(float(x["amount"]), x.get("currency", base), base)
                  for x in profile.get("other_income", [])
                  if _due_in_window(int(x["day"]), today, payday)), 2)

    upcoming = []
    for bill in profile.get("fixed_bills", []):
        due = _due_in_window(int(bill["due_day"]), today, payday)
        if due:
            upcoming.append({"name": bill["name"], "due": due.isoformat(), "kind": "bill",
                             "amount": convert(float(bill["amount"]), bill.get("currency", base), base)})
    for credit in profile.get("credit_due", []):
        due = _due_in_window(int(credit["due_day"]), today, payday)
        if due:
            upcoming.append({"name": credit["name"], "due": due.isoformat(), "kind": "credit",
                             "amount": convert(float(credit["amount"]), credit.get("currency", base), base)})
    subs = subscriptions if subscriptions is not None else detect(ledger, now)
    for s in subs:
        nxt = date.fromisoformat(s.next_expected)
        if today <= nxt < payday:
            upcoming.append({"name": s.merchant, "due": nxt.isoformat(), "kind": "subscription",
                             "amount": convert(s.amount, s.currency, base)})
    F = round(sum(u["amount"] for u in upcoming), 2)

    goal = profile.get("savings_goal") or {}
    G = round(float(goal.get("monthly", 0)) * d / 30, 2)

    monthly_fixed = sum(convert(float(b["amount"]), b.get("currency", base), base) for b in profile.get("fixed_bills", []))
    monthly_fixed += sum(s.monthly_cost_base for s in subs)
    R = round(float(profile.get("buffer_share", 0.10)) * monthly_fixed, 2)

    S = round((B + I - F - G - R) / d, 2)
    upcoming.sort(key=lambda u: u["due"])
    return {
        "safe_to_spend_today": S,
        "currency": base,
        "B_balances": B,
        "I_income_expected": I,
        "F_due_before_payday": F,
        "G_savings_share": G,
        "R_buffer": R,
        "d_days_to_payday": d,
        "next_payday": payday.isoformat(),
        "balances": balances,
        "upcoming": upcoming,
        "status": "ok" if S > 0 else "negative",
    }


def hours_of_work(amount_base: float, profile: dict) -> float | None:
    income = float(profile.get("monthly_income", 0))
    hours = float(profile.get("work_hours_per_month", 174))
    if income <= 0 or hours <= 0:
        return None
    return round(amount_base / (income / hours), 1)
