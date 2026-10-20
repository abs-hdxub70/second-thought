"""Record the browser-extension part of the demo video and splice it into the main demo video.

Uses the same frame size and caption band as record_demo_video.py. The extension runs unpacked
in Chromium, talks to the local API with Mei's demo data (23:50) and is shown on the fictional
demo shop. The result replaces the closing card of the main video with: extension segment +
updated closing card.

  python scripts/record_extension_video.py --main evidence/demo_video.mp4 --out demo_video_full.mp4
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
sys.path.insert(0, str(ROOT / "scripts"))

from playwright.sync_api import expect, sync_playwright  # noqa: E402

from record_demo_video import CARD, H, SCALE, W, Recorder  # noqa: E402
from second_thought.demo import load_demo  # noqa: E402
from second_thought.extension_api import serve  # noqa: E402
from second_thought.state import AppState  # noqa: E402

CODE = "MEI2-DEMO"
API_PORT, SHOP_PORT = 8765, 8770
EXT = ROOT / "extension"
CLOSING_SECONDS = 6.0  # length of the closing card at the end of the main video


class ExtRecorder(Recorder):
    def snap(self, seconds: float) -> None:
        # keep the cursor above the extension's overlay
        self.page.evaluate("() => { if (window.__cur) document.documentElement.appendChild(window.__cur); }")
        super().snap(seconds)


def closing(rec: Recorder, tests: int) -> None:
    rec.card(CARD.format(body=f"""
      <div style="font-size:58px;font-weight:700;line-height:1.25">Second Thought doesn't say no.<br>It says: <span style="color:#6ec4b8">think it over. 再想想。</span></div>
      <div style="font-size:24px;color:#94a3b8;margin-top:42px;line-height:1.7">Real Alipay &amp; WeChat Pay bill parsers · Plaid Sandbox · Checkout Pause browser extension<br>
      Offline agent or DeepSeek / Qwen · permission tiers · 24-hour cooldown · hash-chained audit log · {tests} automated tests</div>
    """), CLOSING_SECONDS)


def record(work: Path, tests: int) -> Path:
    state_root = work / "state"
    state = AppState.for_region("CN", state_root)
    load_demo(state)
    state.save()
    os.environ["ST_API_QUIET"] = "1"
    api = serve("CN", API_PORT, state_root, CODE)
    threading.Thread(target=api.serve_forever, daemon=True).start()
    shop = subprocess.Popen([sys.executable, str(ROOT / "scripts" / "serve_demo_shop.py"), "--port", str(SHOP_PORT)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.8)
    frames = work / "frames"
    frames.mkdir()
    try:
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                str(work / "profile"), channel="chromium", headless=True, viewport={"width": W, "height": H},
                device_scale_factor=SCALE, locale="en-US", timezone_id="Asia/Shanghai",
                args=[f"--disable-extensions-except={EXT}", f"--load-extension={EXT}"])
            sw = ctx.service_workers[0] if ctx.service_workers else ctx.wait_for_event("serviceworker", timeout=15000)
            ext_id = sw.url.split("/")[2]
            page = ctx.new_page()
            rec = ExtRecorder(page, frames)

            rec.card(CARD.format(body="""
              <div style="font-size:22px;letter-spacing:.14em;color:#6ec4b8;text-transform:uppercase">10 · Browser extension</div>
              <div style="font-size:60px;font-weight:700;margin:18px 0 14px">Checkout Pause</div>
              <div style="font-size:30px;color:#cbd5e1;line-height:1.5">The same pause, where the money actually leaves:<br>at the shop's checkout button.</div>
              <div style="font-size:22px;color:#94a3b8;margin-top:36px">Chrome and Edge, and Chromium-based browsers common in China. Taobao, Tmall, JD, Pinduoduo, Amazon, Zalando and more.</div>
            """), 4.5)

            # pairing, shown briefly: local only, with a code
            page.goto(f"chrome-extension://{ext_id}/options.html")
            page.wait_for_timeout(600)
            rec.say("10 · Browser extension", "Set up once: the extension only talks to the app on this computer, after pairing with a one-time code.", 0)
            rec.type(page.locator("#code"), CODE, step=1)
            page.fill("#api", f"http://127.0.0.1:{API_PORT}")
            page.select_option("#lang", "en")
            rec.click(page.locator("#test"), hold=0.3, wait=1.2)
            expect(page.locator("#result .ok")).to_be_visible(timeout=10000)
            rec.snap(2.6)

            page.goto(f"http://127.0.0.1:{SHOP_PORT}/demo-shop/")
            page.wait_for_timeout(1000)
            rec.pos = (W / 2, H / 2)
            rec.say("10 · Browser extension", "23:50 again. Mei is in a live stream: a ¥799 coat, a flash-sale countdown, Huabei instalments.", 3.5)
            card = page.locator("second-thought-pause .card")
            rec.move_to(page.locator("#buy"))
            rec.snap(0.3)
            page.click("#buy")
            expect(card.locator(".ring")).to_be_visible(timeout=10000)
            page.wait_for_timeout(500)
            assert not page.locator("#done").is_visible()
            rec.say("10 · Browser extension", "The shop's button is stopped. First question: do you really want to buy this now? Score 80, every reason from her own data.", 5.0)
            rec.move_to(card.locator(".rule"))
            rec.say("10 · Browser extension", "Her own night rule holds the coat until 11:50 tomorrow and has already moved ¥80 to her Japan trip pot.", 4.5)

            rec.click(card.locator('[data-a="next"]'), hold=0.3, wait=0.8)
            rec.say("10 · Second warning", "If she continues: what is left after this. Today's budget goes negative, the clothing cap drops to ¥359, Japan moves back 16 days.", 5.5)
            rec.move_to(card.locator('[data-a="buy"]'))
            rec.say("10 · Second warning", "'Override my rule' only unlocks after a countdown. It stays her decision, but it is never the easy default.", 3.5)
            rec.click(card.locator('[data-a="park"]'), hold=0.3, wait=1.2)
            rec.say("10 · Second warning", "She parks it. The coat waits in the app's parking lot, and every step is in the same hash-chained audit log.", 4.0)

            pop = ctx.new_page()
            pop.set_viewport_size({"width": W, "height": H})
            pop.goto(f"chrome-extension://{ext_id}/popup.html")
            expect(pop.locator("#status .ok")).to_be_visible(timeout=10000)
            pop.close()
            rec.say("", "", 0)
            closing(rec, tests)
            ctx.close()
        out = work / "extension_segment.mp4"
        seconds = rec.render(out)
        print(f"extension segment: {seconds:.1f} s")
        return out
    finally:
        shop.terminate()
        api.shutdown()
        api.server_close()


def splice(main: Path, segment: Path, out: Path) -> None:
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(main)],
                               capture_output=True, text=True, check=True).stdout.strip())
    cut = dur - CLOSING_SECONDS
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(main), "-i", str(segment), "-filter_complex",
                    f"[0:v]trim=0:{cut:.3f},setpts=PTS-STARTPTS,fps=30,format=yuv420p[a];"
                    f"[1:v]fps=30,format=yuv420p,setpts=PTS-STARTPTS[b];[a][b]concat=n=2:v=1:a=0[v]",
                    "-map", "[v]", "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-movflags", "+faststart", str(out)],
                   check=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--main", default=str(ROOT / "evidence" / "demo_video.mp4"))
    ap.add_argument("--out", default=str(ROOT / "demo_video_full.mp4"))
    ap.add_argument("--tests", type=int, default=0)
    args = ap.parse_args()
    work = Path(tempfile.mkdtemp(prefix="st-extvid-"))
    segment = record(work, args.tests)
    shutil.copy(segment, Path(args.out).with_name("extension_segment.mp4"))
    splice(Path(args.main), segment, Path(args.out))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
