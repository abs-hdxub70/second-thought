"""Application state: profile, plan, parking lot, savings pots, drafts, logs. Persisted per region.

Data residency: each region gets its own folder (state/cn, state/eu), so CN users' data never
lands in the EU store and vice versa. Optional encryption at rest with a Fernet key in
ST_ENCRYPTION_KEY (generate one with `python scripts/make_key.py`).
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .connectors import AlipayCSVConnector, PlaidSandboxConnector, UnionPayMockConnector, WeChatBillConnector
from .engine.ledger import Ledger
from .policy.audit_log import AuditLog
from .policy.plan import CalmPlan

DEFAULT_ROOT = Path(os.getenv("ST_STATE_DIR", ".st_state"))


def _fernet():
    key = os.getenv("ST_ENCRYPTION_KEY")
    if not key:
        return None
    from cryptography.fernet import Fernet

    return Fernet(key.encode())


@dataclass
class AppState:
    state_dir: Path
    profile: dict[str, Any] = field(default_factory=dict)
    plan: CalmPlan = field(default_factory=CalmPlan)
    pending_changes: list[dict] = field(default_factory=list)
    parking: list[dict] = field(default_factory=list)
    pots: dict[str, float] = field(default_factory=dict)
    drafts: list[dict] = field(default_factory=list)
    mood_log: list[dict] = field(default_factory=list)
    outbox: list[dict] = field(default_factory=list)
    pending_actions: dict[str, dict] = field(default_factory=dict)
    sandbox_ops: list[dict] = field(default_factory=list)
    imports: list[dict] = field(default_factory=list)
    clock: str | None = None  # simulated "now" for demos, ISO string
    last_red: str | None = None
    ledger: Ledger = field(default_factory=Ledger)

    PERSISTED = ("profile", "plan", "pending_changes", "parking", "pots", "drafts", "mood_log", "outbox",
                 "pending_actions", "sandbox_ops", "imports", "clock", "last_red")

    # ---- paths ------------------------------------------------------------
    @property
    def audit(self) -> AuditLog:
        return AuditLog(self.state_dir / "audit_log.jsonl")

    @property
    def plaid_log(self) -> Path:
        return self.state_dir / "plaid_requests.jsonl"

    @property
    def _file(self) -> Path:
        return self.state_dir / ("state.json.enc" if _fernet() else "state.json")

    # ---- clock ------------------------------------------------------------
    def now(self) -> datetime:
        return datetime.fromisoformat(self.clock) if self.clock else datetime.now().replace(microsecond=0)

    def set_clock(self, when: datetime | None) -> None:
        self.clock = when.isoformat(timespec="minutes") if when else None

    # ---- persistence --------------------------------------------------------
    def save(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        data = {k: getattr(self, k) for k in self.PERSISTED}
        data["plan"] = self.plan.to_dict()
        raw = json.dumps(data, ensure_ascii=False, indent=2, default=str).encode("utf-8")
        f = _fernet()
        self._file.write_bytes(f.encrypt(raw) if f else raw)

    @classmethod
    def load(cls, state_dir: Path) -> "AppState":
        state = cls(state_dir=Path(state_dir))
        path = state._file
        if path.exists():
            raw = path.read_bytes()
            f = _fernet()
            data = json.loads((f.decrypt(raw) if f else raw).decode("utf-8"))
            for k in cls.PERSISTED:
                if k in data:
                    setattr(state, k, data[k])
            state.plan = CalmPlan.from_dict(data.get("plan"))
        state.rebuild_ledger()
        return state

    @classmethod
    def for_region(cls, region: str, root: Path | None = None) -> "AppState":
        return cls.load((root or DEFAULT_ROOT) / region.lower())

    def reset(self) -> None:
        if self.state_dir.exists():
            shutil.rmtree(self.state_dir)
        fresh = AppState(state_dir=self.state_dir)
        for k in self.PERSISTED + ("plan", "ledger"):
            setattr(self, k, getattr(fresh, k))

    # ---- data imports ---------------------------------------------------------
    def connector(self, source: str):
        if source == "alipay":
            return AlipayCSVConnector()
        if source == "wechat":
            return WeChatBillConnector()
        if source == "unionpay":
            return UnionPayMockConnector()
        if source == "plaid":
            return PlaidSandboxConnector(request_log=self.plaid_log)
        raise ValueError(f"Unknown source {source}")

    def import_file(self, source: str, data: bytes, filename: str) -> int:
        """Store the user's export locally and add it to the ledger. Returns number of new transactions."""
        f = _fernet()
        target = self.state_dir / "imports" / f"{source}__{Path(filename).name}{'.enc' if f else ''}"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(f.encrypt(data) if f else data)
        conn = self.connector(source)
        if source == "plaid":
            conn.offline = True  # a file upload is always the fixture / exported JSON
        added = self.ledger.add(conn.load(data))
        entry = {"source": source, "path": str(target)}
        if entry not in self.imports:
            self.imports.append(entry)
        return added

    def import_plaid_live(self) -> int:
        conn = PlaidSandboxConnector(request_log=self.plaid_log, offline=False)
        txns = conn.load()
        target = self.state_dir / "imports" / "plaid__live.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"added": [], "note": "live sandbox pull, re-fetch on load"}), encoding="utf-8")
        return self.ledger.add(txns)

    def rebuild_ledger(self) -> None:
        self.ledger = Ledger(base_currency=self.profile.get("base_currency", "CNY"))
        for item in self.imports:
            path = Path(item["path"])
            if not path.exists() or path.name == "plaid__live.json":
                continue
            conn = self.connector(item["source"])
            if item["source"] == "plaid":
                conn.offline = True
            raw = path.read_bytes()
            if path.suffix == ".enc":
                f = _fernet()
                if f is None:
                    continue  # encrypted import but no key in this environment
                raw = f.decrypt(raw)
            self.ledger.add(conn.load(raw))
