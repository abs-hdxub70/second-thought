"""Unified ledger: merge all sources, convert currencies, drop duplicates, answer queries."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterable

from ..models import EXPENSE, INCOME, Transaction

# Fixed demo reference rates (units of base currency per 1 unit of foreign currency).
# In production these come from the PBoC / ECB daily reference rates.
DEMO_FX_TO_CNY = {"CNY": 1.0, "EUR": 7.80, "USD": 7.10, "GBP": 9.20, "HKD": 0.91, "JPY": 0.047}
FX_NOTE = "Fixed demo rates, replace with daily reference rates in production."


def convert(amount: float, currency: str, base: str = "CNY") -> float:
    if currency == base:
        return round(amount, 2)
    to_cny = DEMO_FX_TO_CNY.get(currency.upper())
    base_to_cny = DEMO_FX_TO_CNY.get(base.upper())
    if to_cny is None or base_to_cny is None:
        raise ValueError(f"No demo FX rate for {currency}->{base}")
    return round(amount * to_cny / base_to_cny, 2)


@dataclass
class Ledger:
    base_currency: str = "CNY"
    transactions: list[Transaction] = field(default_factory=list)

    def add(self, txns: Iterable[Transaction]) -> int:
        seen = {t.id for t in self.transactions}
        added = 0
        for t in txns:
            if t.id in seen:
                continue
            t.amount_base = convert(t.amount, t.currency, self.base_currency)
            self.transactions.append(t)
            seen.add(t.id)
            added += 1
        self.transactions.sort(key=lambda t: t.timestamp)
        return added

    def expenses(self, start: datetime | None = None, end: datetime | None = None) -> list[Transaction]:
        return [
            t for t in self.transactions
            if t.direction == EXPENSE and (start is None or t.timestamp >= start) and (end is None or t.timestamp <= end)
        ]

    def income(self, start: datetime | None = None, end: datetime | None = None) -> list[Transaction]:
        return [
            t for t in self.transactions
            if t.direction == INCOME and (start is None or t.timestamp >= start) and (end is None or t.timestamp <= end)
        ]

    def before(self, when: datetime, window: timedelta) -> list[Transaction]:
        """Expenses in the window ending at `when` (exclusive)."""
        return [t for t in self.transactions if t.direction == EXPENSE and when - window <= t.timestamp < when]

    def by_id(self, txn_id: str) -> Transaction | None:
        return next((t for t in self.transactions if t.id == txn_id), None)

    def sources(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for t in self.transactions:
            counts[t.source] = counts.get(t.source, 0) + 1
        return counts
