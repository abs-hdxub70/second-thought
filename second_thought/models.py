"""Core data models shared by connectors, engines, policy and agent."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Optional

EXPENSE = "expense"
INCOME = "income"
NEUTRAL = "neutral"  # transfers, red packets between own accounts, credit repayments


@dataclass
class Transaction:
    id: str
    source: str  # alipay | wechat | plaid | unionpay
    timestamp: datetime  # local time of the user
    amount: float  # always positive, in original currency
    currency: str
    direction: str  # expense | income | neutral
    merchant: str
    description: str = ""
    raw_category: str = ""
    category: str = "other"
    payment_method: str = ""
    status: str = ""
    mcc: Optional[str] = None
    is_instalment: bool = False
    instalment_count: int = 0
    tags: list[str] = field(default_factory=list)  # livestream, flash_sale, online, fee, subscription_like
    amount_base: float = 0.0  # converted to the user's base currency
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def is_expense(self) -> bool:
        return self.direction == EXPENSE

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        d.pop("raw", None)
        return d


@dataclass
class RiskReason:
    code: str
    points: int
    en: str
    zh: str


@dataclass
class RiskResult:
    score: int
    band: str  # green | amber | red
    reasons: list[RiskReason]

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "band": self.band,
            "reasons": [asdict(r) for r in self.reasons],
        }
