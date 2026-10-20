"""LLM agent over any OpenAI-compatible chat endpoint (DeepSeek, Qwen/DashScope, others).

Data residency: for users in the CN region we only call providers hosted in China.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from .prompts import SYSTEM_PROMPT
from .safety import Redactor
from .tools import Toolbox

PRESETS = {
    "deepseek": {"base_url": "https://api.deepseek.com", "model": "deepseek-chat", "region": "CN"},
    "qwen": {"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen-plus", "region": "CN"},
    "qwen-intl": {"base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1", "model": "qwen-plus", "region": "INTL"},
}


@dataclass
class LLMConfig:
    provider: str
    base_url: str
    model: str
    api_key: str
    region: str

    @classmethod
    def from_env(cls) -> "LLMConfig | None":
        key = os.getenv("LLM_API_KEY", "")
        if not key:
            return None
        provider = os.getenv("LLM_PROVIDER", "deepseek").lower()
        preset = PRESETS.get(provider, {})
        base_url = os.getenv("LLM_BASE_URL", preset.get("base_url", ""))
        model = os.getenv("LLM_MODEL", preset.get("model", ""))
        if not base_url or not model:
            return None
        return cls(provider, base_url.rstrip("/"), model, key, os.getenv("LLM_REGION", preset.get("region", "INTL")))

    def allowed_for(self, user_region: str) -> bool:
        return user_region != "CN" or self.region == "CN"


class LLMAgent:
    def __init__(self, toolbox: Toolbox, config: LLMConfig, max_steps: int = 6, timeout: int = 45):
        self.tb = toolbox
        self.cfg = config
        self.max_steps = max_steps
        self.timeout = timeout

    def _post(self, messages: list[dict], tools: list[dict]) -> dict:
        import requests

        resp = requests.post(
            f"{self.cfg.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.cfg.api_key}", "Content-Type": "application/json"},
            json={"model": self.cfg.model, "messages": messages, "tools": tools, "temperature": 0.3},
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"LLM error {resp.status_code}: {resp.text[:200]}")
        return resp.json()

    def respond(self, text: str, history: list[dict], lang: str = "en") -> dict[str, Any]:
        profile = self.tb.state.profile
        red = Redactor([profile.get("name", ""), (self.tb.state.plan.ally or {}).get("name", "")])
        goal = (profile.get("savings_goal") or {}).get("name", "none")
        system = SYSTEM_PROMPT.format(language="Chinese (简体中文)" if lang == "zh" else "English",
                                      currency=profile.get("base_currency", "CNY"),
                                      patterns=", ".join(profile.get("patterns", [])) or "none", goal=goal)
        messages: list[dict] = [{"role": "system", "content": system}]
        for h in history[-8:]:
            messages.append({"role": h["role"], "content": red.redact(h["content"])})
        messages.append({"role": "user", "content": red.redact(text)})
        tools = self.tb.openai_tools()
        events: list[dict] = []
        data: dict[str, Any] = {}
        for _ in range(self.max_steps):
            reply = self._post(messages, tools)["choices"][0]["message"]
            calls = reply.get("tool_calls") or []
            if not calls:
                return {"text": reply.get("content") or "", "events": events, "data": data}
            messages.append({"role": "assistant", "content": reply.get("content") or "", "tool_calls": calls})
            for call in calls:
                name = call["function"]["name"]
                try:
                    args = json.loads(call["function"].get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                res = self.tb.call(name, red.restore(args), actor="agent")
                events.append(res.to_dict())
                if name == "pause_check" and res.status == "ok":
                    data["pause"] = res.result
                payload = {"status": res.status, "message": res.message, "result": res.result}
                if res.status == "needs_confirmation":
                    payload["message"] = "Prepared. The user must confirm it in the app before anything happens."
                messages.append({"role": "tool", "tool_call_id": call["id"],
                                 "content": red.redact(json.dumps(payload, ensure_ascii=False, default=str))[:6000]})
        return {"text": "I got a bit lost in the details there. Could you ask again in one sentence?", "events": events, "data": data}
