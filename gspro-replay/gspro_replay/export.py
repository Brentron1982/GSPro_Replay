"""Render replay.html to MP4: headless Chromium draws each frame through the
viewer's deterministic export API, JPEG frames are piped into ffmpeg (H.264)."""
from __future__ import annotations

import base64
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path


def _ffmpeg():
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        sys.exit("ffmpeg not found. Install it (https://ffmpeg.org) or: pip install imageio-ffmpeg")


def _launch(pw):
    args = ["--ignore-gpu-blocklist", "--enable-gpu-rasterization"]
    if platform.system() == "Linux":
        args += ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
    errors = []
    for kw in ({}, {"channel": "msedge"}, {"channel": "chrome"}):
        try:
            return pw.chromium.launch(args=args, **kw)
        except Exception as e:  # noqa: BLE001
            errors.append(str(e).splitlines()[0])
    sys.exit("Could not start a Chromium browser. Run:  python -m playwright install chromium\n" + "\n".join(errors))


def export(replay_html, output, fps=30, width=1920, height=1080, speed=1.0, holes=None,
           crf=20, preset="veryfast", style="lowpoly", camera="broadcast"):
    from playwright.sync_api import sync_playwright
    replay_html = Path(replay_html).resolve()
    if not replay_html.exists():
        sys.exit(f"{replay_html} not found")
    width -= width % 2
    height -= height % 2
    ff = _ffmpeg()
    with sync_playwright() as pw:
        browser = _launch(pw)
        page = browser.new_page(viewport={"width": width, "height": height})
        page.on("pageerror", lambda e: print("  page error:", e))
        page.goto(replay_html.as_uri() + "?export", timeout=120000)
        page.wait_for_function("window.replay !== undefined", timeout=120000)
        page.evaluate("replay.ready")
        page.evaluate(f"replay.setup({{width:{width},height:{height},style:'{style}',camera:'{camera}'}})")
        ranges = page.evaluate(f"replay.ranges({sorted(holes) if holes else []})")
        times = []
        for t0, t1 in ranges:
            t = t0
            while t < t1:
                times.append(t)
                t += speed / fps
        n = len(times)
        print(f"• rendering {n} frames ({n / fps / 60:.1f} min of video) at {width}x{height}@{fps}")
        cmd = [ff, "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(fps), "-c:v", "mjpeg",
               "-i", "-", "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p",
               "-movflags", "+faststart", str(output)]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        t_start = time.time()
        try:
            for i, t in enumerate(times):
                page.evaluate(f"replay.frame({t})")
                proc.stdin.write(base64.b64decode(page.evaluate("replay.grab(0.93)")))
                if i % 30 == 0 or i == n - 1:
                    el = time.time() - t_start
                    rate = (i + 1) / el if el else 0
                    eta = (n - i - 1) / rate if rate else 0
                    print(f"\r  {i + 1}/{n} frames  {rate:.1f} fps  ETA {int(eta // 60)}:{int(eta % 60):02d}  ",
                          end="", flush=True)
        finally:
            proc.stdin.close()
            proc.wait()
            browser.close()
    print(f"\n• saved {output}")
