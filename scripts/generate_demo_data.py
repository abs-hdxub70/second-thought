"""Generate synthetic demo data for the persona Mei (no real personal data).

Writes into data/:
  alipay_bill_mei.csv            Alipay export format, GBK, info block above the table
  wechat_bill_mei.csv / .xlsx    WeChat Pay export format, UTF-8 with BOM / Excel
  unionpay_statement_mei.json    mock card statement (salary, rent, utilities, repayments)
  plaid_sandbox_transactions.json  Plaid /transactions/sync shape (old EU account, EUR)
  profile_mei.json               profile, calm-state plan, mood check-ins

Usage: python scripts/generate_demo_data.py [--anchor 2026-10-20] [--out data]
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import random
from datetime import date, datetime, timedelta
from pathlib import Path

RNG = random.Random(2026)


def order_no(prefix: str, when: datetime) -> str:
    return prefix + when.strftime("%Y%m%d") + "".join(str(RNG.randint(0, 9)) for _ in range(28 - len(prefix) - 8))


def at(day: date, hh: int, mm: int, ss: int | None = None) -> datetime:
    return datetime(day.year, day.month, day.day, hh, mm, RNG.randint(0, 59) if ss is None else ss)


def monthly(start: date, end: date, dom: int) -> list[date]:
    out, d = [], date(start.year, start.month, 1)
    while d <= end:
        try:
            cand = d.replace(day=dom)
        except ValueError:
            cand = None
        if cand and start <= cand <= end:
            out.append(cand)
        d = date(d.year + (d.month // 12), d.month % 12 + 1, 1)
    return out


def build(anchor: date):
    start = anchor - timedelta(days=90)
    days = [start + timedelta(days=i) for i in range(91)]
    alipay, wechat, unionpay, plaid = [], [], [], []

    def ali(when, cat, party, desc, direction, amount, method, status="交易成功"):
        alipay.append([when, cat, party, "", desc, direction, amount, method, status, order_no("", when), "", ""])

    def wx(when, kind, party, desc, direction, amount, method, status="支付成功"):
        wechat.append([when, kind, party, desc, direction, amount, method, status, order_no("42000", when), "", "/"])

    # ---------------- recurring ----------------
    for d in monthly(start, anchor, 3):
        ali(at(d, 9, 12), "文化休闲", "爱奇艺", "爱奇艺VIP会员 连续包月", "支出", 25.00, "余额宝")
    for d in monthly(start, anchor, 12):
        ali(at(d, 8, 40), "文化休闲", "优酷", "优酷VIP会员 自动续费", "支出", 25.00, "余额宝")
    for d in monthly(start, anchor, 25):
        ali(at(d, 10, 5), "生活服务", "百度网盘", "百度网盘超级会员 连续包月", "支出", 30.00, "招商银行储蓄卡")
    trial = date(anchor.year, 8, 1)
    ali(at(trial, 22, 10), "文化休闲", "喜马拉雅", "喜马拉雅VIP 7天免费试用", "支出", 0.00, "余额宝")
    for d in [trial + timedelta(days=7)] + monthly(trial + timedelta(days=8), anchor, (trial + timedelta(days=7)).day):
        ali(at(d, 22, 10), "文化休闲", "喜马拉雅", "喜马拉雅VIP会员 自动续费", "支出", 25.00, "余额宝")
    for i, d in enumerate(monthly(start, anchor, 15)):
        wx(at(d, 7, 55), "商户消费", "腾讯视频", "腾讯视频VIP 连续包月", "支出", 25.00 if i == 0 else 30.00, "零钱")
    for d in monthly(start, anchor, 6):
        wx(at(d, 8, 20), "商户消费", "QQ音乐", "QQ音乐豪华绿钻 自动续费", "支出", 15.00, "零钱")

    for d in monthly(start, anchor, 10):
        unionpay.append({"ref": order_no("UP", at(d, 9, 0)), "time": at(d, 9, 0, 0).strftime("%Y-%m-%d %H:%M:%S"),
                         "amount": 15000.00, "type": "credit", "merchant": "工资 深圳某设计工作室", "memo": "代发工资"})
    for d in monthly(start, anchor, 1):
        unionpay.append({"ref": order_no("UP", at(d, 10, 0)), "time": at(d, 10, 2).strftime("%Y-%m-%d %H:%M:%S"),
                         "amount": 4200.00, "type": "debit", "merchant": "自如 房租", "memo": "月租", "mcc": "6513"})
    for d in monthly(start, anchor, 15):
        unionpay.append({"ref": order_no("UP", at(d, 11, 0)), "time": at(d, 11, 30).strftime("%Y-%m-%d %H:%M:%S"),
                         "amount": round(RNG.uniform(150, 210), 2), "type": "debit", "merchant": "深圳供电局", "memo": "电费", "mcc": "4900"})
    for d in monthly(start, anchor, 18):
        unionpay.append({"ref": order_no("UP", at(d, 9, 0)), "time": at(d, 9, 15).strftime("%Y-%m-%d %H:%M:%S"),
                         "amount": 98.00, "type": "debit", "merchant": "中国移动", "memo": "话费", "mcc": "4814"})
    # Huabei repayments (neutral transfers); September paid two days late -> overdue interest
    for d, amount in ((date(anchor.year, 8, 9), 1620.00), (date(anchor.year, 9, 11), 2140.00), (date(anchor.year, 10, 9), 1980.00)):
        if start <= d <= anchor:
            unionpay.append({"ref": order_no("UP", at(d, 20, 0)), "time": at(d, 20, 15).strftime("%Y-%m-%d %H:%M:%S"),
                             "amount": amount, "type": "transfer", "merchant": "花呗还款", "memo": "花呗账单还款"})
    ali(at(date(anchor.year, 9, 11), 20, 16), "信用借还", "花呗", "花呗逾期利息", "支出", 23.60, "招商银行储蓄卡")

    # Plaid (old EU account): Spotify + Adobe still running, one overdraft fee
    def pl(tid, d, hh, amount, name, merchant, pfc, channel="online"):
        plaid.append({"transaction_id": tid, "account_id": "acc_eu_checking", "amount": amount, "iso_currency_code": "EUR",
                      "date": d.isoformat(), "datetime": f"{d.isoformat()}T{hh:02d}:00:00Z", "name": name,
                      "merchant_name": merchant, "personal_finance_category": {"primary": pfc, "detailed": pfc + "_OTHER"},
                      "payment_channel": channel, "pending": False})
    for d in monthly(start, anchor, 2):
        pl(f"fxt_spotify_{d:%m%d}", d, 6, 10.99, "SPOTIFY P1A2B3", "Spotify", "ENTERTAINMENT")
    for d in monthly(start, anchor, 21):
        pl(f"fxt_adobe_{d:%m%d}", d, 7, 26.99, "ADOBE *CREATIVE CLOUD", "Adobe", "GENERAL_SERVICES")
    pl("fxt_overdraft_0902", date(anchor.year, 9, 2), 8, 15.00, "OVERDRAFT FEE", "Overdraft fee", "BANK_FEES", "other")
    pl("fxt_interest_0930", date(anchor.year, 9, 30), 8, -0.02, "INTEREST PAYMENT", "Interest", "INCOME", "other")

    # ---------------- daily life (random filler) ----------------
    clothing = ["棉麻衬衫", "高腰阔腿裤", "针织开衫", "小白鞋", "宽松卫衣", "牛仔外套"]
    beauty = ["保湿精华 30ml", "防晒霜", "眼影盘", "面膜 10片装", "气垫粉底"]
    household = ["收纳盒 3件套", "香薰蜡烛", "床品四件套", "桌面绿植"]
    for d in days:
        wd = d.weekday()
        if wd < 5 and RNG.random() < 0.7:
            when, price = at(d, 8, RNG.randint(30, 59)), RNG.choice([9.9, 13.9, 15.9])
            if RNG.random() < 0.5:
                ali(when, "餐饮美食", "瑞幸咖啡", "生椰拿铁", "支出", price, "余额宝")
            else:
                wx(when, "商户消费", "瑞幸咖啡", "生椰拿铁", "支出", price, "零钱")
        if RNG.random() < 0.55:
            ali(at(d, RNG.choice([12, 19]), RNG.randint(0, 50)), "餐饮美食", "美团", "美团外卖订单", "支出",
                round(RNG.uniform(26, 62), 2), "余额宝")
        if wd == 5:
            ali(at(d, 16, RNG.randint(0, 59)), "超市便利", "盒马鲜生", "盒马生鲜", "支出", round(RNG.uniform(120, 260), 2), "招商银行储蓄卡")
        if RNG.random() < 0.25:
            ali(at(d, RNG.choice([9, 18, 22]), RNG.randint(0, 59)), "交通出行", "滴滴出行", "快车行程", "支出",
                round(RNG.uniform(18, 46), 2), "余额宝")
        if RNG.random() < 0.3:
            wx(at(d, RNG.choice([13, 21]), RNG.randint(0, 59)), "商户消费", "美宜佳便利店", "便利店消费", "支出",
               round(RNG.uniform(8, 35), 2), "零钱")
        if RNG.random() < 0.12:
            wx(at(d, 15, RNG.randint(0, 59)), "商户消费", "拼多多", RNG.choice(household), "支出", round(RNG.uniform(19, 59), 2), "零钱")
        if RNG.random() < 0.06:
            wx(at(d, 20, RNG.randint(0, 59)), "微信红包", "朋友", "/", "支出", RNG.choice([66.00, 88.00]), "零钱", "已领取")
    # weekly-ish online shopping before the last week, often late
    shop_days = [start + timedelta(days=i) for i in range(3, 80, 6)]
    for i, d in enumerate(shop_days):
        late = RNG.random() < 0.6
        when = at(d + timedelta(days=1), 0, RNG.randint(5, 50)) if late else at(d, 22, RNG.randint(10, 55))
        kind = i % 3
        if kind == 0:
            item, cat, amount = RNG.choice(clothing), "服饰装扮", round(RNG.uniform(129, 399), 2)
        elif kind == 1:
            item, cat, amount = RNG.choice(beauty), "美容美发", round(RNG.uniform(79, 299), 2)
        else:
            item, cat, amount = RNG.choice(household), "日用百货", round(RNG.uniform(39, 189), 2)
        live = RNG.random() < 0.5
        ali(when, cat, "淘宝直播" if live else "淘宝", ("【直播间】" if live else "") + item, "支出", amount,
            "花呗" if RNG.random() < 0.5 else "余额宝")

    # ---------------- story events ----------------
    y = anchor.year
    ali(datetime(y, 8, 14, 23, 20, 11), "服饰装扮", "淘宝直播", "【直播间】羊毛双面呢大衣", "支出", 1299.00, "花呗")
    ali(datetime(y, 8, 20, 21, 5, 40), "数码电器", "天猫 Apple Store", "iPad mini 花呗分期", "支出", 3999.00, "花呗分期(3期)")
    ali(datetime(y, 9, 27, 23, 41, 2), "服饰装扮", "淘宝直播", "【直播间】针织马甲", "支出", 189.00, "花呗")
    wx(datetime(y, 10, 5, 22, 48, 9), "商户消费", "抖音商城", "直播间 宽松牛仔外套", "支出", 329.00, "零钱")
    wx(datetime(y, 10, 12, 0, 40, 33), "商户消费", "抖音商城", "直播间 小香风外套", "支出", 199.00, "零钱")
    ali(datetime(y, 10, 14, 23, 12, 50), "餐饮美食", "美团", "美团外卖 夜宵", "支出", 58.00, "余额宝")
    wx(datetime(y, 10, 16, 23, 48, 10), "商户消费", "抖音商城", "直播间 零食大礼包", "支出", 159.00, "零钱")
    wx(datetime(y, 10, 19, 23, 38, 27), "商户消费", "抖音商城", "无线降噪耳机（直播间专享）", "支出", 459.00, "零钱")
    wx(datetime(y, 10, 20, 23, 5, 18), "商户消费", "抖音商城", "直播间 口红礼盒", "支出", 129.00, "零钱")
    ali(datetime(y, 10, 20, 23, 31, 44), "美容美发", "淘宝直播", "【直播间】补水面膜 20片", "支出", 89.00, "花呗")
    # noise the parser must handle: closed order and a neutral transfer
    ali(datetime(y, 10, 2, 14, 0, 0), "日用百货", "淘宝", "已取消的订单", "支出", 59.00, "花呗", "交易关闭")
    ali(datetime(y, 9, 15, 12, 0, 0), "投资理财", "余额宝", "转入余额宝", "不计收支", 500.00, "招商银行储蓄卡")
    wx(datetime(y, 9, 20, 18, 0, 0), "微信红包", "妈妈", "/", "收入", 200.00, "/", "已存入零钱")
    unionpay.append({"ref": order_no("UP", datetime(y, 9, 8, 15, 0)), "time": f"{y}-09-08 15:02:11", "amount": 68.00,
                     "type": "debit", "merchant": "大参林药房", "memo": "药品", "mcc": "5912"})

    # remove anything random that would fall into the demo hour (22:52-23:52 on the anchor day)
    lo, hi = datetime(y, anchor.month, anchor.day, 22, 52), datetime(y, anchor.month, anchor.day, 23, 52)
    keep = {(datetime(y, 10, 20, 23, 5, 18)), datetime(y, 10, 20, 23, 31, 44)}
    alipay = [r for r in alipay if not (lo <= r[0] <= hi) or r[0] in keep]
    wechat = [r for r in wechat if not (lo <= r[0] <= hi) or r[0] in keep]
    return start, alipay, wechat, unionpay, plaid


def summary(rows, dir_idx, amt_idx):
    s = {"支出": [0, 0.0], "收入": [0, 0.0], "other": [0, 0.0]}
    for r in rows:
        k = r[dir_idx] if r[dir_idx] in s else "other"
        s[k][0] += 1
        s[k][1] += float(r[amt_idx])
    return s


def write_alipay(path: Path, start: date, anchor: date, rows):
    rows = sorted(rows, key=lambda r: r[0], reverse=True)  # Alipay lists newest first
    s = summary(rows, 5, 6)
    buf = io.StringIO()
    buf.write("------------------------------------------------------------------------------------\n")
    buf.write("导出信息：\n姓名：林梅（演示数据）\n支付宝账户：demo****@example.com\n")
    buf.write(f"起始时间：[{start} 00:00:00]    终止时间：[{anchor} 23:59:59]\n导出交易类型：[全部]\n")
    buf.write(f"导出时间：[{anchor} 23:45:12]\n共{len(rows)}笔记录\n")
    buf.write(f"收入：{s['收入'][0]}笔 {s['收入'][1]:.2f}元\n支出：{s['支出'][0]}笔 {s['支出'][1]:.2f}元\n")
    buf.write(f"不计收支：{s['other'][0]}笔 {s['other'][1]:.2f}元\n\n特别提示：\n")
    buf.write("1.本回单内容可表明支付宝受理了相关交易申请，不代表交易已经成功。\n2.本文件为演示用合成数据，不含任何真实个人信息。\n")
    buf.write("------------------------支付宝（中国）网络技术有限公司  电子客户回单------------------------\n")
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["交易时间", "交易分类", "交易对方", "对方账号", "商品说明", "收/支", "金额", "收/付款方式", "交易状态", "交易订单号", "商家订单号", "备注", ""])
    for r in rows:
        w.writerow([r[0].strftime("%Y-%m-%d %H:%M:%S"), r[1], r[2], r[3] or "/", r[4], r[5], f"{r[6]:.2f}", r[7], r[8],
                    r[9] + "\t", r[10] + "\t", r[11], ""])
    path.write_bytes(buf.getvalue().encode("gbk"))


def wechat_table(rows):
    rows = sorted(rows, key=lambda r: r[0], reverse=True)
    header = ["交易时间", "交易类型", "交易对方", "商品", "收/支", "金额(元)", "支付方式", "当前状态", "交易单号", "商户单号", "备注"]
    body = [[r[0].strftime("%Y-%m-%d %H:%M:%S"), r[1], r[2], r[3], r[4], f"¥{r[5]:.2f}", r[6], r[7], r[8] + "\t", r[9] or "/", r[10]]
            for r in rows]
    return rows, header, body


def write_wechat(path_csv: Path, path_xlsx: Path, start: date, anchor: date, rows):
    rows, header, body = wechat_table(rows)
    s = summary(rows, 4, 5)
    pad = "," * 10
    lines = ["微信支付账单明细" + pad, "微信昵称：[小梅（演示）]" + pad, f"起始时间：[{start} 00:00:00] 终止时间：[{anchor} 23:59:59]" + pad,
             "导出类型：[全部]" + pad, f"导出时间：[{anchor} 23:45:30]" + pad, pad, f"共{len(rows)}笔记录" + pad,
             f"收入：{s['收入'][0]}笔 {s['收入'][1]:.2f}元" + pad, f"支出：{s['支出'][0]}笔 {s['支出'][1]:.2f}元" + pad,
             f"中性交易：{s['other'][0]}笔 {s['other'][1]:.2f}元" + pad, "注：" + pad, "1. 本文件为演示用合成数据。" + pad, pad,
             "----------------------微信支付账单明细列表--------------------" + pad]
    buf = io.StringIO()
    buf.write("\n".join(lines) + "\n")
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(body)
    path_csv.write_bytes(buf.getvalue().encode("utf-8-sig"))

    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    for line in lines:
        ws.append([line.rstrip(",")])
    ws.append(header)
    for row in body:
        ws.append([c.strip("\t") for c in row])
    wb.save(path_xlsx)


def profile(anchor: date) -> dict:
    y = anchor.year
    mood = [
        {"ts": f"{y}-10-14T21:10", "mood": 2, "stress": 4},
        {"ts": f"{y}-10-15T20:00", "mood": 4, "stress": 2},
        {"ts": f"{y}-10-16T22:30", "mood": 2, "stress": 5},
        {"ts": f"{y}-10-17T19:00", "mood": 4, "stress": 2},
        {"ts": f"{y}-10-18T12:00", "mood": 3, "stress": 2},
        {"ts": f"{y}-10-19T21:00", "mood": 2, "stress": 4},
        {"ts": f"{y}-10-20T19:40", "mood": 2, "stress": 4},
    ]
    return {
        "profile": {
            "name": "Mei Lin",
            "persona_note": "Synthetic demo persona. No real person or data.",
            "region": "CN",
            "base_currency": "CNY",
            "language": "en",
            "patterns": ["late_night_impulse", "forgets_subscriptions", "livestream_shopping"],
            "trigger_categories": ["clothing", "beauty"],
            "payday": 10,
            "monthly_income": 15000,
            "work_hours_per_month": 174,
            "accounts": [
                {"name": "CMB debit (UnionPay)", "currency": "CNY", "balance": 11500.0, "source": "unionpay"},
                {"name": "Old EU account (Plaid sandbox)", "currency": "EUR", "balance": 42.0, "source": "plaid"},
            ],
            "fixed_bills": [
                {"name": "Rent 房租", "amount": 4200, "due_day": 1},
                {"name": "Electricity 电费", "amount": 180, "due_day": 15},
                {"name": "Phone 话费", "amount": 98, "due_day": 18},
            ],
            "credit_due": [{"name": "Huabei 花呗", "amount": 1850, "due_day": 9}],
            "savings_goal": {"name": "Japan trip", "target": 8000, "monthly": 1500},
            "buffer_share": 0.10,
            "consents": {"financial_data": True, "ally_alerts": True, "llm_processing": False},
        },
        "plan": {
            "night_hold": True, "night_start": "23:00", "night_end": "06:00", "night_hold_threshold": 300,
            "hold_hours": 12, "category_caps": {"clothing": 2000}, "blocked_categories": ["gambling"],
            "auto_save_share": 0.10, "daily_sweep_cap": 100,
            "ally": {"name": "Lin (sister)", "channel": "SMS", "alerts": ["red_flag"]}, "ally_auto_alert": False,
        },
        "mood_log": mood,
        "pots": {"Japan trip": 1200.0},
        "demo_clock": f"{anchor}T23:50",
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--anchor", default="2026-10-20")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "data"))
    args = ap.parse_args()
    anchor = date.fromisoformat(args.anchor)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    start, alipay, wechat, unionpay, plaid = build(anchor)
    write_alipay(out / "alipay_bill_mei.csv", start, anchor, alipay)
    write_wechat(out / "wechat_bill_mei.csv", out / "wechat_bill_mei.xlsx", start, anchor, wechat)
    unionpay.sort(key=lambda x: x["time"])
    (out / "unionpay_statement_mei.json").write_text(json.dumps(
        {"card_label": "招商银行 银联借记卡 (mock)", "currency": "CNY", "lines": unionpay}, ensure_ascii=False, indent=2), encoding="utf-8")
    plaid.sort(key=lambda x: x["date"])
    (out / "plaid_sandbox_transactions.json").write_text(json.dumps({
        "note": "Synthetic fixture in Plaid /transactions/sync response shape (amount > 0 = money out).",
        "accounts": [{"account_id": "acc_eu_checking", "name": "Old EU checking", "balances": {"current": 42.0, "iso_currency_code": "EUR"}}],
        "added": plaid, "has_more": False}, indent=2), encoding="utf-8")
    (out / "profile_mei.json").write_text(json.dumps(profile(anchor), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"alipay rows {len(alipay)}, wechat rows {len(wechat)}, unionpay {len(unionpay)}, plaid {len(plaid)} -> {out}")


if __name__ == "__main__":
    main()
