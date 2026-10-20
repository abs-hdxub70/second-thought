"""End-to-end check of the browser extension in a real Chromium.

Starts the local API (with the demo persona Mei, 23:50) and the fictional demo shop, loads the
unpacked extension, pairs it through the options page and clicks "立即购买" on the demo shop.
Checks both warning steps, parking, buying anyway and offline mode, and saves screenshots
to evidence/extension/.

  python scripts/extension_e2e.py            # screenshots + checks
  python scripts/extension_e2e.py --video    # also records a video per page
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from playwright.sync_api import expect, sync_playwright  # noqa: E402

from second_thought.demo import load_demo  # noqa: E402
from second_thought.extension_api import serve  # noqa: E402
from second_thought.state import AppState  # noqa: E402

CODE = "MEI2-DEMO"
API_PORT, SHOP_PORT = 8765, 8770
EXT = ROOT / "extension"
OUT_ROOT = ROOT / "evidence" / "extension"
OUT = OUT_ROOT  # language subfolder, set in main()
SHOP = f"http://127.0.0.1:{SHOP_PORT}/demo-shop/"


def fresh_state(root: Path) -> None:
    if root.exists():
        shutil.rmtree(root)
    state = AppState.for_region("CN", root)
    load_demo(state)
    state.save()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", action="store_true")
    ap.add_argument("--slow", type=int, default=0, help="extra pause in ms between steps (for recordings)")
    ap.add_argument("--lang", choices=["zh", "en"], default="zh", help="overlay language for the screenshots")
    args = ap.parse_args()
    global OUT
    OUT = OUT_ROOT / args.lang
    OUT.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="st-ext-"))
    state_root = work / "state"
    fresh_state(state_root)
    os.environ["ST_API_QUIET"] = "1"
    api = serve("CN", API_PORT, state_root, CODE)
    threading.Thread(target=api.serve_forever, daemon=True).start()
    shop = subprocess.Popen([sys.executable, str(ROOT / "scripts" / "serve_demo_shop.py"), "--port", str(SHOP_PORT)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.8)
    results: list[str] = []
    pause = (lambda ms=600: time.sleep((ms + args.slow) / 1000))

    try:
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                str(work / "profile"), channel="chromium", headless=True,
                viewport={"width": 1280, "height": 800}, device_scale_factor=2 if not args.video else 1,
                locale="zh-CN", record_video_dir=str(work / "video") if args.video else None,
                record_video_size={"width": 1280, "height": 800} if args.video else None,
                args=[f"--disable-extensions-except={EXT}", f"--load-extension={EXT}"])
            sw = ctx.service_workers[0] if ctx.service_workers else ctx.wait_for_event("serviceworker", timeout=15000)
            ext_id = sw.url.split("/")[2]
            results.append(f"extension loaded: {ext_id}")

            # 1. pair through the options page
            opt = ctx.new_page()
            opt.goto(f"chrome-extension://{ext_id}/options.html")
            opt.fill("#api", f"http://127.0.0.1:{API_PORT}")
            opt.fill("#code", CODE)
            opt.select_option("#lang", args.lang)
            opt.click("#test")
            expect(opt.locator("#result")).to_contain_text("Connected", timeout=10000)
            results.append("pairing: " + opt.locator("#result").inner_text().strip())
            opt.screenshot(path=str(OUT / "01_options_paired.png"), full_page=True)
            opt.close()

            # 2. the demo shop: click buy, step 1
            page = ctx.new_page()
            page.goto(SHOP)
            pause(1200)
            page.screenshot(path=str(OUT / "02_shop.png"))
            page.click("#buy")
            card = page.locator("second-thought-pause .card")
            expect(card.locator(".ring")).to_be_visible(timeout=10000)
            pause(1500)
            assert not page.locator("#done").is_visible(), "checkout went through without asking"
            score = card.locator(".ring span").inner_text()
            reasons = card.locator("li").all_inner_texts()
            results.append(f"step 1: score {score}, reasons {len(reasons)}: " + " | ".join(r.replace(chr(10), ' ') for r in reasons))
            assert int(score) >= 70 and len(reasons) >= 4
            expect(card.locator(".rule")).to_be_visible()
            card.screenshot(path=str(OUT / "03_step1_why_wait.png"))
            page.screenshot(path=str(OUT / "03_step1_page.png"))

            # 3. step 2, the second warning with money left and the countdown
            card.locator('[data-a="next"]').click()
            expect(card.locator(".row").first).to_be_visible()
            buy = card.locator('[data-a="buy"]')
            expect(buy).to_be_disabled()
            pause(1500)
            rows = card.locator(".row").all_inner_texts()
            results.append("step 2: " + " | ".join(r.replace("\n", " ") for r in rows))
            card.screenshot(path=str(OUT / "04_step2_money_left.png"))
            page.screenshot(path=str(OUT / "04_step2_page.png"))

            # 4. keep it parked
            card.locator('[data-a="park"]').click()
            expect(card.locator(".done")).to_be_visible(timeout=10000)
            pause(1200)
            results.append("park: " + card.locator(".done").inner_text())
            card.screenshot(path=str(OUT / "05_parked.png"))
            card.locator('[data-a="close2"]').click()
            assert not page.locator("#done").is_visible()

            # 5. buy anyway after the countdown: the click goes through and is logged
            page.reload()
            pause(800)
            page.click("#buy")
            expect(card.locator(".ring")).to_be_visible(timeout=10000)
            card.locator('[data-a="next"]').click()
            expect(buy).to_be_enabled(timeout=30000)
            pause(600)
            buy.click()
            expect(page.locator("#done")).to_be_visible(timeout=10000)
            results.append("buy anyway: checkout went through after the countdown")
            pause(800)
            page.screenshot(path=str(OUT / "06_bought.png"))

            # 6. popup with the numbers
            pop = ctx.new_page()
            pop.set_viewport_size({"width": 340, "height": 330})
            pop.goto(f"chrome-extension://{ext_id}/popup.html")
            expect(pop.locator("#status .ok")).to_be_visible(timeout=10000)
            pause(500)
            pop.screenshot(path=str(OUT / "07_popup.png"))
            results.append("popup: " + pop.locator("body").inner_text().replace("\n", " | "))
            pop.close()

            # 7. offline: stop the API, the extension still asks with its own numbers
            api.shutdown()
            api.server_close()
            page.goto(SHOP + "?offline")
            pause(800)
            page.evaluate("() => 0")
            ctx.service_workers[0].evaluate("chrome.storage.local.set({passed: {}})")
            page.click("#buy")
            expect(card.locator(".off")).to_be_visible(timeout=15000)
            pause(1000)
            results.append("offline: " + card.locator(".off").inner_text())
            card.screenshot(path=str(OUT / "08_offline.png"))
            page.close()
            ctx.close()

        # audit log of the demo state: checks and decisions arrived through the gate
        state = AppState.for_region("CN", state_root)
        via = [e for e in state.audit.entries() if "via browser extension" in (e.get("note") or "")]
        ok, _ = state.audit.verify()
        results.append(f"audit: {len(via)} entries via the extension, chain intact: {ok}")
        assert ok and len(via) >= 3
        if args.video:
            vids = sorted((work / "video").glob("*.webm"), key=lambda f: f.stat().st_size)
            for i, v in enumerate(vids):
                shutil.copy(v, OUT / f"recording_{i}.webm")
    finally:
        shop.terminate()
        try:
            api.shutdown()
        except Exception:
            pass
    (OUT / "e2e_results.txt").write_text("\n".join(results) + "\n", encoding="utf-8")
    print("\n".join(results))
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
