import sys
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from second_thought.agent import Assistant, Toolbox  # noqa: E402
from second_thought.demo import DATA_DIR, load_demo  # noqa: E402
from second_thought.engine.ledger import Ledger  # noqa: E402
from second_thought.models import EXPENSE, Transaction  # noqa: E402
from second_thought.state import AppState  # noqa: E402


@pytest.fixture()
def demo_state(tmp_path):
    state = AppState(state_dir=tmp_path / "cn")
    load_demo(state, DATA_DIR)
    return state


@pytest.fixture()
def toolbox(demo_state):
    return Toolbox(demo_state)


@pytest.fixture()
def bot(toolbox):
    return Assistant(toolbox, use_llm=False)


def txn(when: str, amount: float, merchant: str = "Shop", category: str = "clothing", tags=None,
        currency: str = "CNY", description: str = "", **kw) -> Transaction:
    t = Transaction(id=f"t-{when}-{amount}-{merchant}", source="test", timestamp=datetime.fromisoformat(when),
                    amount=amount, currency=currency, direction=kw.pop("direction", EXPENSE), merchant=merchant,
                    description=description, category=category, tags=list(tags or []), **kw)
    return t


@pytest.fixture()
def make_ledger():
    def _make(txns):
        led = Ledger()
        led.add(txns)
        return led
    return _make
