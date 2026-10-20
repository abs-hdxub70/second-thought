"""Assistant entry point: safety check first, then the LLM agent if configured, else the offline agent."""

from __future__ import annotations

from typing import Any

from .llm import LLMAgent, LLMConfig
from .router import OfflineAgent
from .safety import check_message, crisis_reply, distress_line
from .tools import Toolbox


class Assistant:
    def __init__(self, toolbox: Toolbox, use_llm: bool = True):
        self.tb = toolbox
        self.offline = OfflineAgent(toolbox)
        self.config = LLMConfig.from_env() if use_llm else None
        self.notice = ""
        region = toolbox.state.profile.get("region", "CN")
        if self.config and not self.config.allowed_for(region):
            self.notice = (f"LLM provider '{self.config.provider}' is hosted outside China, so it is not used for CN users "
                           f"(data residency). Running the offline agent.")
            self.config = None

    @property
    def mode(self) -> str:
        return f"llm:{self.config.provider}" if self.config else "offline"

    def respond(self, text: str, history: list[dict] | None = None, lang: str = "en") -> dict[str, Any]:
        region = self.tb.state.profile.get("region", "CN")
        safety = check_message(text)
        self.tb.state.audit.append(actor="user", tool="chat_message", tier="-", decision="received",
                                   args={"safety": safety, "chars": len(text)}, scenario_time=self.tb.state.now())
        if safety == "crisis":
            self.tb.state.audit.append(actor="agent", tool="crisis_protocol", tier="-", decision="executed",
                                       args={"region": region}, scenario_time=self.tb.state.now(),
                                       note="finance flow stopped, helplines shown")
            return {"text": crisis_reply(region, lang), "events": [], "crisis": True, "mode": "safety",
                    "label": "Safety message"}
        out: dict[str, Any]
        if self.config:
            try:
                out = LLMAgent(self.tb, self.config).respond(text, history or [], lang)
                out["mode"], out["label"] = self.mode, "AI-generated"
            except Exception as exc:  # network or provider problem: fall back, never leave the user hanging
                out = self.offline.respond(text, lang)
                out["mode"], out["label"] = "offline", "Automated reply (offline fallback)"
                out["error"] = str(exc)[:200]
        else:
            out = self.offline.respond(text, lang)
            out["mode"], out["label"] = "offline", "Automated reply"
        if safety == "distress":
            out["text"] += distress_line(region, lang)
        out["crisis"] = False
        out["pending"] = [e["action_id"] for e in out.get("events", []) if e.get("status") == "needs_confirmation"]
        return out


__all__ = ["Assistant", "Toolbox"]
