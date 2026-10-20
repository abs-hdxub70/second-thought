"""Record the demo video from the running app (headless Chromium), with an English caption band.

Prerequisites: the app is running (streamlit run app/streamlit_app.py), demo data exists,
`pip install playwright && playwright install chromium`, and ffmpeg is on the PATH.

Usage: python scripts/record_demo_video.py [--url http://localhost:8501] [--out demo_video.mp4]
"""

from __future__ import annotations

import argparse
import io
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import Page, sync_playwright

W, H, SCALE = 1600, 800, 1.2          # CSS viewport and device scale -> 1920 x 960 app frame
BAND = 120                            # caption band height in output pixels -> 1920 x 1080
TEAL, INK, WHITE = (47, 111, 104), (17, 24, 39), (255, 255, 255)
HOLD_FACTOR = 1.7                     # stretch every static hold so captions can be read


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
    for index in range(10):  # pick the Simplified Chinese face inside the collection
        try:
            f = ImageFont.truetype(path, size, index=index)
        except OSError:
            break
        if "SC" in " ".join(f.getname()):
            return f
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)


F_STEP, F_TEXT = _font(26, bold=True), _font(28)
CURSOR_JS = """
(() => {
  if (window.__cur) return;
  const c = document.createElement('div');
  c.id = '__cur';
  Object.assign(c.style, {position:'fixed', zIndex: 2147483647, width:'22px', height:'22px', borderRadius:'50%',
    background:'rgba(47,111,104,0.30)', border:'2px solid #2f6f68', pointerEvents:'none',
    transform:'translate(-50%,-50%)', left:'800px', top:'420px', transition:'none'});
  document.body.appendChild(c);
  window.__cur = c;
})();
"""


