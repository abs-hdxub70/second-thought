"""Checkout detection of the browser extension (extension/detect.js), run in headless Chromium."""

from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")
DETECT = Path(__file__).resolve().parent.parent / "extension" / "detect.js"


@pytest.fixture(scope="module")
def page():
    try:
        with sync_api.sync_playwright() as p:
            browser = p.chromium.launch()
            pg = browser.new_page()
            yield pg
            browser.close()
    except Exception as exc:  # pragma: no cover - no browser in this environment
        pytest.skip(f"Chromium not available: {exc}")


def load(page, html: str) -> None:
    page.set_content(html)
    page.add_script_tag(path=str(DETECT))


def test_checkout_buttons_in_chinese_english_german(page):
    load(page, "<p>x</p>")
    yes = ["立即购买", "提交订单", "去结算(3)", "结算 ¥899.00", "Buy now", "Place your order", "Proceed to checkout",
           "Zur Kasse", "Jetzt kaufen", "Zahlungspflichtig bestellen"]
    no = ["加入购物车", "Add to cart", "Checkout our new arrivals", "Buy now and save 20% on your next order this season", ""]
    assert page.evaluate("l => l.map(STDetect.isCheckoutLabel)", yes) == [True] * len(yes)
    assert page.evaluate("l => l.map(STDetect.isCheckoutLabel)", no) == [False] * len(no)


def test_number_formats(page):
    load(page, "<p>x</p>")
    got = page.evaluate("l => l.map(STDetect.parseNumber)", ["1.299,00", "1,299.00", "12,5", "799", "1 299"])
    assert got == [1299, 1299, 12.5, 799, 1299]


def test_amount_from_total_line_and_from_price_near_button(page):
    load(page, "<div>商品 ¥899.00</div><div>优惠 -¥100</div><div><span>实付款</span> <b>¥1,058.00</b></div>"
               "<button id=b>提交订单</button>")
    assert page.evaluate("STDetect.findAmount(document, document.getElementById('b'))")["amount"] == 1058
    load(page, "<div><del class='price'>¥1,299</del><span class='price'>¥799.00</span><div><button id=b>立即购买</button></div></div>")
    got = page.evaluate("STDetect.findAmount(document, document.getElementById('b'))")
    assert got["amount"] == 799 and got["currency"] == "CNY"
    load(page, "<div>Gesamtsumme</div><div>89,99 €</div><button id=b>Zahlungspflichtig bestellen</button>")
    got = page.evaluate("STDetect.findAmount(document, document.getElementById('b'))")
    assert got["amount"] == 89.99 and got["currency"] == "EUR"


def test_click_on_inner_span_finds_the_button(page):
    load(page, "<a id=a href='#'><span id=s>立即购买</span></a><div id=big><p>立即购买</p><p>很多很多其他内容 a long description</p></div>")
    assert page.evaluate("STDetect.findCheckoutElement(document.getElementById('s')).id") == "a"


def test_signals_and_site_keys(page):
    load(page, "<p>直播中 LIVE · 限时秒杀 · 花呗分期</p>")
    sig = page.evaluate("STDetect.findSignals(document)")
    assert sig["livestream"] and sig["flash_sale"] and sig["instalment"]
    keys = page.evaluate("l => l.map(STDetect.siteKey)", ["buy.taobao.com", "www.amazon.co.uk", "zalando.de"])
    assert keys == ["taobao.com", "amazon.co.uk", "zalando.de"]
