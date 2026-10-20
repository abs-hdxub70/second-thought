"""Local API for the browser extension (Checkout Pause).

The extension asks this server, running on the user's own computer next to the app, whether a
checkout is a good idea and what money is left afterwards. It uses the same Toolbox and permission
gate as the app, so every check and decision lands in the same audit log.

Safety rules for this server
  * binds to 127.0.0.1 only, never to the network
  * every request except /v1/ping needs the pairing code (Authorization: Bearer <code>)
  * the Host header must be 127.0.0.1 or localhost (stops DNS rebinding)
  * an Origin header, if present, must be a browser-extension origin, so web pages cannot use it;
    no CORS headers are ever sent
  * repeated wrong codes lock the server for a minute
  * the extension sends only amount, currency, product title, shop domain and page signals
    (live stream, countdown, instalments); no browsing history, no page content is stored

Run:  python -m second_thought.extension_api --region CN --port 8765
"""

from __future__ import annotations

import argparse
import hmac
import json
import os
import re
import secrets
import threading
import time
import uuid
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .agent.tools import CATEGORY_ENUM, Toolbox
from .engine.categories import FLASH_SALE_KEYWORDS, INSTALMENT_KEYWORDS, KEYWORD_CATEGORIES, LIVESTREAM_KEYWORDS
from .engine.ledger import DEMO_FX_TO_CNY
from .state import DEFAULT_ROOT, AppState

VIA = "browser extension"
SYMBOLS = {"CNY": "¥", "EUR": "€", "USD": "$", "GBP": "£", "HKD": "HK$", "JPY": "¥"}
MAX_BODY = 16 * 1024
CACHE_MINUTES = 15
EXTENSION_ORIGINS = ("chrome-extension://", "moz-extension://", "safari-web-extension://")
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I


