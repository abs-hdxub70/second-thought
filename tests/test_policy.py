import json
from datetime import datetime, timedelta

from second_thought.policy import plan as plan_rules
from second_thought.policy.audit_log import AuditLog
from second_thought.policy.plan import CalmPlan


def test_agent_can_only_propose_t2(toolbox):
    res = toolbox.call("save_to_pot", {"amount": 50}, actor="agent")
    assert res.status == "needs_confirmation" and res.action_id
    assert toolbox.state.pots["Japan trip"] == 1200.0  # nothing moved yet
    done = toolbox.confirm(res.action_id)
    assert done.status == "ok"
    assert toolbox.state.pots["Japan trip"] == 1250.0


def test_agent_cannot_confirm_itself(toolbox):
    res = toolbox.call("save_to_pot", {"amount": 50}, actor="agent", confirmed=True)
    assert res.status == "needs_confirmation"


def test_t3_reserved_for_rules_engine(toolbox):
    for actor in ("agent", "user"):
        res = toolbox.call("auto_save", {"amount": 10, "reason": "auto: x"}, actor=actor)
        assert res.status == "denied"


def test_unknown_tool_denied_and_logged(toolbox):
    res = toolbox.call("transfer_to_external", {"amount": 9999, "to": "someone"}, actor="agent")
    assert res.status == "denied"
    last = toolbox.state.audit.entries()[-1]
    assert last["decision"] == "denied" and last["tool"] == "transfer_to_external"


def test_essentials_never_held(toolbox):
    res = toolbox.call("auto_hold", {"title": "medicine", "amount": 500, "category": "health", "reason": "night_hold"},
                       actor="rules")
    assert res.status == "denied"


def test_daily_auto_save_cap(toolbox):
    toolbox.state.plan.daily_sweep_cap = 100
    assert toolbox.call("auto_save", {"amount": 90, "reason": "auto: a"}, actor="rules").status == "ok"
    assert toolbox.call("auto_save", {"amount": 20, "reason": "auto: b"}, actor="rules").status == "denied"


def test_asymmetric_friction():
    plan = CalmPlan()
    pending: list = []
    now = datetime(2026, 10, 20, 23, 50)
    plan, out = plan_rules.request_change(plan, pending, "night_hold_threshold", 100, now)
    assert out["status"] == "applied" and plan.night_hold_threshold == 100  # tighter: now
    plan, out = plan_rules.request_change(plan, pending, "night_hold", False, now)
    assert out["status"] == "queued" and plan.night_hold is True  # looser: later
    plan, applied = plan_rules.apply_due(plan, pending, now + timedelta(hours=23))
    assert not applied and plan.night_hold is True
    plan, applied = plan_rules.apply_due(plan, pending, now + timedelta(hours=24))
    assert applied and plan.night_hold is False


def test_more_agent_power_waits():
    plan = CalmPlan(auto_save_share=0.1)
    _, out = plan_rules.request_change(plan, [], "auto_save_share", 0.5, datetime(2026, 1, 1))
    assert out["status"] == "queued"


def test_ally_removal_waits_unless_unsafe():
    plan = CalmPlan(ally={"name": "Lin", "channel": "SMS", "alerts": ["red_flag"]})
    p2, out = plan_rules.request_change(plan, [], "ally", None, datetime(2026, 1, 1))
    assert out["status"] == "queued" and p2.ally is not None
    p3, out = plan_rules.request_change(plan, [], "ally", None, datetime(2026, 1, 1), safety_exit=True)
    assert out["status"] == "applied" and p3.ally is None


def test_night_window_crossing_midnight():
    plan = CalmPlan(night_start="23:00", night_end="06:00")
    assert plan.in_night_window(datetime(2026, 1, 1, 23, 30))
    assert plan.in_night_window(datetime(2026, 1, 2, 2, 0))
    assert not plan.in_night_window(datetime(2026, 1, 2, 12, 0))


def test_audit_chain_detects_tampering(tmp_path):
    log = AuditLog(tmp_path / "audit.jsonl")
    for i in range(5):
        log.append(actor="user", tool="t", tier="T0", decision="executed", args={"i": i})
    assert log.verify() == (True, None)
    lines = log.path.read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[2])
    entry["args"]["i"] = 99
    lines[2] = json.dumps(entry, ensure_ascii=False)
    log.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok, bad = log.verify()
    assert not ok and bad == 3


def test_every_call_is_logged(toolbox):
    before = len(toolbox.state.audit.entries())
    toolbox.call("get_safe_to_spend", actor="agent")
    toolbox.call("park_item", {"title": "x", "amount": 10}, actor="agent")
    assert len(toolbox.state.audit.entries()) == before + 2
    assert toolbox.state.audit.verify()[0]
