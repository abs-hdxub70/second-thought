"""Local API used by the browser extension: guards, checkout check, decisions."""

import json
import threading
import urllib.error
import urllib.request
from datetime import datetime

import pytest

from second_thought.extension_api import CheckoutService, guess_category, new_pairing_code, serve

CODE = "TEST-CODE"
COAT = {"amount": 799, "currency": "CNY", "title": "Oversized wool coat 羊毛大衣", "site": "night-market.example",
        "signals": "直播间 限时秒杀"}


@pytest.fixture()
def service(demo_state, tmp_path):
    demo_state.save()
    return CheckoutService("CN", tmp_path)


@pytest.fixture()
def server(demo_state, tmp_path):
    demo_state.save()
    srv = serve("CN", 0, tmp_path, CODE)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv
    srv.shutdown()
    srv.server_close()


def request(srv, path, body=None, code=CODE, headers=None):
    port = srv.server_address[1]
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, method="POST" if data else "GET")
    req.add_header("Content-Type", "application/json")
    if code:
        req.add_header("Authorization", f"Bearer {code}")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read()), dict(resp.headers)
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read()), dict(err.headers)


def test_ping_is_open_but_data_needs_the_pairing_code(server):
    assert request(server, "/v1/ping", code=None)[0] == 200
    assert request(server, "/v1/summary", code=None)[0] == 401
    assert request(server, "/v1/summary", code="WRONG-CODE")[0] == 401
    status, body, headers = request(server, "/v1/summary")
    assert status == 200 and body["ready"] and body["currency"] == "CNY"
    assert "Access-Control-Allow-Origin" not in headers


def test_web_pages_and_foreign_hosts_are_refused(server):
    assert request(server, "/v1/summary", headers={"Origin": "https://shop.example"})[0] == 403
    assert request(server, "/v1/summary", headers={"Host": "evil.example:80"})[0] == 403
    status, _, _ = request(server, "/v1/summary", headers={"Origin": "chrome-extension://abcdefghijklmnop"})
    assert status == 200


def test_too_many_wrong_codes_lock_the_api(server):
    for _ in range(10):
        request(server, "/v1/summary", code="NOPE-NOPE")
    assert request(server, "/v1/summary")[0] == 429


def test_night_checkout_is_red_held_and_shows_money_left(service):
    check = service.check(COAT)
    codes = {r["code"] for r in check["risk"]["reasons"]}
    assert check["risk"]["band"] == "red" and {"night", "livestream", "trigger"} <= codes
    assert check["category"] == "clothing" and check["signals"]["flash_sale"]
    m = check["money"]
    assert m["safe_today_after"] == pytest.approx(m["safe_today_before"] - 799)
    assert m["left_until_payday_after"] == pytest.approx(m["left_until_payday_before"] - 799)
    assert m["goal_name"] == "Japan trip" and m["goal_delay_days"] == 16
    assert check["hold"] and "night_hold" in check["hold"]["rule"] and check["hold"]["auto_saved"] == 80
    assert check["countdown_seconds"] == 20


def test_repeat_click_does_not_hold_twice(service):
    first = service.check(COAT)
    again = service.check(COAT)
    assert again["repeat"] and again["check_id"] == first["check_id"]
    state = service._toolbox().state
    assert sum(1 for i in state.parking if i["status"] == "parked") == 1


def test_buying_anyway_is_the_users_call_and_logged(service):
    check = service.check(COAT)
    out = service.decide({"check_id": check["check_id"], "decision": "bought"})
    assert out["status"] == "ok"
    state = service._toolbox().state
    item = next(i for i in state.parking if i["id"] == check["hold"]["item_id"])
    assert item["status"] == "bought" and item["note"] == "override at checkout"
    last = state.audit.entries()[-1]
    assert last["tool"] == "resolve_parked" and last["actor"] == "user" and "via browser extension" in last["note"]
    assert state.audit.verify()[0]


def test_daytime_park_creates_24h_item_and_saves(demo_state, tmp_path):
    demo_state.set_clock(datetime(2026, 10, 21, 14, 0))
    demo_state.save()
    svc = CheckoutService("CN", tmp_path)
    check = svc.check({"amount": 150, "title": "Wireless headphones", "site": "shop.example"})
    assert check["hold"] is None and check["category"] == "electronics"
    out = svc.decide({"check_id": check["check_id"], "decision": "park"})
    assert out["hold_until"] == "2026-10-22T14:00" and out["saved"] == 15
    assert svc.decide({"check_id": check["check_id"], "decision": "skip"})["repeat"]


def test_bad_input_is_refused(service):
    with pytest.raises(ValueError):
        service.check({"amount": "lots"})
    with pytest.raises(ValueError):
        service.check({"amount": -5})
    with pytest.raises(LookupError):
        service.decide({"check_id": "nope", "decision": "skip"})


def test_helpers():
    code = new_pairing_code()
    assert len(code) == 9 and code[4] == "-" and not set(code) & set("01IO")
    assert guess_category("Lippenstift Set") == "beauty"
    assert guess_category("Winter Mantel") == "clothing"
