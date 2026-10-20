"""Regret rescue: track return windows for online purchases and draft return requests.

China: 7-day no-reason return for goods bought online, counted from receipt
(Consumer Rights Protection Law, Art. 25; custom-made, perishable, digital and print goods excluded).
EU: 14-day right of withdrawal for distance purchases.
We count from the purchase date, which is the safe side: the real deadline is never earlier.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from ..models import Transaction
from .categories import RETURNABLE_CATEGORIES
from .ledger import Ledger

WINDOW_DAYS = {"CN": 7, "EU": 14}


def candidates(ledger: Ledger, now: datetime, region: str = "CN", risk_fn=None) -> list[dict]:
    window = WINDOW_DAYS.get(region, 7)
    out = []
    for t in ledger.expenses(now - timedelta(days=window), now):
        if t.category not in RETURNABLE_CATEGORIES or "online" not in t.tags:
            continue
        deadline = t.timestamp.date() + timedelta(days=window)
        days_left = (deadline - now.date()).days
        if days_left < 0:
            continue
        item = {
            "id": t.id,
            "merchant": t.merchant,
            "description": t.description,
            "amount": t.amount,
            "currency": t.currency,
            "amount_base": t.amount_base,
            "purchased": t.timestamp.isoformat(timespec="minutes"),
            "deadline": deadline.isoformat(),
            "days_left": days_left,
            "window_days": window,
            "tags": t.tags,
        }
        if risk_fn is not None:
            risk = risk_fn(t)
            item["risk_score"] = risk.score
            item["risk_band"] = risk.band
        out.append(item)
    # Impulse buys first (most likely to be regretted), then the closest deadline, then the biggest refund.
    out.sort(key=lambda x: (0 if x.get("risk_score", 0) >= 40 else 1, x["days_left"], -x["amount_base"]))
    return out


def draft_return_request(t: Transaction | dict, region: str = "CN") -> dict[str, str]:
    get = (lambda k: t[k]) if isinstance(t, dict) else (lambda k: getattr(t, k))
    order = get("id").split("-", 1)[-1]
    when = get("purchased")[:10] if isinstance(t, dict) else t.timestamp.date().isoformat()
    item = get("description") or get("merchant")
    if region == "EU":
        en = (f"Hello,\n\nI bought \"{item}\" on {when} (order {order}). I am withdrawing from this purchase "
              f"within the 14-day withdrawal period and would like a full refund. The item is unused and in its "
              f"original packaging. Please send me the return instructions.\n\nThank you.")
        zh = (f"您好：\n\n我于 {when} 购买了「{item}」（订单号 {order}）。根据欧盟 14 天撤回权，我申请撤回本次购买并全额退款。"
              f"商品未使用，包装完好，请告知退货方式。\n\n谢谢！")
    else:
        en = (f"Hello,\n\nI bought \"{item}\" on {when} (order {order}). Under the 7-day no-reason return rule "
              f"(Consumer Rights Protection Law, Art. 25) I would like to return it for a full refund. The item is "
              f"unused and in its original packaging.\n\nThank you.")
        zh = (f"您好：\n\n我于 {when} 购买了「{item}」（订单号 {order}）。根据《消费者权益保护法》第二十五条七日无理由退货的规定，"
              f"申请退货并全额退款。商品未使用，包装完好。\n\n谢谢！")
    return {"en": en, "zh": zh}
