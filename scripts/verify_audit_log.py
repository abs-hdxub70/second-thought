"""Verify the hash chain of an audit log file.

Usage: python scripts/verify_audit_log.py evidence/audit_log.jsonl
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from second_thought.policy.audit_log import AuditLog  # noqa: E402

log = AuditLog(Path(sys.argv[1] if len(sys.argv) > 1 else "evidence/audit_log.jsonl"))
ok, bad = log.verify()
seq, head = log.head()
print(f"entries: {seq}\nhead hash: {head}\nchain intact: {ok}" + ("" if ok else f"\nfirst broken entry: {bad}"))
sys.exit(0 if ok else 1)
