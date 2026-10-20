"""Subscription detection and the bill check ("ADHD tax" report).

A subscription = 2+ charges from the same merchant with gaps of 6-8, 28-32 or 360-370 days and
amounts within 10% of each other (one price step is allowed and flagged as a price rise).
"""

from __future__ import annotations

import re
import statistics
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta

from ..models import EXPENSE, Transaction
from .categories import ESSENTIAL_CATEGORIES, SERVICE_GROUPS, service_group
from .ledger import Ledger

CADENCES = {"weekly": (6, 8, 7), "monthly": (28, 32, 30), "yearly": (360, 370, 365)}
EXCLUDED = ESSENTIAL_CATEGORIES | {"transfer", "investment", "refund", "income"}


@dataclass
class Subscription:
    key: str
    merchant: str
    cadence: str
    amount: float  # last charge, original currency
    currency: str
    monthly_cost_base: float
    charges: int
    first_charge: str
    last_charge: str
    next_expected: str
    source: str
    group: str | None = None
    flags: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def merchant_key(merchant: str, description: str = "") -> str:
    text = f"{merchant} {description}".lower()
    for names in SERVICE_GROUPS.values():
        for n in names:
            if n.lower() in text:
                return n.lower()
    return re.sub(r"[\s\W_]+", "", merchant.lower()) or "unknown"


def _consistent(amounts: list[float]) -> tuple[bool, bool]:
    """Return (consistent, price_increase). Allows exactly one upward price step."""
    if max(amounts) <= min(amounts) * 1.10:
        return True, False
    for i in range(1, len(amounts)):
        before, after = amounts[:i], amounts[i:]
        if max(before) <= min(before) * 1.10 and max(after) <= min(after) * 1.10 and min(after) > max(before):
            return True, after[-1] > before[0] * 1.05
    return False, False


def _cadence(gaps: list[int]) -> str | None:
    for name, (lo, hi, _) in CADENCES.items():
        if all(lo <= g <= hi for g in gaps):
            return name
    return None


def _next_expected(last: datetime, cadence: str) -> datetime:
    if cadence == "monthly":
        month = last.month % 12 + 1
        year = last.year + (1 if last.month == 12 else 0)
        day = min(last.day, 28)
        return last.replace(year=year, month=month, day=day)
    return last + timedelta(days=CADENCES[cadence][2])


def detect(ledger: Ledger, today: datetime) -> list[Subscription]:
    paid: dict[str, list[Transaction]] = defaultdict(list)
    zero: dict[str, list[Transaction]] = defaultdict(list)
    for t in ledger.transactions:
        if t.category in EXCLUDED:
            continue
        key = merchant_key(t.merchant, t.description)
        if t.amount == 0:
            zero[key].append(t)
        elif t.direction == EXPENSE:
            paid[key].append(t)

    subs: list[Subscription] = []
    for key, txns in paid.items():
        if len(txns) < 2:
            continue
        txns.sort(key=lambda t: t.timestamp)
        gaps = [(b.timestamp.date() - a.timestamp.date()).days for a, b in zip(txns, txns[1:])]
        cadence = _cadence(gaps)
        if not cadence:
            continue
        ok, price_up = _consistent([t.amount for t in txns])
        if not ok:
            continue
        last = txns[-1]
        lo, hi, period = CADENCES[cadence]
        if (today.date() - last.timestamp.date()).days > hi + 10:
            continue  # stopped
        monthly = last.amount_base * {"weekly": 52 / 12, "monthly": 1, "yearly": 1 / 12}[cadence]
        sub = Subscription(
            key=key,
            merchant=last.merchant,
            cadence=cadence,
            amount=last.amount,
            currency=last.currency,
            monthly_cost_base=round(monthly, 2),
            charges=len(txns),
            first_charge=txns[0].timestamp.date().isoformat(),
            last_charge=last.timestamp.date().isoformat(),
            next_expected=_next_expected(last.timestamp, cadence).date().isoformat(),
            source=last.source,
            group=service_group(last.merchant, last.description),
        )
        if price_up:
            sub.flags.append("price_increase")
            sub.notes.append(f"Price went from {txns[0].amount:.2f} to {last.amount:.2f} {last.currency}")
        first_paid = txns[0].timestamp
        for z in zero.get(key, []):
            gap = (first_paid.date() - z.timestamp.date()).days
            if 5 <= gap <= 9 or 28 <= gap <= 32:
                sub.flags.append("trial_converted")
                sub.notes.append(f"Free trial on {z.timestamp.date()} turned into a paid plan")
                break
        if last.source == "plaid" and last.currency != ledger.base_currency:
            sub.flags.append("foreign_account")
            sub.notes.append("Charged on your old foreign account, easy to forget")
        subs.append(sub)

    groups: dict[str, list[Subscription]] = defaultdict(list)
    for s in subs:
        if s.group:
            groups[s.group].append(s)
    for group, members in groups.items():
        if len(members) >= 2:
            names = [m.merchant for m in members]
            for m in members:
                m.flags.append("duplicate_service")
                others = ", ".join(n for n in names if n != m.merchant)
                m.notes.append(f"Same kind of service ({group}) as: {others}")
    subs.sort(key=lambda s: -s.monthly_cost_base)
    return subs


