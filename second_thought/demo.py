"""Load the synthetic persona Mei into a state, ready for the demo."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .policy.plan import CalmPlan
from .state import AppState

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

FILES = [
    ("alipay", "alipay_bill_mei.csv"),
    ("wechat", "wechat_bill_mei.csv"),
    ("unionpay", "unionpay_statement_mei.json"),
    ("plaid", "plaid_sandbox_transactions.json"),
]


def load_demo(state: AppState, data_dir: Path = DATA_DIR, set_clock: bool = True) -> dict:
    """Reset the state and import Mei's synthetic exports. Returns counts per source."""
    state.reset()
    seed = json.loads((data_dir / "profile_mei.json").read_text(encoding="utf-8"))
    state.profile = seed["profile"]
    state.plan = CalmPlan.from_dict(seed["plan"])
    state.mood_log = seed.get("mood_log", [])
    state.pots = seed.get("pots", {})
    if set_clock and seed.get("demo_clock"):
        state.set_clock(datetime.fromisoformat(seed["demo_clock"]))
    state.rebuild_ledger()
    counts = {}
    for source, name in FILES:
        counts[source] = state.import_file(source, (data_dir / name).read_bytes(), name)
    state.save()
    state.audit.append(actor="user", tool="import_demo_data", tier="T0 Observe", decision="executed",
                       args={"files": [n for _, n in FILES]}, result=counts, scenario_time=state.now(),
                       note="synthetic persona, separate consent for financial data recorded in profile")
    return counts
