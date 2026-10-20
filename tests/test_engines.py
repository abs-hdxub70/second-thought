from datetime import datetime

from conftest import txn

from second_thought.engine import returns, risk_score, safe_to_spend, subscriptions
from second_thought.engine.ledger import convert
from second_thought.engine.risk_score import PurchaseIntent


def test_risk_red_at_night_in_a_burst(make_ledger):
    led = make_ledger([txn("2026-10-20T23:05", 129, tags=["livestream"]), txn("2026-10-20T23:31", 89, tags=["livestream"])])
    intent = PurchaseIntent(899, datetime(2026, 10, 20, 23, 50), "clothing", tags=["livestream"])
    r = risk_score.score(intent, led, trigger_categories=["clothing"])
    codes = {x.code for x in r.reasons}
    assert {"night", "burst", "livestream", "trigger"} <= codes
    assert r.score == 70 and r.band == "red"


def test_risk_green_for_daytime_groceries(make_ledger):
    led = make_ledger([txn("2026-10-18T16:00", 150, merchant="盒马", category="groceries")])
    r = risk_score.score(PurchaseIntent(160, datetime(2026, 10, 20, 16, 0), "groceries"), led)
    assert r.band == "green" and r.score < 40


def test_risk_festival_and_mood(make_ledger):
    led = make_ledger([])
    mood = [{"ts": "2026-11-11T19:00", "mood": 2, "stress": 4}]
    r = risk_score.score(PurchaseIntent(300, datetime(2026, 11, 11, 20, 0), "beauty", is_instalment=True), led, mood_log=mood)
    assert {x.code for x in r.reasons} == {"festival", "mood", "instalment"}


def test_risk_score_is_capped():
    assert risk_score.RED == 70 and risk_score.AMBER == 40


def test_safe_to_spend_formula(make_ledger):
    profile = {
        "base_currency": "CNY", "payday": 10,
        "accounts": [{"name": "main", "currency": "CNY", "balance": 10000}],
        "fixed_bills": [{"name": "rent", "amount": 3000, "due_day": 1}],
        "credit_due": [{"name": "card", "amount": 1000, "due_day": 5}],
        "savings_goal": {"monthly": 1500}, "buffer_share": 0.10,
    }
    res = safe_to_spend.compute(profile, make_ledger([]), datetime(2026, 10, 20, 12, 0), subscriptions=[])
    # d = 21, F = 4000, G = 1050, R = 300 -> (10000 - 4000 - 1050 - 300) / 21
    assert res["d_days_to_payday"] == 21
    assert res["safe_to_spend_today"] == round((10000 - 4000 - 1050 - 300) / 21, 2)


def test_subscription_detection_flags(make_ledger):
    txns = []
    for m in ("2026-08-15", "2026-09-15", "2026-10-15"):
        txns.append(txn(f"{m}T08:00", 25 if m.startswith("2026-08") else 30, merchant="腾讯视频", category="subscriptions"))
    for m in ("2026-08-03", "2026-09-03", "2026-10-03"):
        txns.append(txn(f"{m}T08:00", 25, merchant="爱奇艺", category="subscriptions"))
    txns.append(txn("2026-08-01T22:00", 0.0, merchant="喜马拉雅", category="subscriptions"))
    for m in ("2026-08-08", "2026-09-08", "2026-10-08"):
        txns.append(txn(f"{m}T22:00", 25, merchant="喜马拉雅", category="subscriptions"))
    txns.append(txn("2026-10-01T10:00", 4200, merchant="房租", category="housing"))
    txns.append(txn("2026-09-01T10:00", 4200, merchant="房租", category="housing"))
    subs = {s.merchant: s for s in subscriptions.detect(make_ledger(txns), datetime(2026, 10, 20))}
    assert set(subs) == {"腾讯视频", "爱奇艺", "喜马拉雅"}  # rent is essential, not a subscription
    assert "price_increase" in subs["腾讯视频"].flags
    assert "duplicate_service" in subs["爱奇艺"].flags
    assert "trial_converted" in subs["喜马拉雅"].flags


def test_bill_check_on_demo(toolbox):
    b = toolbox.svc.get_bill_check()
    names = {s["merchant"] for s in b["subscriptions"]}
    assert {"Spotify", "Adobe", "喜马拉雅", "腾讯视频"} <= names
    assert len(b["fees"]) == 2 and b["fees_total"] > 0
    assert b["open_instalments"] and b["open_instalments"][0]["count"] == 3


def test_return_windows_china_seven_days(toolbox):
    items = toolbox.svc.get_return_windows()
    ear = next(i for i in items if "耳机" in i["description"])
    assert ear["window_days"] == 7 and ear["days_left"] == 6
    assert items[0]["id"] == ear["id"]  # impulse buys first
    draft = returns.draft_return_request(ear, "CN")
    assert "七日无理由退货" in draft["zh"] and "Art. 25" in draft["en"]


def test_fx_conversion():
    assert convert(10, "EUR", "CNY") == 78.0
    assert convert(78, "CNY", "EUR") == 10.0
