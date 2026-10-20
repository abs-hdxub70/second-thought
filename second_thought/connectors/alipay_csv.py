"""Alipay (支付宝) bill export parser.

Users export their bill in the Alipay app (我的 > 账单 > ... > 开具交易流水证明 / 账单下载).
The CSV comes in GBK encoding with an info block above the table. Typical columns:
交易时间, 交易分类, 交易对方, 对方账号, 商品说明, 收/支, 金额, 收/付款方式, 交易状态, 交易订单号, 商家订单号, 备注
"""

from __future__ import annotations

from pathlib import Path

from ..engine.categories import enrich
from ..models import EXPENSE, INCOME, NEUTRAL, Transaction
from .base import find_table, parse_amount, parse_datetime, read_text, stable_id

REQUIRED = ("交易时间", "收/支", "金额")
SKIP_STATUS = ("交易关闭", "已关闭", "失败")


def _direction(value: str) -> str:
    if "支出" in value:
        return EXPENSE
    if "收入" in value:
        return INCOME
    return NEUTRAL  # 不计收支 / empty


class AlipayCSVConnector:
    name = "alipay"
    region = "CN"
    status = "real-parser"

    def load(self, source: str | Path | bytes) -> list[Transaction]:
        rows = find_table(read_text(source), REQUIRED)
        header, body = rows[0], rows[1:]
        idx = {name: i for i, name in enumerate(header)}

        def col(row: list[str], name: str) -> str:
            i = idx.get(name)
            return row[i] if i is not None and i < len(row) else ""

        out: list[Transaction] = []
        for row in body:
            when = col(row, "交易时间")
            if not when or not when[:4].isdigit():
                continue  # footer lines
            status = col(row, "交易状态")
            if any(s in status for s in SKIP_STATUS):
                continue
            order_no = col(row, "交易订单号")
            txn = Transaction(
                id="ali-" + (order_no or stable_id(when, col(row, "交易对方"), col(row, "金额"))),
                source=self.name,
                timestamp=parse_datetime(when),
                amount=parse_amount(col(row, "金额")),
                currency="CNY",
                direction=_direction(col(row, "收/支")),
                merchant=col(row, "交易对方"),
                description=col(row, "商品说明"),
                raw_category=col(row, "交易分类"),
                category="other",
                payment_method=col(row, "收/付款方式"),
                status=status,
                raw={k: col(row, k) for k in idx},
            )
            out.append(enrich(txn))
        return out
