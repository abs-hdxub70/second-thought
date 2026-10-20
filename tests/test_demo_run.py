import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import run_demo  # noqa: E402


def test_demo_run_writes_evidence(tmp_path):
    summary = run_demo.run(tmp_path)
    assert summary["audit_chain_ok"]
    assert summary["denied_actions"] >= 3
    assert summary["plan_after"]["night_hold"] is False  # applied only after the 24h cooldown
    for name in ("demo_transcript.md", "audit_log.jsonl", "sandbox_operations.json", "summary.json"):
        assert (tmp_path / name).exists()
    ops = json.loads((tmp_path / "sandbox_operations.json").read_text(encoding="utf-8"))
    assert ops["sandbox_ops"] and all(op["status"] == "settled (sandbox)" for op in ops["sandbox_ops"])
