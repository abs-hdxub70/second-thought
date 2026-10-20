import json

from second_thought.connectors import AlipayCSVConnector, PlaidSandboxConnector, UnionPayMockConnector, WeChatBillConnector
from second_thought.demo import DATA_DIR
from second_thought.models import EXPENSE, INCOME, NEUTRAL

ALIPAY_SAMPLE = (
    "------------------------------------------------------------------------------------\n"
    "导出信息：\n姓名：测试\n共3笔记录\n"
    "------------------------支付宝（中国）网络技术有限公司  电子客户回单------------------------\n"
    "交易时间,交易分类,交易对方,对方账号,商品说明,收/支,金额,收/付款方式,交易状态,交易订单号,商家订单号,备注,\n"
    "2026-10-20 23:31:44,美容美发,淘宝直播,/,【直播间】补水面膜,支出,89.00,花呗,交易成功,2026102011112222333344445555\t,\t,,\n"
    "2026-10-19 12:00:00,投资理财,余额宝,/,转入余额宝,不计收支,500.00,招商银行储蓄卡,交易成功,2026101911112222333344445556\t,\t,,\n"
    "2026-10-18 10:00:00,日用百货,淘宝,/,已取消的订单,支出,59.00,花呗,交易关闭,2026101811112222333344445557\t,\t,,\n"
)


def test_alipay_gbk_with_info_block():
    txns = AlipayCSVConnector().load(ALIPAY_SAMPLE.encode("gbk"))
    assert len(txns) == 2  # closed order skipped
    mask = txns[0]
    assert mask.amount == 89.0 and mask.direction == EXPENSE and mask.currency == "CNY"
    assert mask.category == "beauty"
    assert "livestream" in mask.tags and "online" in mask.tags
    assert mask.is_instalment  # paid with Huabei
    assert mask.id == "ali-2026102011112222333344445555"  # trailing tab stripped
    assert txns[1].direction == NEUTRAL


def test_alipay_demo_file_parses():
    txns = AlipayCSVConnector().load(DATA_DIR / "alipay_bill_mei.csv")
    assert len(txns) > 100
    assert any(t.category == "fees" for t in txns)
    ipad = next(t for t in txns if "iPad" in t.description)
    assert ipad.is_instalment and ipad.instalment_count == 3


def test_wechat_csv_and_xlsx_match():
    csv_txns = WeChatBillConnector().load(DATA_DIR / "wechat_bill_mei.csv")
    xlsx_txns = WeChatBillConnector().load(DATA_DIR / "wechat_bill_mei.xlsx")
    assert len(csv_txns) == len(xlsx_txns) > 50
    assert {t.id for t in csv_txns} == {t.id for t in xlsx_txns}
    ear = next(t for t in csv_txns if "耳机" in t.description)
    assert ear.amount == 459.0 and ear.category == "electronics" and "livestream" in ear.tags
    assert any(t.direction == INCOME for t in csv_txns)  # red packet received


def test_unionpay_mock_uses_mcc():
    txns = UnionPayMockConnector().load(DATA_DIR / "unionpay_statement_mei.json")
    rent = next(t for t in txns if "房租" in t.merchant)
    assert rent.category == "housing"
    repay = next(t for t in txns if t.merchant == "花呗还款")
    assert repay.direction == NEUTRAL and repay.category == "credit_repayment"
    salary = next(t for t in txns if "工资" in t.merchant)
    assert salary.direction == INCOME


def test_plaid_mapping_sign_and_categories(tmp_path):
    log = tmp_path / "plaid.jsonl"
    conn = PlaidSandboxConnector(request_log=log, offline=True)
    txns = conn.load(DATA_DIR / "plaid_sandbox_transactions.json")
    spotify = [t for t in txns if t.merchant == "Spotify"]
    assert spotify and all(t.direction == EXPENSE and t.currency == "EUR" for t in spotify)
    assert any(t.category == "fees" for t in txns)
    interest = next(t for t in txns if t.merchant == "Interest")
    assert interest.direction == INCOME
    entries = [json.loads(line) for line in log.read_text().splitlines()]
    assert entries[0]["endpoint"] == "fixture"
    assert "secret" not in log.read_text()
