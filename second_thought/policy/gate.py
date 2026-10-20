"""Permission gate. Every tool call, from the UI, the agent or the rules engine, passes through here.

Tiers
  T0 Observe   read, compute, show                     -> runs
  T1 Advise    nudges, The Pause, recommendations       -> runs, no side effects
  T2 Confirm   park, save to own pot, drafts, budgets   -> agent can only PROPOSE; a person confirms
  T3 Bounded   night holds, auto-save, ally alert       -> only the deterministic rules engine, only
                                                           rules the user set while calm, within caps
  Never        pay third parties, borrow, trade, change credentials -> no such tools exist

The model never moves money on its own: its strongest move is a proposal waiting for a tap.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable

from ..state import AppState


class Tier(IntEnum):
    T0 = 0
    T1 = 1
    T2 = 2
    T3 = 3


TIER_LABELS = {
    Tier.T0: "T0 Observe",
    Tier.T1: "T1 Advise",
    Tier.T2: "T2 Act after confirmation",
    Tier.T3: "T3 Act within pre-set limits",
}

ACTORS = ("user", "agent", "rules")


@dataclass
class ToolSpec:
    name: str
    tier: Tier
    fn: Callable[..., Any]
    description: str
    params: dict[str, Any] = field(default_factory=lambda: {"type": "object", "properties": {}})
    check: Callable[[dict[str, Any]], str | None] | None = None
    agent_visible: bool = True


@dataclass
class GateResult:
    status: str  # ok | needs_confirmation | denied
    result: Any = None
    message: str = ""
    action_id: str | None = None
    tool: str = ""
    tier: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "result": self.result, "message": self.message,
                "action_id": self.action_id, "tool": self.tool, "tier": self.tier}


class Gate:
    def __init__(self, state: AppState):
        self.state = state
        self.tools: dict[str, ToolSpec] = {}
        self._via = ""

    def register(self, spec: ToolSpec) -> None:
        self.tools[spec.name] = spec

    def agent_tools(self) -> list[ToolSpec]:
        return [t for t in self.tools.values() if t.agent_visible and t.tier <= Tier.T2]

    def _log(self, actor: str, spec_name: str, tier: str, decision: str, args: dict, result: Any = None,
             note: str = "") -> None:
        if self._via:
            note = f"{note} · via {self._via}" if note else f"via {self._via}"
        self.state.audit.append(actor=actor, tool=spec_name, tier=tier, decision=decision, args=args,
                                result=_summarise(result), scenario_time=self.state.now(), note=note)

    def call(self, name: str, args: dict[str, Any] | None = None, actor: str = "agent",
             confirmed: bool = False, via: str = "") -> GateResult:
        """`via` names the surface a person used (e.g. the browser extension); it is only logged."""
        args = dict(args or {})
        if actor not in ACTORS:
            raise ValueError(f"Unknown actor {actor}")
        previous, self._via = self._via, via
        try:
            return self._call(name, args, actor, confirmed)
        finally:
            self._via = previous

    def _call(self, name: str, args: dict[str, Any], actor: str, confirmed: bool) -> GateResult:
        spec = self.tools.get(name)
        if spec is None:
            self._log(actor, name, "-", "denied", args, note="unknown tool")
            return GateResult("denied", message=f"'{name}' is not an available action.", tool=name)
        tier = TIER_LABELS[spec.tier]
        if spec.tier == Tier.T3 and actor != "rules":
            self._log(actor, name, tier, "denied", args, note="T3 is reserved for the rules engine")
            return GateResult("denied", message="Only rules you set while calm can trigger this.", tool=name, tier=tier)
        if actor == "agent" and not spec.agent_visible:
            self._log(actor, name, tier, "denied", args, note="not exposed to the agent")
            return GateResult("denied", message="The assistant cannot run this action.", tool=name, tier=tier)
        reason = spec.check(args) if spec.check else None
        if reason:
            self._log(actor, name, tier, "denied", args, note=reason)
            return GateResult("denied", message=reason, tool=name, tier=tier)
        if spec.tier == Tier.T2 and not (confirmed and actor == "user"):
            action_id = uuid.uuid4().hex[:8]
            self.state.pending_actions[action_id] = {"tool": name, "args": args, "proposed_by": actor,
                                                     "proposed_at": self.state.now().isoformat(timespec="minutes")}
            self.state.save()
            self._log(actor, name, tier, "proposed", args, note=f"awaiting confirmation {action_id}")
            return GateResult("needs_confirmation", message="Waiting for your confirmation.",
                              action_id=action_id, tool=name, tier=tier)
        try:
            result = spec.fn(**args)
        except (ValueError, KeyError) as exc:
            self._log(actor, name, tier, "failed", args, note=str(exc))
            return GateResult("denied", message=str(exc), tool=name, tier=tier)
        self.state.save()
        self._log(actor, name, tier, "executed", args, result)
        return GateResult("ok", result=result, tool=name, tier=tier)

    def confirm(self, action_id: str) -> GateResult:
        pending = self.state.pending_actions.pop(action_id, None)
        if pending is None:
            return GateResult("denied", message="That proposal no longer exists.")
        self.state.audit.append(actor="user", tool=pending["tool"], tier="T2 Act after confirmation",
                                decision="confirmed", args=pending["args"], scenario_time=self.state.now(),
                                note=f"action {action_id}")
        return self.call(pending["tool"], pending["args"], actor="user", confirmed=True)

    def reject(self, action_id: str) -> GateResult:
        pending = self.state.pending_actions.pop(action_id, None)
        if pending is None:
            return GateResult("denied", message="That proposal no longer exists.")
        self.state.save()
        self.state.audit.append(actor="user", tool=pending["tool"], tier="T2 Act after confirmation",
                                decision="rejected", args=pending["args"], scenario_time=self.state.now(),
                                note=f"action {action_id}")
        return GateResult("ok", message="Dismissed.", tool=pending["tool"])


def _summarise(result: Any) -> Any:
    """Keep the audit log readable: store small results whole, big ones as a summary."""
    if result is None or isinstance(result, (int, float, str, bool)):
        return result
    if isinstance(result, dict):
        small = {k: v for k, v in result.items() if isinstance(v, (int, float, str, bool)) or v is None}
        return small or {"keys": list(result)[:10]}
    if isinstance(result, list):
        return {"items": len(result)}
    return str(result)[:200]
