"""Plaid Sandbox connector (real API calls, sandbox environment only).

Flow: /sandbox/public_token/create -> /item/public_token/exchange -> /transactions/sync
Needs PLAID_CLIENT_ID and PLAID_SECRET (free sandbox keys from dashboard.plaid.com).
Without keys, or with offline=True, it reads a fixture file in the same JSON shape so the demo
still runs. Every real request is logged (endpoint, status, request_id; never secrets or tokens).
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from ..engine.categories import enrich
from ..models import EXPENSE, INCOME, NEUTRAL, Transaction

SANDBOX_URL = "https://sandbox.plaid.com"
DEFAULT_INSTITUTION = "ins_109508"  # Plaid's "First Platypus Bank" sandbox institution


class PlaidSandboxConnector:
    name = "plaid"
    region = "US/CA/UK/EU"
    status = "real-sandbox"

    def __init__(self, request_log: Path | None = None, offline: bool | None = None,
                 client_id: str | None = None, secret: str | None = None):
        self.client_id = client_id or os.getenv("PLAID_CLIENT_ID", "")
        self.secret = secret or os.getenv("PLAID_SECRET", "")
        self.offline = offline if offline is not None else not (self.client_id and self.secret)
        self.request_log = request_log
        self.balances: list[dict[str, Any]] = []

    # ---- real API -------------------------------------------------------
    def _post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        import requests

        body = {"client_id": self.client_id, "secret": self.secret, **payload}
        started = time.time()
        resp = requests.post(f"{SANDBOX_URL}{endpoint}", json=body, timeout=30)
        data = resp.json() if resp.content else {}
        self._log({
            "ts": datetime.now().isoformat(timespec="seconds"),
            "endpoint": endpoint,
            "http_status": resp.status_code,
            "request_id": data.get("request_id"),
            "ms": int((time.time() - started) * 1000),
            "error_code": data.get("error_code"),
        })
        if resp.status_code != 200:
            raise RuntimeError(f"Plaid {endpoint} failed: {data.get('error_code')} {data.get('error_message')}")
        return data

    def _log(self, entry: dict[str, Any]) -> None:
        if self.request_log is None:
            return
        self.request_log.parent.mkdir(parents=True, exist_ok=True)
        with self.request_log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def fetch_live(self, institution_id: str = DEFAULT_INSTITUTION, max_polls: int = 10) -> dict[str, Any]:
        public = self._post("/sandbox/public_token/create", {
            "institution_id": institution_id,
            "initial_products": ["transactions"],
        })["public_token"]
        access = self._post("/item/public_token/exchange", {"public_token": public})["access_token"]
        added: list[dict[str, Any]] = []
        accounts: list[dict[str, Any]] = []
        cursor = None
        for _ in range(max_polls):  # sandbox data can take a few seconds to be ready
            payload: dict[str, Any] = {"access_token": access, "count": 250}
            if cursor:
                payload["cursor"] = cursor
            page = self._post("/transactions/sync", payload)
            added.extend(page.get("added", []))
            accounts = page.get("accounts", accounts)
            cursor = page.get("next_cursor")
            if page.get("has_more"):
                continue
            if added:
                break
            time.sleep(2)
        return {"accounts": accounts, "added": added}

    # ---- mapping --------------------------------------------------------
    @staticmethod
    def to_transactions(payload: dict[str, Any]) -> list[Transaction]:
        out: list[Transaction] = []
        for t in payload.get("added", []):
            if t.get("pending"):
                continue
            amount = float(t.get("amount", 0))  # Plaid: positive = money out
            when = t.get("datetime") or t.get("authorized_datetime") or (t.get("date", "") + "T12:00:00")
            ts = datetime.fromisoformat(when.replace("Z", "+00:00")).replace(tzinfo=None)
            pfc = (t.get("personal_finance_category") or {}).get("primary", "")
            if pfc in ("TRANSFER_IN", "TRANSFER_OUT", "LOAN_PAYMENTS"):
                direction = NEUTRAL
            else:
                direction = EXPENSE if amount > 0 else INCOME
            txn = Transaction(
                id="plaid-" + t["transaction_id"],
                source="plaid",
                timestamp=ts,
                amount=abs(amount),
                currency=t.get("iso_currency_code") or t.get("unofficial_currency_code") or "USD",
                direction=direction,
                merchant=t.get("merchant_name") or t.get("name", ""),
                description=t.get("name", ""),
                raw_category=pfc,
                category="other",
                payment_method=t.get("payment_channel", ""),
                status="posted",
                raw={"account_id": t.get("account_id")},
            )
            out.append(enrich(txn))
        return out

    def load(self, source: str | Path | bytes | None = None) -> list[Transaction]:
        if self.offline:
            if source is None:
                raise ValueError("Offline mode needs a fixture file (data/plaid_sandbox_transactions.json).")
            data = source if isinstance(source, bytes) else Path(source).read_bytes()
            payload = json.loads(data.decode("utf-8"))
            self._log({"ts": datetime.now().isoformat(timespec="seconds"), "endpoint": "fixture",
                       "http_status": None, "note": "offline fixture, no network call"})
        else:
            payload = self.fetch_live()
        self.balances = payload.get("accounts", [])
        return self.to_transactions(payload)
