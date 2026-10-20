"""Impulse risk score, 0-100. Transparent: every point comes with a reason the user can read.

Signals and points (see technical documentation):
  night (23:00-05:00)                         20
  burst (3+ purchases within 60 minutes)      20
  live-stream or flash-sale merchant          15
  amount spike (> mean + 2 sd, 90 days)       15
  category on the user's trigger list         15
  instalments / BNPL                          10
  festival window or 2 days after payday      10
  low mood / high stress logged in last 3h    10
Bands: <40 green (log only), 40-69 amber (nudge), >=70 red (offer The Pause / apply calm-state hold)
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Iterable

from ..models import RiskReason, RiskResult, Transaction
from .ledger import Ledger

NIGHT_START, NIGHT_END = 23, 5
CATEGORY_ZH = {"clothing": "服饰", "beauty": "美妆", "electronics": "数码", "food": "餐饮", "household": "日用",
               "entertainment": "娱乐", "gaming": "游戏", "travel": "旅行", "sports": "运动", "gambling": "博彩",
               "subscriptions": "订阅", "other": "其他"}
AMBER, RED = 40, 70


@dataclass
class PurchaseIntent:
    """A purchase that has not happened yet (The Pause) or a transaction being scored after the fact."""
    amount_base: float
    when: datetime
    category: str = "other"
    merchant: str = ""
    title: str = ""
    tags: list[str] = field(default_factory=list)
    is_instalment: bool = False

    @classmethod
    def from_transaction(cls, t: Transaction) -> "PurchaseIntent":
        return cls(t.amount_base, t.timestamp, t.category, t.merchant, t.description, list(t.tags), t.is_instalment)


def _fourth_friday_of_november(year: int) -> date:
    d = date(year, 11, 1)
    first_friday = d + timedelta(days=(4 - d.weekday()) % 7)
    return first_friday + timedelta(weeks=3)


def festival_name(day: date) -> str | None:
    if day.month == 11 and day.day in (10, 11):
        return "Double 11 (双十一)"
    if day.month == 6 and 16 <= day.day <= 18:
        return "618 (年中大促)"
    if day.month == 12 and day.day == 12:
        return "Double 12 (双十二)"
    bf = _fourth_friday_of_november(day.year)
    if bf <= day <= bf + timedelta(days=3):
        return "Black Friday"
    return None


def is_night(when: datetime) -> bool:
    return when.hour >= NIGHT_START or when.hour < NIGHT_END


def _days_after_payday(day: date, payday: int) -> int | None:
    if payday <= 0:
        return None
    delta = day.day - payday
    return delta if 0 <= delta <= 2 else None


def score(
    intent: PurchaseIntent,
    ledger: Ledger,
    trigger_categories: Iterable[str] = (),
    payday: int = 0,
    mood_log: Iterable[dict] = (),
) -> RiskResult:
    reasons: list[RiskReason] = []

    if is_night(intent.when):
        reasons.append(RiskReason("night", 20, f"Late at night ({intent.when:%H:%M})", f"深夜消费（{intent.when:%H:%M}）"))

    recent = ledger.before(intent.when, timedelta(minutes=60))
    if len(recent) >= 2:
        reasons.append(RiskReason("burst", 20, f"Purchase number {len(recent) + 1} within an hour",
                                  f"一小时内第 {len(recent) + 1} 笔消费"))

    if "livestream" in intent.tags or "flash_sale" in intent.tags:
        label_en = "Live-stream shopping" if "livestream" in intent.tags else "Flash sale with countdown"
        label_zh = "直播购物" if "livestream" in intent.tags else "限时秒杀"
        reasons.append(RiskReason("livestream", 15, label_en, label_zh))

    history = [t.amount_base for t in ledger.expenses(intent.when - timedelta(days=90), intent.when)
               if t.category == intent.category]
    if len(history) < 5:  # not enough data in the category: compare with all discretionary spending
        history = [t.amount_base for t in ledger.expenses(intent.when - timedelta(days=90), intent.when)]
    if len(history) >= 5:
        mean = statistics.fmean(history)
        sd = statistics.pstdev(history)
        if intent.amount_base > mean + 2 * sd:
            reasons.append(RiskReason("spike", 15, f"Much bigger than usual (typical about {mean:.0f})",
                                      f"金额明显高于平时（平时约 {mean:.0f}）"))

    if intent.category in set(trigger_categories):
        reasons.append(RiskReason("trigger", 15, f"'{intent.category}' is on your trigger list",
                                  f"「{CATEGORY_ZH.get(intent.category, intent.category)}」在你的易冲动清单上"))

    if intent.is_instalment:
        reasons.append(RiskReason("instalment", 10, "Paid in instalments / buy now pay later", "分期或先买后付"))

    fest = festival_name(intent.when.date())
    after_pay = _days_after_payday(intent.when.date(), payday)
    if fest:
        reasons.append(RiskReason("festival", 10, f"Shopping festival: {fest}", f"购物节：{fest}"))
    elif after_pay is not None:
        reasons.append(RiskReason("payday", 10, "Right after payday", "刚发工资"))

    for entry in mood_log:
        ts = entry["ts"] if isinstance(entry["ts"], datetime) else datetime.fromisoformat(entry["ts"])
        if timedelta(0) <= intent.when - ts <= timedelta(hours=3) and (entry.get("mood", 3) <= 2 or entry.get("stress", 1) >= 4):
            reasons.append(RiskReason("mood", 10, "You logged a rough mood in the last 3 hours", "过去 3 小时你记录了情绪低落"))
            break

    total = min(100, sum(r.points for r in reasons))
    band = "red" if total >= RED else "amber" if total >= AMBER else "green"
    return RiskResult(total, band, reasons)


def score_transaction(t: Transaction, ledger: Ledger, **kwargs) -> RiskResult:
    return score(PurchaseIntent.from_transaction(t), ledger, **kwargs)
