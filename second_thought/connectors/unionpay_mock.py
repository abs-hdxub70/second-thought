"""UnionPay (银联) card statement adapter. MOCK: reads a synthetic JSON statement.

There is no public consumer API for reading UnionPay card history, so this adapter shows the
interface a bank partner would plug into. Fields mirror a typical card statement line.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..engine.categories import enrich
from ..models import EXPENSE, INCOME, NEUTRAL, Transaction
from .base import parse_datetime


class UnionPayMockConnector:
    name = "unionpay"
    region = "CN/global"
    status = "mock"

    def load(self, source: str | Path | bytes) -> list[Transaction]:
        data = source if isinstance(source, bytes) else Path(source).read_bytes()
        statement = json.loads(data.decode("utf-8"))
        out: list[Transaction] = []
        for line in statement.get("lines", []):
            kind = line.get("type", "debit")
            direction = {"debit": EXPENSE, "credit": INCOME}.get(kind, NEUTRAL)
            txn = Transaction(
                id="up-" + line["ref"],
                source=self.name,
                timestamp=parse_datetime(line["time"]),
                amount=abs(float(line["amount"])),
                currency=line.get("currency", "CNY"),
                direction=direction,
                merchant=line.get("merchant", ""),
                description=line.get("memo", ""),
                category="other",
                payment_method=statement.get("card_label", "UnionPay debit"),
                status="posted",
                mcc=line.get("mcc"),
            )
            out.append(enrich(txn))
        return out
