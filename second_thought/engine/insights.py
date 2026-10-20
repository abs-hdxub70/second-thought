"""Money mirror: the weekly look back. Numbers only, one suggestion, no lectures."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta

from .categories import DISCRETIONARY_CATEGORIES
from .ledger import Ledger
from .risk_score import AMBER, is_night


def _parse_ts(value) -> datetime:
    return value if isinstance(value, datetime) else datetime.fromisoformat(value)


def money_mirror(ledger: Ledger, now: datetime, risk_fn, mood_log: list[dict], days: int = 7,
                 duplicates_monthly: float = 0.0, night_hold_on: bool = False, night_threshold: float = 0.0,
                 symbol: str = "") -> dict:
    start = now - timedelta(days=days)
    spend = [t for t in ledger.expenses(start, now) if t.category in DISCRETIONARY_CATEGORIES]
    total = round(sum(t.amount_base for t in spend), 2)

    by_hour = [0.0] * 24
    by_category: dict[str, float] = defaultdict(float)
    impulse = night = live = 0.0
    night_count = night_below = 0
    impulse_items = []
    for t in spend:
        by_hour[t.timestamp.hour] += t.amount_base
        by_category[t.category] += t.amount_base
        risk = risk_fn(t)
        if risk.score >= AMBER:
            impulse += t.amount_base
            impulse_items.append({"merchant": t.merchant, "description": t.description,
                                  "amount_base": t.amount_base, "score": risk.score,
                                  "when": t.timestamp.isoformat(timespec="minutes")})
        if is_night(t.timestamp):
            night += t.amount_base
            night_count += 1
            if t.amount_base < night_threshold:
                night_below += 1
        if "livestream" in t.tags:
            live += t.amount_base

    rough_days: set[date] = set()
    for m in mood_log:
        ts = _parse_ts(m["ts"])
        if start <= ts <= now and (m.get("mood", 3) <= 2 or m.get("stress", 1) >= 4):
            rough_days.add(ts.date())
    per_day: dict[date, float] = defaultdict(float)
    for t in spend:
        per_day[t.timestamp.date()] += t.amount_base
    all_days = [start.date() + timedelta(days=i + 1) for i in range(days)]
    rough = [per_day.get(d, 0.0) for d in all_days if d in rough_days]
    calm = [per_day.get(d, 0.0) for d in all_days if d not in rough_days]
    rough_avg = round(sum(rough) / len(rough), 2) if rough else None
    calm_avg = round(sum(calm) / len(calm), 2) if calm else None

    share = lambda x: round(x / total, 3) if total else 0.0  # noqa: E731
    night_share, live_share, impulse_share = share(night), share(live), share(impulse)

    if night_share >= 0.4 and night_hold_on and night_below:
        lower = max(50, int(night_threshold / 3 // 10 * 10))
        rec = {"code": "lower_night_threshold",
               "en": f"{night_share:.0%} of this week's spending happened late at night, and {night_below} of those {night_count} buys were under "
                     f"your {symbol}{night_threshold:.0f} night-hold threshold. Lowering it to {symbol}{lower} would catch them.",
               "zh": f"本周 {night_share:.0%} 的消费发生在深夜，其中 {night_count} 笔里有 {night_below} 笔低于你的夜间暂缓门槛 {symbol}{night_threshold:.0f}。"
                     f"把门槛降到 {symbol}{lower}，就能拦下它们。"}
    elif night_share >= 0.4:
        rec = {"code": "night_hold",
               "en": f"{night_share:.0%} of this week's spending happened late at night. A night hold in your calm-state plan would catch most of it.",
               "zh": f"本周 {night_share:.0%} 的消费发生在深夜。在冷静计划里开启夜间暂缓，可以拦下其中大部分。"}
    elif live_share >= 0.25:
        rec = {"code": "livestream_shield",
               "en": f"Live streams made up {live_share:.0%} of your spending. Try parking live-stream buys for 24 hours.",
               "zh": f"直播购物占你消费的 {live_share:.0%}。试试把直播下单先放进等待区 24 小时。"}
    elif duplicates_monthly > 0:
        rec = {"code": "duplicates",
               "en": f"You pay about {symbol}{duplicates_monthly:.0f} a month for services that overlap. Cancelling one is the easiest win this week.",
               "zh": f"你每月约有 {symbol}{duplicates_monthly:.0f} 花在重复的会员上。取消一个是本周最容易的改变。"}
    else:
        rec = {"code": "keep_going",
               "en": "No strong pattern this week. Keep logging your mood, it makes next week's mirror sharper.",
               "zh": "本周没有明显的冲动模式。继续记录心情，下周的复盘会更准确。"}

    return {
        "window": f"{start.date()} to {now.date()}",
        "discretionary_total": total,
        "impulse_spend": round(impulse, 2),
        "impulse_share": impulse_share,
        "night_spend": round(night, 2),
        "night_share": night_share,
        "night_purchases": night_count,
        "night_purchases_below_threshold": night_below,
        "livestream_spend": round(live, 2),
        "livestream_share": live_share,
        "by_hour": [round(x, 2) for x in by_hour],
        "by_category": dict(sorted(((k, round(v, 2)) for k, v in by_category.items()), key=lambda kv: -kv[1])),
        "rough_day_avg": rough_avg,
        "calm_day_avg": calm_avg,
        "rough_days": len(rough),
        "impulse_items": sorted(impulse_items, key=lambda x: -x["score"])[:8],
        "recommendation": rec,
    }
