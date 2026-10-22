"""Record real footage of Parts Intelligence (the local Noordveld app) at phone size, frame-accurate via CDP screencast.

Needs the site on http://localhost:5180 and the API running.
Run: python -I scripts/record_platform.py  ->  assets/platform/%04d.jpg (30 fps) + assets/platform/marks.json
"""
import asyncio
import base64
import json
import os
import shutil
import subprocess
import tempfile
import time

from playwright.async_api import async_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets", "platform")
URL = "http://localhost:5180/parts-intelligence"
QUESTION = "Find AS-411-C"


async def main():
    frames, marks = [], {}
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await browser.new_context(viewport={"width": 390, "height": 693}, device_scale_factor=3, is_mobile=True, has_touch=True)
        page = await ctx.new_page()
        await page.goto(URL, wait_until="networkidle")
        box = page.get_by_placeholder("e.g. Find NVM-1010-AT")
        await box.wait_for(timeout=30000)
        await page.wait_for_timeout(800)

        cdp = await ctx.new_cdp_session(page)

        async def on_frame(ev):
            frames.append((ev["metadata"]["timestamp"], ev["data"]))
            await cdp.send("Page.screencastFrameAck", {"sessionId": ev["sessionId"]})

        cdp.on("Page.screencastFrame", lambda ev: asyncio.ensure_future(on_frame(ev)))
        await cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 92, "maxWidth": 1170, "maxHeight": 2080, "everyNthFrame": 1})
        t0 = time.time()
        marks["_t0"] = t0
        mark = lambda n: marks.__setitem__(n, round(time.time() - t0, 3))

        await page.wait_for_timeout(700)
        mark("type")
        await box.tap()
        await box.type(QUESTION, delay=85)
        await page.wait_for_timeout(350)
        mark("send")
        await box.press("Enter")
        await page.get_by_text("tilt cylinder", exact=False).first.wait_for(timeout=45000)
        mark("answer")
        await page.wait_for_timeout(1600)
        await page.evaluate("window.scrollBy({top: 380, behavior: 'smooth'})")
        await page.wait_for_timeout(1500)
        mark("scrolled")
        await page.get_by_role("button", name="Investigate NVM-1040-HY").first.tap()
        await page.get_by_text("warehouses with stock", exact=False).first.wait_for(timeout=45000)
        await page.evaluate("window.scrollTo(0, 0)")
        mark("detail")
        await page.wait_for_timeout(1300)
        await page.evaluate("window.scrollBy({top: 520, behavior: 'smooth'})")
        await page.wait_for_timeout(1800)
        mark("end")
        await cdp.send("Page.stopScreencast")
        await page.wait_for_timeout(300)
        await browser.close()

    # frames arrive only on change: turn them into constant 30 fps with their real durations
    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(OUT)
    tmp = tempfile.mkdtemp()
    frames.sort(key=lambda f: f[0])
    start = frames[0][0]
    lines = []
    for i, (ts, data) in enumerate(frames):
        path = os.path.join(tmp, f"{i:05d}.jpg")
        open(path, "wb").write(base64.b64decode(data))
        dur = (frames[i + 1][0] - ts) if i + 1 < len(frames) else 0.5
        lines += [f"file '{path.replace(os.sep, '/')}'", f"duration {max(dur, 0.001):.4f}"]
    lines.append(lines[-2])
    lst = os.path.join(tmp, "list.txt")
    open(lst, "w").write("\n".join(lines))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-vf", "fps=30,scale=1080:-2:flags=lanczos",
                    "-q:v", "2", os.path.join(OUT, "%04d.jpg")], check=True)
    # express the marks on the video's own clock (frame 0 = first screencast frame)
    t0 = marks.pop("_t0")
    video_marks = {k: round(v + t0 - start, 3) for k, v in marks.items()}
    json.dump(video_marks, open(os.path.join(OUT, "marks.json"), "w"), indent=2)
    marks = video_marks
    print(json.dumps(marks), len(frames), "raw frames ->", len(os.listdir(OUT)) - 1, "jpgs")


asyncio.run(main())