class Recorder:
    def __init__(self, page: Page, workdir: Path):
        self.page = page
        self.dir = workdir
        self.frames: list[tuple[Path, float]] = []
        self.step = ""
        self.text = ""
        self.pos = (W / 2, H / 2)

    # ---- frames ----------------------------------------------------------------
    def compose(self, raw: bytes) -> Image.Image:
        app = Image.open(io.BytesIO(raw)).convert("RGB")
        frame = Image.new("RGB", (app.width, app.height + BAND), INK)
        frame.paste(app, (0, 0))
        draw = ImageDraw.Draw(frame)
        x, y = 60, app.height + 22
        if self.step:
            draw.text((x, y), self.step, font=F_STEP, fill=(110, 196, 184))
            y += 38
        for line in self._wrap(self.text, frame.width - 120)[:2]:
            draw.text((x, y), line, font=F_TEXT, fill=WHITE)
            y += 38
        return frame

    def _wrap(self, text: str, width: int) -> list[str]:
        words, lines, cur = text.split(" "), [], ""
        for w in words:
            trial = (cur + " " + w).strip()
            if F_TEXT.getlength(trial) <= width:
                cur = trial
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines

    def snap(self, seconds: float) -> None:
        if seconds >= 1.0:
            seconds *= HOLD_FACTOR  # reading time for captions; animation frames stay fast
        self.page.evaluate(CURSOR_JS)
        path = self.dir / f"f{len(self.frames):05d}.png"
        self.compose(self.page.screenshot()).save(path)
        self.frames.append((path, seconds))

    def card(self, html: str, seconds: float) -> None:
        tmp = self.page.context.new_page()
        tmp.set_viewport_size({"width": W, "height": int((H * SCALE + BAND) / SCALE)})
        tmp.set_content(html)
        tmp.wait_for_timeout(300)
        path = self.dir / f"f{len(self.frames):05d}.png"
        Image.open(io.BytesIO(tmp.screenshot())).convert("RGB").resize((int(W * SCALE), int(H * SCALE) + BAND)).save(path)
        tmp.close()
        self.frames.append((path, seconds))

    def say(self, step: str, text: str, hold: float = 0.0) -> None:
        self.step, self.text = step, text
        if hold:
            self.snap(hold)

    # ---- actions -----------------------------------------------------------------
    def idle(self, extra: float = 1.2) -> None:
        self.page.wait_for_timeout(int(extra * 1000))
        for _ in range(60):
            if self.page.locator('[data-testid="stStatusWidget"]').count() == 0:
                break
            self.page.wait_for_timeout(250)
        self.page.wait_for_timeout(300)

    def move_to(self, locator) -> tuple[float, float]:
        locator.scroll_into_view_if_needed()
        box = locator.bounding_box()
        tx, ty = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        sx, sy = self.pos
        for i in range(1, 9):
            k = i / 8
            k = k * k * (3 - 2 * k)
            self.page.evaluate(f"window.__cur && (window.__cur.style.left='{sx + (tx - sx) * k}px', window.__cur.style.top='{sy + (ty - sy) * k}px')")
            self.snap(0.04)
        self.pos = (tx, ty)
        return tx, ty

    def click(self, locator, hold: float = 0.3, wait: float = 1.2) -> None:
        self.move_to(locator)
        self.page.evaluate("window.__cur && (window.__cur.style.width='34px', window.__cur.style.height='34px')")
        self.snap(0.12)
        self.page.evaluate("window.__cur && (window.__cur.style.width='22px', window.__cur.style.height='22px')")
        locator.click()
        self.idle(wait)
        self.snap(hold)

    def type(self, locator, text: str, step: int = 2) -> None:
        self.move_to(locator)
        locator.click()
        for i in range(step, len(text) + step, step):
            locator.fill(text[:i])
            self.snap(0.045)

    def chat(self, text: str, hold: float) -> None:
        box = self.page.locator('[data-testid="stChatInputTextArea"]')
        self.type(box, text)
        box.press("Enter")
        self.idle(1.5)
        self.snap(hold)

    def scroll(self, dy: int, steps: int = 8) -> None:
        self.page.mouse.move(W * 0.6, H * 0.5)
        for _ in range(steps):
            self.page.mouse.wheel(0, dy / steps)
            self.page.wait_for_timeout(60)
            self.snap(0.05)
        self.page.wait_for_timeout(300)

    def tab(self, name: str, hold: float = 0.5) -> None:
        self.click(self.page.get_by_role("tab", name=name), hold=hold, wait=1.5)

    def button(self, name: str, hold: float = 0.4, wait: float = 1.5, exact: bool = True) -> None:
        self.click(self.page.get_by_role("button", name=name, exact=exact).first, hold=hold, wait=wait)

    # ---- output ------------------------------------------------------------------
    def render(self, out: Path) -> float:
        lst = self.dir / "frames.txt"
        with lst.open("w") as fh:
            for path, dur in self.frames:
                fh.write(f"file '{path.name}'\nduration {dur:.3f}\n")
            fh.write(f"file '{self.frames[-1][0].name}'\n")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                        "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-crf", "18", "-preset", "medium",
                        "-movflags", "+faststart", str(out)], check=True, cwd=self.dir)
        return sum(d for _, d in self.frames)


CARD = """<html><body style="margin:0;height:100vh;display:flex;align-items:center;justify-content:center;
background:#0f172a;font-family:'Noto Sans CJK SC','Noto Sans',sans-serif;color:#fff">
<div style="max-width:1150px;padding:0 60px">{body}</div></body></html>"""


def title_card(rec: Recorder) -> None:
    rec.card(CARD.format(body="""
      <div style="font-size:22px;letter-spacing:.14em;color:#6ec4b8;text-transform:uppercase">FinTechathon 2026 · Topic A</div>
      <div style="font-size:72px;font-weight:700;margin:18px 0 6px">Second Thought <span style="color:#6ec4b8">再想想</span></div>
      <div style="font-size:30px;color:#cbd5e1">A personal finance assistant that puts a pause between the urge and the payment.</div>
      <div style="font-size:22px;color:#94a3b8;margin-top:40px">Built for impulsive spending patterns: ADHD, bipolar disorder, emotional spending, impulse buys in live streams and with buy-now-pay-later.</div>
    """), 5.0)
    rec.card(CARD.format(body="""
      <div style="font-size:22px;letter-spacing:.14em;color:#6ec4b8;text-transform:uppercase">Demo persona (synthetic data)</div>
      <div style="font-size:48px;font-weight:700;margin:18px 0 18px">Mei, 26, UX designer in Shenzhen</div>
      <div style="font-size:28px;color:#cbd5e1;line-height:1.6">Found out last year she has ADHD. Pays with Alipay, WeChat Pay and Huabei,
      still has a European bank account from her exchange year.<br>It is 23:50 and she is watching a live stream.</div>
    """), 6.0)