def new_pairing_code() -> str:
    raw = "".join(secrets.choice(ALPHABET) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


def load_or_create_code(root: Path) -> str:
    env = os.getenv("ST_EXTENSION_CODE")
    if env:
        return env.strip().upper()
    path = root / "extension_pairing_code"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    root.mkdir(parents=True, exist_ok=True)
    code = new_pairing_code()
    path.write_text(code, encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:  # pragma: no cover - e.g. some Windows file systems
        pass
    return code


def guess_category(text: str) -> str:
    low = text.lower()
    for category, words in KEYWORD_CATEGORIES:
        if category in ("credit_repayment", "fees", "transfer"):
            continue
        if any(w.lower() in low for w in words):
            return category
    return "other"


def _has(text: str, words: tuple[str, ...]) -> bool:
    low = text.lower()
    return any(w.lower() in low for w in words)


def _clean(value: Any, limit: int = 120) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


class CheckoutService:
    """Turns extension requests into Toolbox calls. One instance per server, state reloaded per request."""

    def __init__(self, region: str = "CN", root: Path | None = None):
        self.region = region.upper()
        self.root = Path(root or DEFAULT_ROOT)
        self.lock = threading.Lock()
        self.checks: dict[str, dict] = {}

    def _toolbox(self) -> Toolbox:
        return Toolbox(AppState.for_region(self.region, self.root))

    # ---- read ---------------------------------------------------------------------
    def summary(self) -> dict:
        with self.lock:
            tb = self._toolbox()
            st = tb.state
            if not st.profile:
                return {"ready": False, "message": "No profile yet. Open the app and set up or load the demo."}
            sts = tb.svc.get_safe_to_spend()
            base = sts["currency"]
            goal = st.profile.get("savings_goal") or {}
            parked = [i for i in st.parking if i["status"] == "parked"]
            return {
                "ready": True, "name": st.profile.get("name", ""), "region": self.region,
                "currency": base, "symbol": SYMBOLS.get(base, ""), "now": st.now().isoformat(timespec="minutes"),
                "safe_to_spend_today": sts["safe_to_spend_today"],
                "left_until_payday": round(sts["safe_to_spend_today"] * sts["d_days_to_payday"], 2),
                "days_to_payday": sts["d_days_to_payday"], "next_payday": sts["next_payday"],
                "goal": {"name": goal.get("name"), "target": goal.get("target"),
                         "saved": st.pots.get(goal.get("name") or "", 0.0)} if goal else None,
                "parked": len(parked),
                "night_window_active": st.plan.night_hold and st.plan.in_night_window(st.now()),
            }

    # ---- checkout check ----------------------------------------------------------------
    def check(self, body: dict) -> dict:
        try:
            amount = float(body.get("amount"))
        except (TypeError, ValueError):
            raise ValueError("amount must be a number") from None
        if not 0 < amount < 10_000_000:
            raise ValueError("amount out of range")
        title = _clean(body.get("title")) or "Online purchase"
        site = _clean(body.get("site"), 80).lower()
        merchant = _clean(body.get("merchant"), 80) or site
        signals = _clean(body.get("signals"), 400)
        text = f"{title} {merchant} {signals}"
        livestream = bool(body.get("livestream")) or _has(text, LIVESTREAM_KEYWORDS + ("live", "直播间"))
        flash = bool(body.get("flash_sale")) or _has(text, FLASH_SALE_KEYWORDS + ("blitzangebot", "deal endet"))
        instalment = bool(body.get("instalment")) or _has(text, INSTALMENT_KEYWORDS + ("ratenzahlung", "pay later"))
        category = body.get("category") if body.get("category") in CATEGORY_ENUM else guess_category(f"{title} {merchant}")

        with self.lock:
            tb = self._toolbox()
            st = tb.state
            if not st.profile:
                raise LookupError("No profile yet. Open the app and set up or load the demo.")
            base = st.profile.get("base_currency", "CNY")
            currency = (_clean(body.get("currency"), 3) or base).upper()
            if currency not in DEMO_FX_TO_CNY:
                currency = base
            key = f"{site}|{title}|{amount:.2f}|{currency}"
            cached = next((c for c in self.checks.values() if c["key"] == key
                           and st.now() - datetime.fromisoformat(c["at"]) <= timedelta(minutes=CACHE_MINUTES)
                           and c["decision"] is None), None)
            if cached:
                return {**cached["response"], "repeat": True}

            sts = tb.svc.get_safe_to_spend()
            res = tb.call("pause_check", {"amount": amount, "title": title, "merchant": merchant, "category": category,
                                          "currency": currency, "livestream": livestream, "flash_sale": flash,
                                          "instalment": instalment}, actor="user", via=VIA)
            if res.status != "ok":
                raise ValueError(res.message)
            r = res.result
            amount_base = r["intent"]["amount_base"]
            hold = self._hold_from(r.get("rules", []))
            response = {
                "check_id": uuid.uuid4().hex[:10],
                "title": title, "site": site, "amount": amount, "currency": currency,
                "base_currency": base, "symbol": SYMBOLS.get(base, ""), "amount_base": amount_base,
                "category": category, "essential": r["essential"],
                "signals": {"livestream": livestream, "flash_sale": flash, "instalment": instalment},
                "risk": r["risk"], "hours_of_work": r["hours_of_work"], "days_of_budget": r["days_of_budget"],
                "halt": r["halt"], "money": self._money(tb, sts, amount_base, category),
                "hold": hold, "now": st.now().isoformat(timespec="minutes"),
                "countdown_seconds": self._countdown(r["risk"]["band"], hold, r["essential"]),
            }
            self.checks[response["check_id"]] = {"key": key, "at": st.now().isoformat(timespec="minutes"),
                                                 "response": response, "decision": None, "args": {
                                                     "title": title, "amount": amount, "currency": currency,
                                                     "merchant": merchant, "category": category,
                                                     "risk_score": r["risk"]["score"]}}
            self._trim()
            return response

    @staticmethod
    def _hold_from(rules: list[dict]) -> dict | None:
        hold = next((o for o in rules if o.get("tool") == "auto_hold" and o.get("status") == "ok"), None)
        if not hold:
            return None
        saved = next((o["result"]["amount"] for o in rules if o.get("tool") == "auto_save" and o.get("status") == "ok"), 0)
        item = hold["result"]
        return {"item_id": item["id"], "until": item["hold_until"], "rule": hold.get("rule", item.get("reason", "")),
                "auto_saved": saved}

    @staticmethod
    def _countdown(band: str, hold: dict | None, essential: bool) -> int:
        if essential:
            return 0
        if hold:
            return 20
        return {"red": 10, "amber": 5}.get(band, 3)

    @staticmethod
    def _money(tb: Toolbox, sts: dict, amount_base: float, category: str) -> dict:
        st = tb.state
        days = sts["d_days_to_payday"]
        today = sts["safe_to_spend_today"]
        left = round(today * days, 2)
        after_left = round(left - amount_base, 2)
        goal = st.profile.get("savings_goal") or {}
        per_day = float(goal.get("monthly", 0)) / 30 if goal else 0
        cap = st.plan.category_caps.get(category)
        cap_info = None
        if cap is not None:
            start = st.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            spent = round(sum(t.amount_base for t in st.ledger.expenses(start, st.now()) if t.category == category), 2)
            cap_info = {"category": category, "cap": cap, "spent": spent, "left": round(cap - spent, 2),
                        "left_after": round(cap - spent - amount_base, 2)}
        return {
            "safe_today_before": today, "safe_today_after": round(today - amount_base, 2),
            "left_until_payday_before": left, "left_until_payday_after": after_left,
            "per_day_after": round(after_left / days, 2) if days else after_left,
            "days_to_payday": days, "next_payday": sts["next_payday"],
            "goal_name": goal.get("name"), "goal_delay_days": round(amount_base / per_day) if per_day else None,
            "category_cap": cap_info,
        }

    def _trim(self) -> None:
        if len(self.checks) > 200:
            for k in sorted(self.checks, key=lambda k: self.checks[k]["at"])[:-200]:
                self.checks.pop(k, None)

    # ---- decision ---------------------------------------------------------------------
    def decide(self, body: dict) -> dict:
        check_id = _clean(body.get("check_id"), 20)
        decision = body.get("decision")
        if decision not in ("park", "skip", "bought"):
            raise ValueError("decision must be park, skip or bought")
        with self.lock:
            entry = self.checks.get(check_id)
            if entry is None:
                raise LookupError("Unknown or expired check.")
            if entry["decision"] is not None:
                return {"status": "ok", "decision": entry["decision"], "repeat": True}
            tb = self._toolbox()
            hold = entry["response"]["hold"]
            args = entry["args"]
            note = _clean(body.get("note"), 200)
            saved = 0.0
            hold_until = None
            if hold:
                if decision == "park":
                    hold_until = hold["until"]
                    res = None
                else:
                    res = tb.call("resolve_parked", {"item_id": hold["item_id"],
                                                     "decision": "skipped" if decision == "skip" else "bought",
                                                     "note": note or ("override at checkout" if decision == "bought" else "")},
                                  actor="user", confirmed=True, via=VIA)
                saved = float(hold.get("auto_saved") or 0)
            elif decision == "park":
                res = tb.call("park_item", {**args, "hours": 24}, actor="user", confirmed=True, via=VIA)
                if res.status == "ok":
                    hold_until = res.result["hold_until"]
            else:
                decided = {k: v for k, v in args.items() if k != "merchant"}
                res = tb.call("record_decision", {**decided, "decision": "skipped" if decision == "skip" else "bought",
                                                  "note": note}, actor="user", confirmed=True, via=VIA)
            if res is not None:
                if res.status != "ok":
                    raise ValueError(res.message)
                saved += sum(o["result"]["amount"] for o in res.result.get("rules", []) or []
                             if o.get("tool") == "auto_save" and o.get("status") == "ok")
            entry["decision"] = decision
            goal = (tb.state.profile.get("savings_goal") or {}).get("name")
            return {"status": "ok", "decision": decision, "saved": round(saved, 2), "pot": goal,
                    "hold_until": hold_until, "symbol": entry["response"]["symbol"]}


class _Limiter:
    def __init__(self, max_failures: int = 10, window: float = 60.0):
        self.max, self.window, self.failures, self.locked_until = max_failures, window, [], 0.0

    def locked(self) -> bool:
        return time.monotonic() < self.locked_until

    def fail(self) -> None:
        now = time.monotonic()
        self.failures = [t for t in self.failures if now - t < self.window] + [now]
        if len(self.failures) >= self.max:
            self.locked_until = now + self.window
            self.failures = []


def make_handler(service: CheckoutService, code: str, port: int):
    limiter = _Limiter()
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    class Handler(BaseHTTPRequestHandler):
        server_version = "SecondThought/1"
        sys_version = ""

        def log_message(self, fmt: str, *args: Any) -> None:  # concise, never logs headers or bodies
            if os.getenv("ST_API_QUIET") != "1":
                print(f"[extension-api] {self.command} {self.path.split('?')[0]} -> {args[1] if len(args) > 1 else ''}")

        def _send(self, status: int, payload: dict) -> None:
            data = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def _guard(self, needs_code: bool = True) -> bool:
            if self.headers.get("Host", "") not in allowed_hosts:
                self._send(403, {"error": "bad host"})
                return False
            origin = self.headers.get("Origin")
            if origin and not origin.startswith(EXTENSION_ORIGINS):
                self._send(403, {"error": "web pages cannot use this API"})
                return False
            if not needs_code:
                return True
            if limiter.locked():
                self._send(429, {"error": "too many wrong pairing codes, wait a minute"})
                return False
            given = self.headers.get("Authorization", "").removeprefix("Bearer ").strip().upper()
            if not hmac.compare_digest(given.encode(), code.encode()):
                limiter.fail()
                self._send(401, {"error": "pairing code missing or wrong"})
                return False
            return True

        def _body(self) -> dict | None:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = -1
            if length < 0 or length > MAX_BODY:
                self._send(413, {"error": "body too large"})
                return None
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except (ValueError, UnicodeDecodeError):
                self._send(400, {"error": "invalid JSON"})
                return None
            if not isinstance(body, dict):
                self._send(400, {"error": "expected a JSON object"})
                return None
            return body

        def do_OPTIONS(self) -> None:  # no CORS for anyone
            self._send(403, {"error": "not available"})

        def do_GET(self) -> None:
            path = self.path.split("?")[0]
            if path == "/v1/ping":
                if self._guard(needs_code=False):
                    self._send(200, {"app": "second-thought", "api": 1})
                return
            if not self._guard():
                return
            if path == "/v1/summary":
                self._send(200, service.summary())
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self) -> None:
            path = self.path.split("?")[0]
            if not self._guard():
                return
            body = self._body()
            if body is None:
                return
            try:
                if path == "/v1/checkout":
                    self._send(200, service.check(body))
                elif path == "/v1/decision":
                    self._send(200, service.decide(body))
                else:
                    self._send(404, {"error": "not found"})
            except LookupError as exc:
                self._send(409, {"error": str(exc)})
            except ValueError as exc:
                self._send(400, {"error": str(exc)})

    return Handler


def serve(region: str = "CN", port: int = 8765, root: Path | None = None, code: str | None = None) -> ThreadingHTTPServer:
    root = Path(root or DEFAULT_ROOT)
    code = (code or load_or_create_code(root)).upper()
    service = CheckoutService(region, root)
    server = ThreadingHTTPServer(("127.0.0.1", port), BaseHTTPRequestHandler)
    server.RequestHandlerClass = make_handler(service, code, server.server_address[1])  # real port if 0 was asked
    server.daemon_threads = True
    server.service = service  # type: ignore[attr-defined]
    return server


def main() -> None:
    ap = argparse.ArgumentParser(description="Local API for the Second Thought browser extension")
    ap.add_argument("--region", default=os.getenv("ST_REGION", "CN"), choices=["CN", "EU", "cn", "eu"])
    ap.add_argument("--port", type=int, default=int(os.getenv("ST_EXTENSION_PORT", "8765")))
    args = ap.parse_args()
    root = DEFAULT_ROOT
    code = load_or_create_code(root)
    server = serve(args.region, args.port, root, code)
    print(f"Second Thought extension API on http://127.0.0.1:{args.port} (region {args.region.upper()})")
    print(f"Pairing code for the extension: {code}")
    print("Only this computer can reach it. Stop with Ctrl+C.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
