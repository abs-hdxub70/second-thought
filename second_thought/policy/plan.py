"""Calm-state plan: rules the user sets while calm, plus asymmetric friction for changes.

Safer changes (more protection, less agent power) apply immediately.
Riskier changes (fewer protections, more agent power, removing the ally) wait 24 hours.
The only exception is the "I feel unsafe" exit, which removes the trusted ally immediately.
"""

from __future__ import annotations

import copy
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, time, timedelta
from typing import Any

COOLDOWN = timedelta(hours=24)


@dataclass
class CalmPlan:
    night_hold: bool = True
    night_start: str = "23:00"
    night_end: str = "06:00"
    night_hold_threshold: float = 300.0
    hold_hours: int = 12
    category_caps: dict[str, float] = field(default_factory=dict)  # monthly caps, base currency
    blocked_categories: list[str] = field(default_factory=lambda: ["gambling"])
    auto_save_share: float = 0.10  # share of a parked/skipped purchase moved to savings automatically
    daily_sweep_cap: float = 100.0
    ally: dict[str, Any] | None = None  # {"name": ..., "channel": ..., "alerts": ["red_flag"]}
    ally_auto_alert: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "CalmPlan":
        return cls(**(d or {}))

    # ---- helpers --------------------------------------------------------
    def _t(self, value: str) -> time:
        h, m = value.split(":")
        return time(int(h), int(m))

    def window_minutes(self, start: str | None = None, end: str | None = None) -> int:
        s, e = self._t(start or self.night_start), self._t(end or self.night_end)
        sm, em = s.hour * 60 + s.minute, e.hour * 60 + e.minute
        return (em - sm) % (24 * 60)

    def in_night_window(self, when: datetime) -> bool:
        s, e = self._t(self.night_start), self._t(self.night_end)
        now = when.time()
        return (now >= s or now < e) if s > e else (s <= now < e)


def classify(plan: CalmPlan, path: str, value: Any) -> str:
    """Return 'safer' or 'riskier' for setting `path` to `value`."""
    if path == "night_hold":
        return "safer" if value and not plan.night_hold else ("riskier" if not value and plan.night_hold else "safer")
    if path == "night_window":
        start, end = value
        return "safer" if plan.window_minutes(start, end) >= plan.window_minutes() else "riskier"
    if path == "night_hold_threshold":
        return "safer" if float(value) <= plan.night_hold_threshold else "riskier"
    if path == "hold_hours":
        return "safer" if int(value) >= plan.hold_hours else "riskier"
    if path.startswith("category_caps."):
        cat = path.split(".", 1)[1]
        current = plan.category_caps.get(cat)
        if value is None:
            return "riskier" if current is not None else "safer"
        return "safer" if current is None or float(value) <= current else "riskier"
    if path.startswith("blocked_categories."):
        cat = path.split(".", 1)[1]
        blocked = cat in plan.blocked_categories
        return "safer" if value or not blocked else "riskier"
    if path in ("auto_save_share", "daily_sweep_cap"):
        return "safer" if float(value) <= float(getattr(plan, path)) else "riskier"  # more agent power waits
    if path == "ally":
        return "riskier" if value is None and plan.ally is not None else "safer"
    if path == "ally_auto_alert":
        return "safer" if value else "riskier"
    raise ValueError(f"Unknown plan setting: {path}")


def apply(plan: CalmPlan, path: str, value: Any) -> CalmPlan:
    p = copy.deepcopy(plan)
    if path == "night_window":
        p.night_start, p.night_end = value
    elif path.startswith("category_caps."):
        cat = path.split(".", 1)[1]
        if value is None:
            p.category_caps.pop(cat, None)
        else:
            p.category_caps[cat] = float(value)
    elif path.startswith("blocked_categories."):
        cat = path.split(".", 1)[1]
        if value and cat not in p.blocked_categories:
            p.blocked_categories.append(cat)
        if not value and cat in p.blocked_categories:
            p.blocked_categories.remove(cat)
    elif path in ("night_hold", "night_hold_threshold", "hold_hours", "auto_save_share",
                  "daily_sweep_cap", "ally", "ally_auto_alert"):
        current = getattr(p, path)
        if isinstance(current, float):
            value = float(value)
        elif isinstance(current, bool):
            value = bool(value)
        elif isinstance(current, int):
            value = int(value)
        setattr(p, path, value)
    else:
        raise ValueError(f"Unknown plan setting: {path}")
    return p


def request_change(plan: CalmPlan, pending: list[dict], path: str, value: Any, now: datetime,
                   safety_exit: bool = False) -> tuple[CalmPlan, dict]:
    """Apply a safer change now, or queue a riskier one for 24 hours. Returns (plan, outcome)."""
    kind = classify(plan, path, value)
    if kind == "safer" or (safety_exit and path == "ally" and value is None):
        new_plan = apply(plan, path, value)
        return new_plan, {"status": "applied", "kind": kind, "path": path, "value": value,
                          "safety_exit": bool(safety_exit)}
    change = {
        "id": uuid.uuid4().hex[:8],
        "path": path,
        "value": value,
        "requested_at": now.isoformat(timespec="minutes"),
        "effective_at": (now + COOLDOWN).isoformat(timespec="minutes"),
    }
    pending.append(change)
    return plan, {"status": "queued", "kind": kind, **change}


def apply_due(plan: CalmPlan, pending: list[dict], now: datetime) -> tuple[CalmPlan, list[dict]]:
    """Apply queued changes whose cooldown has passed. Returns (plan, applied)."""
    applied = []
    for change in list(pending):
        if datetime.fromisoformat(change["effective_at"]) <= now:
            plan = apply(plan, change["path"], change["value"])
            pending.remove(change)
            applied.append(change)
    return plan, applied
