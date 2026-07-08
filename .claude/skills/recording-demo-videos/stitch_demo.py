#!/usr/bin/env python3
"""Stitch ordered per-step screenshots into a captioned demo mp4 — one tool for iOS / Watch / Web.

Each terminal just produces ordered, labelled screenshots (iOS: XCUITest; Watch: simctl -uitest-screen;
Web: Playwright). This turns them into a demo the viewer can follow SILENTLY at a readable pace:
one screenshot per step held ~4.5s with a plain-Chinese caption strip across the top → mp4 (H.264,
yuv420p, +faststart, no audio) so Safari/iOS play it. Deterministic (no live-capture timing/desktop
artefacts), and the frames ARE the screenshots so it's easy to verify.

Usage: stitch_demo.py manifest.json out.mp4
  manifest.json = [{"image": "path.png", "caption": "一句人话"}, ...]
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFont

FONT_PATH = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"
DWELL_SECONDS = 4.5   # hold each step long enough to read (skill rule: ~3 words/s + time to see the screen)
TARGET_H = 1280       # normalise all frames to this height (even dims for H.264)


def render_frame(image_path: str, caption: str, out_path: str) -> None:
    im = Image.open(image_path).convert("RGB")
    w, h = im.size
    nh = TARGET_H
    nw = max(2, int(round(w * nh / h)))
    nw -= nw % 2
    nh -= nh % 2
    im = im.resize((nw, nh), Image.LANCZOS)

    strip_h = max(56, nh // 14)
    fs = max(22, strip_h // 2)
    font = ImageFont.truetype(FONT_PATH, fs)
    d = ImageDraw.Draw(im)
    # shrink the font until the caption fits the width with margin
    while d.textlength(caption, font=font) > nw - 28 and fs > 14:
        fs -= 2
        font = ImageFont.truetype(FONT_PATH, fs)

    strip = Image.new("RGBA", (nw, strip_h), (15, 23, 42, 235))  # dark, near-opaque
    sd = ImageDraw.Draw(strip)
    tw = sd.textlength(caption, font=font)
    bbox = sd.textbbox((0, 0), caption, font=font)
    ty = (strip_h - (bbox[3] - bbox[1])) // 2 - bbox[1]
    sd.text(((nw - tw) // 2, ty), caption, fill=(255, 255, 255), font=font)

    frame = im.convert("RGBA")
    frame.alpha_composite(strip, (0, 0))
    frame.convert("RGB").save(out_path)


def main() -> int:
    manifest = json.load(open(sys.argv[1], encoding="utf-8"))
    out = sys.argv[2]
    tmp = tempfile.mkdtemp(prefix="demo-frames-")
    frames = []
    for i, step in enumerate(manifest):
        fp = os.path.join(tmp, f"f{i:03d}.png")
        render_frame(step["image"], step["caption"], fp)
        frames.append(fp)

    listf = os.path.join(tmp, "list.txt")
    with open(listf, "w", encoding="utf-8") as f:
        for fp in frames:
            f.write(f"file '{fp}'\nduration {DWELL_SECONDS}\n")
        f.write(f"file '{frames[-1]}'\n")  # concat demuxer ignores the last duration → repeat the frame

    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", listf,
         "-vf", "fps=25,format=yuv420p", "-c:v", "libx264", "-crf", "23",
         "-movflags", "+faststart", "-an", out],
        check=True,
    )
    print(f"wrote {out} ({len(frames)} steps, ~{len(frames) * DWELL_SECONDS:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
