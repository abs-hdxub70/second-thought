"""Append-only audit log with a hash chain.

Each line stores the SHA-256 of the previous line, so editing or deleting any entry breaks
verification from that point on. The same file is our execution evidence for the submission.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

GENESIS = "0" * 64


def _canonical(entry: dict[str, Any]) -> str:
    return json.dumps(entry, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def entry_hash(entry: dict[str, Any]) -> str:
    body = {k: v for k, v in entry.items() if k != "hash"}
    return hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()


class AuditLog:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def entries(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        with self.path.open(encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def head(self) -> tuple[int, str]:
        entries = self.entries()
        if not entries:
            return 0, GENESIS
        return entries[-1]["seq"], entries[-1]["hash"]

    def append(self, *, actor: str, tool: str, tier: str, decision: str, args: dict[str, Any] | None = None,
               result: Any = None, scenario_time: datetime | None = None, note: str = "") -> dict[str, Any]:
        seq, prev = self.head()
        entry = {
            "seq": seq + 1,
            "wall_time": datetime.now().isoformat(timespec="seconds"),
            "scenario_time": scenario_time.isoformat(timespec="minutes") if scenario_time else None,
            "actor": actor,
            "tool": tool,
            "tier": tier,
            "decision": decision,
            "args": args or {},
            "result": result,
            "note": note,
            "prev_hash": prev,
        }
        entry["hash"] = entry_hash(entry)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        return entry

    def verify(self) -> tuple[bool, int | None]:
        """Return (ok, first_bad_seq)."""
        prev = GENESIS
        for e in self.entries():
            if e.get("prev_hash") != prev or entry_hash(e) != e.get("hash"):
                return False, e.get("seq")
            prev = e["hash"]
        return True, None

    def daily_anchor(self) -> dict[str, Any]:
        """Head hash to anchor externally (e.g. on a testnet) as a tamper-evidence checkpoint."""
        seq, head = self.head()
        return {"entries": seq, "head_hash": head, "generated": datetime.now().isoformat(timespec="seconds")}