def closing_card(rec: Recorder) -> None:
    rec.card(CARD.format(body="""
      <div style="font-size:58px;font-weight:700;line-height:1.25">Second Thought doesn't say no.<br>It says: <span style="color:#6ec4b8">think it over. 再想想。</span></div>
      <div style="font-size:24px;color:#94a3b8;margin-top:42px;line-height:1.7">Real Alipay &amp; WeChat Pay bill parsers · Plaid Sandbox · offline agent or DeepSeek / Qwen<br>
      Permission tiers · 24-hour cooldown · hash-chained audit log · 37 automated tests</div>
    """), 6.0)


def run(url: str, out: Path) -> float:
    work = Path(tempfile.mkdtemp())
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": W, "height": H}, device_scale_factor=SCALE, locale="en-US",
                                  timezone_id="Asia/Shanghai")
        page = ctx.new_page()
        rec = Recorder(page, work)
        page.goto(url)
        rec.idle(5)
        # start from a clean region, off camera
        page.get_by_role("button", name="Reset this region").click()
        rec.idle(3)

        title_card(rec)

        rec.say("1 · Set up", "No diagnosis needed. People pick patterns that sound like them and give separate consent for their financial data.", 4.5)
        rec.scroll(260)
        rec.snap(2.5)
        rec.say("1 · Set up", "For the demo we load Mei's synthetic Alipay and WeChat Pay exports, a UnionPay statement and a Plaid sandbox account.", 1.5)
        rec.button("Load demo persona (Mei)", hold=1.0, wait=4)

        rec.say("2 · Smart budgeting", "One number: safe to spend today. Rent, the Huabei bill, subscriptions, her savings goal and a buffer are already set aside.", 3.5)
        rec.click(page.get_by_text("How this is calculated"), hold=4.0)
        rec.click(page.get_by_text("How this is calculated"), hold=0.3)

        rec.tab("Transactions", hold=0.3)
        rec.say("2 · Connectors", "One ledger from Alipay, WeChat Pay, UnionPay and the Plaid sandbox, converted to CNY, each line with its impulse score.", 5.0)
        rec.tab("Today", hold=0.3)

        rec.say("3 · Bill analysis", "Mei asks about her bills. The agent finds 8 subscriptions, overlapping services, a free trial that turned paid and 2 fees.", 0.5)
        rec.chat("Check my subscriptions and fees", hold=5.0)
        rec.say("3 · Bill analysis", "The agent only prepares cancellation drafts. Nothing happens until Mei taps Confirm.", 0.3)
        rec.scroll(380)
        rec.snap(2.5)
        rec.click(page.get_by_role("button", name="Confirm").first, hold=1.0, wait=2)
        for _ in range(4):
            dismiss = page.get_by_role("button", name="Dismiss")
            if dismiss.count() == 0:
                break
            rec.click(dismiss.first, hold=0.2, wait=1.2)
        rec.tab("Bills", hold=0.3)
        rec.say("3 · Bill analysis", "The bill check: flags like 'old foreign account', 'free trial turned paid' and 'price went up', plus the avoidable 'ADHD tax'.", 4.5)
        rec.scroll(700, steps=10)
        rec.snap(1.5)
        drafts = page.get_by_text("saves", exact=False)
        if drafts.count():
            rec.click(drafts.last, hold=0.3)
            rec.say("3 · Bill analysis", "A ready-to-copy cancellation message plus where to switch off auto-renewal. Never sent automatically.", 4.0)

        rec.tab("Today", hold=0.3)
        rec.say("4 · The Pause", "23:50. Mei has already bought twice in the last hour. Now a ¥899 jacket in a live stream.", 0.4)
        rec.type(page.get_by_label("What is it?"), "Cashmere jacket, live stream", step=3)
        amount = page.get_by_label("Amount")
        rec.move_to(amount)
        amount.fill("899")
        rec.snap(0.4)
        rec.click(page.get_by_text("Live stream", exact=True), hold=0.3, wait=0.6)
        rec.click(page.get_by_role("button", name="Check it"), hold=0.5, wait=2.5)
        rec.scroll(420)
        rec.say("4 · The Pause", "Impulse score 70 out of 100, with every reason visible. About 10 hours of her work, or almost 5 days of budget.", 4.5)
        rec.say("4 · The Pause", "Her calm-state plan holds it for 12 hours, and 10% (¥90) moves to her Japan trip pot. Essentials are never held.", 4.5)

        rec.say("5 · Asymmetric friction", "She tries to switch the rule off. Removing a protection needs her confirmation and then waits 24 hours.", 0.4)
        rec.chat("remove my night limit", hold=4.5)
        rec.click(page.get_by_role("button", name="Confirm").first, hold=2.5, wait=2)

        rec.tab("Parking & returns", hold=0.3)
        rec.say("6 · Regret rescue", "The jacket waits in the parking lot. Last night's ¥459 earphones still have 6 days on China's 7-day no-reason return window.", 4.5)
        rec.click(page.get_by_role("button", name="Draft return request").first, hold=0.3, wait=2)
        rec.scroll(500)
        exp = page.get_by_text("deadline", exact=False)
        if exp.count():
            rec.click(exp.last, hold=0.3)
        rec.say("6 · Regret rescue", "One tap drafts the return request, citing the Consumer Rights Protection Law, Art. 25.", 4.0)

        rec.tab("Money mirror", hold=0.3)
        rec.say("7 · Spending insights", "The weekly money mirror: most impulse spending happened after 23:00, and stress days cost ¥260 versus ¥68.", 4.5)
        rec.say("7 · Spending insights", "One concrete suggestion instead of a lecture: lower the night-hold threshold to catch the small late buys.", 2.0)
        rec.scroll(520)
        rec.snap(2.5)

        rec.tab("Plan & safety", hold=0.3)
        rec.say("8 · Security", "The queued change, the permission tiers, and an audit log of every action. The model can never move money on its own.", 4.5)
        rec.click(page.get_by_role("button", name="Verify hash chain"), hold=0.3, wait=1.5)
        rec.say("8 · Security", "Each log entry stores the hash of the previous one, so any edit breaks the chain. This log is our execution evidence.", 4.0)

        rec.tab("Today", hold=0.3)
        rec.say("9 · 中文", "Fully bilingual. Switching to Chinese, and asking the same kind of question in Chinese.", 0.4)
        rec.click(page.get_by_text("中文", exact=True).first, hold=1.5, wait=2.5)
        rec.chat("要不要买 599 元的包？", hold=5.0)
        rec.tab("账单", hold=0.3)
        rec.scroll(700, steps=10)
        zh_drafts = page.get_by_text("每月省", exact=False)
        if zh_drafts.count():
            rec.click(zh_drafts.last, hold=0.3)
        rec.say("9 · 中文", "Drafts, labels and replies follow the language. The return and cancellation texts are ready to paste into Taobao or WeChat.", 4.5)

        rec.say("", "", 0)
        closing_card(rec)
        browser.close()
    total = rec.render(out)
    shutil.rmtree(work, ignore_errors=True)
    return total


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8501")
    ap.add_argument("--out", default="demo_video.mp4")
    args = ap.parse_args()
    seconds = run(args.url, Path(args.out).resolve())
    print(f"wrote {args.out} ({seconds / 60:.1f} min)")


if __name__ == "__main__":
    main()