def bill_check(ledger: Ledger, today: datetime, days: int = 90) -> dict:
    """The 'ADHD tax' report: fees, duplicate services, converted trials, price rises, open instalments."""
    start = today - timedelta(days=days)
    subs = detect(ledger, today)
    fees = [t for t in ledger.expenses(start, today) if t.category == "fees"]
    instalments = []
    for t in ledger.expenses(start, today):
        if t.is_instalment and t.instalment_count > 1:
            months = (today.year - t.timestamp.year) * 12 + today.month - t.timestamp.month
            remaining = max(0, t.instalment_count - months)
            if remaining:
                instalments.append({
                    "id": t.id, "merchant": t.merchant, "description": t.description,
                    "total": t.amount_base, "count": t.instalment_count,
                    "monthly": round(t.amount_base / t.instalment_count, 2), "remaining": remaining,
                    "date": t.timestamp.date().isoformat(),
                })
    bnpl = [t for t in ledger.expenses(start, today) if t.is_instalment]
    duplicates = [s for s in subs if "duplicate_service" in s.flags]
    # Keep the cheapest per group, count the rest as avoidable.
    dup_avoidable = 0.0
    seen_groups: set[str] = set()
    for s in sorted(duplicates, key=lambda s: s.monthly_cost_base):
        if s.group in seen_groups:
            dup_avoidable += s.monthly_cost_base
            s.flags.append("cancel_candidate")
        seen_groups.add(s.group or "")
    fees_total = round(sum(t.amount_base for t in fees), 2)
    return {
        "window_days": days,
        "subscriptions": [s.to_dict() for s in subs],
        "subscriptions_monthly_total": round(sum(s.monthly_cost_base for s in subs), 2),
        "fees": [t.to_dict() for t in fees],
        "fees_total": fees_total,
        "duplicate_services": [s.to_dict() for s in duplicates],
        "duplicates_avoidable_monthly": round(dup_avoidable, 2),
        "trial_conversions": [s.to_dict() for s in subs if "trial_converted" in s.flags],
        "price_increases": [s.to_dict() for s in subs if "price_increase" in s.flags],
        "foreign_account_subscriptions": [s.to_dict() for s in subs if "foreign_account" in s.flags],
        "open_instalments": instalments,
        "bnpl_spend": round(sum(t.amount_base for t in bnpl), 2),
        "avoidable_estimate_90d": round(fees_total + dup_avoidable * days / 30, 2),
    }


def median_gap(txns: list[Transaction]) -> float:
    gaps = [(b.timestamp - a.timestamp).days for a, b in zip(txns, txns[1:])]
    return statistics.median(gaps) if gaps else 0.0
