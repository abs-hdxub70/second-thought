"""Connector interface. Every payment source turns into a list of Transaction objects."""

from __future__ import annotations

import csv
import hashlib
import io
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable, Protocol

from ..models import Transaction


class Connector(Protocol):
    name: str
    region: str
    status: str  # real-parser | real-sandbox | mock | roadmap

    def load(self, source: str | Path | bytes) -> list[Transaction]: ...


REGISTRY: dict[str, dict[str, str]] = {
    "alipay": {"region": "CN", "status": "real-parser", "how": "User-exported bill CSV (账单下载), GBK"},
    "wechat": {"region": "CN", "status": "real-parser", "how": "User-exported bill (CSV or XLSX)"},
    "unionpay": {"region": "CN/global", "status": "mock", "how": "Same interface, synthetic card statement"},
    "plaid": {"region": "US/CA/UK/EU", "status": "real-sandbox", "how": "Plaid Sandbox API (/transactions/sync)"},
    "ecny": {"region": "CN", "status": "roadmap", "how": "Capped sub-wallet as hard limit"},
    "camt053": {"region": "EU", "status": "roadmap", "how": "ISO 20022 statement files"},
}


def read_text(source: str | Path | bytes, encodings: Iterable[str] = ("utf-8-sig", "gb18030")) -> str:
    """Decode bytes from a file path or raw bytes, trying UTF-8 (with BOM) then GB18030 (superset of GBK)."""
    data = source if isinstance(source, bytes) else Path(source).read_bytes()
    last_error: Exception | None = None
    for enc in encodings:
        try:
            return data.decode(enc)
        except UnicodeDecodeError as exc:
            last_error = exc
    raise ValueError(f"Could not decode file: {last_error}")


def find_table(text: str, must_have: tuple[str, ...]) -> list[list[str]]:
    """Return CSV rows starting at the header line that contains all `must_have` columns.

    Chinese bill exports put 10-25 lines of account info above the table, so we scan for the header.
    """
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if all(col in line for col in must_have):
            reader = csv.reader(io.StringIO("\n".join(lines[i:])))
            rows = [[c.strip().strip("\t").strip() for c in row] for row in reader]
            return [r for r in rows if any(r)]
    raise ValueError(f"Header with columns {must_have} not found. Is this the right export file?")


def parse_amount(value: str) -> float:
    cleaned = re.sub(r"[^\d.\-]", "", value.replace(",", ""))
    return abs(float(cleaned)) if cleaned not in ("", "-", ".") else 0.0


def parse_datetime(value: str) -> datetime:
    value = value.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return datetime.fromisoformat(value)


def stable_id(*parts: object) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:16]
