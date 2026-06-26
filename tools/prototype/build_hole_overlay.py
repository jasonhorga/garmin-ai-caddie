"""Overlay historical shots on Garmin's BirdsEye hole image.

Data source: logs/probe_map_bodies/snapshot_400065_hole.json
  Each shot has startLoc/endLoc with x/y pixel coords directly on the 730×730 image.

Usage: uv run build_hole_overlay.py [hole_number]
"""

from __future__ import annotations

import argparse
import io
import json
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]  # repo root: tools/<sub>/<file>.py is 2 dirs deep (P2 reorg fix)
SRC = ROOT / "logs" / "probe_map_bodies" / "snapshot_400065_hole.json"
OUT = ROOT / "output" / "hole_overlays"
OUT.mkdir(parents=True, exist_ok=True)

# Color per shot order (1st=red tee, 2nd=orange, 3rd=yellow, putts=blue)
ORDER_COLORS = {
    1: (220, 50, 50),
    2: (240, 140, 40),
    3: (240, 210, 50),
    4: (120, 200, 60),
    5: (60, 180, 200),
    6: (90, 120, 220),
}
PUTT_COLOR = (40, 80, 220)


def fetch_image(url: str) -> Image.Image:
    cache = OUT / ("img_" + url.split("/")[-1].split("?")[0])
    if cache.exists():
        return Image.open(cache).convert("RGBA")
    with urllib.request.urlopen(url, timeout=20) as r:
        data = r.read()
    cache.write_bytes(data)
    return Image.open(io.BytesIO(data)).convert("RGBA")


def shot_color(shot: dict) -> tuple[int, int, int]:
    if shot.get("shotType") == "PUTT":
        return PUTT_COLOR
    return ORDER_COLORS.get(shot["shotOrder"], (180, 180, 180))


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in (
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


SS = 4  # overlay supersampling factor (anti-aliased via LANCZOS downscale)


def draw_hole(hole: dict, out_path: Path, focus_round: int | None) -> None:
    img = fetch_image(hole["holeImageUrl"])
    W, H = img.size
    overlay_hi = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay_hi)

    by_round: dict[int, list[dict]] = {}
    for s in hole["shots"]:
        by_round.setdefault(s["scorecardId"], []).append(s)
    for shots in by_round.values():
        shots.sort(key=lambda s: s["shotOrder"])

    if focus_round is None and by_round:
        focus_round = max(
            by_round, key=lambda sid: max(s["shotTime"] for s in by_round[sid])
        )

    # Connecting line for focus round only
    if focus_round in by_round:
        pts = []
        for s in by_round[focus_round]:
            sx, sy = s["startLoc"].get("x"), s["startLoc"].get("y")
            ex, ey = s["endLoc"].get("x"), s["endLoc"].get("y")
            if sx is not None and sy is not None and not pts:
                pts.append((sx * SS, sy * SS))
            if ex is not None and ey is not None:
                pts.append((ex * SS, ey * SS))
        if len(pts) >= 2:
            d.line(pts, fill=(255, 255, 255, 210), width=2 * SS)

    # Non-focus endpoints first (small background dots, no outline)
    for s in hole["shots"]:
        if s["scorecardId"] == focus_round:
            continue
        ex, ey = s["endLoc"].get("x"), s["endLoc"].get("y")
        if ex is None or ey is None:
            continue
        c = shot_color(s)
        r = 4 * SS
        cx, cy = ex * SS, ey * SS
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=c + (160,))

    # Focus endpoints on top: bigger, filled, white outer ring + dark inner outline
    if focus_round in by_round:
        for s in by_round[focus_round]:
            ex, ey = s["endLoc"].get("x"), s["endLoc"].get("y")
            if ex is None or ey is None:
                continue
            c = shot_color(s)
            r = 7 * SS
            cx, cy = ex * SS, ey * SS
            d.ellipse(
                (cx - r - SS, cy - r - SS, cx + r + SS, cy + r + SS),
                outline=(255, 255, 255, 240),
                width=2 * SS,
            )
            d.ellipse(
                (cx - r, cy - r, cx + r, cy + r),
                fill=c + (245,),
                outline=(0, 0, 0, 230),
                width=max(1, SS // 2),
            )

    # Tee markers
    for shots in by_round.values():
        first = shots[0]
        sx, sy = first["startLoc"].get("x"), first["startLoc"].get("y")
        if sx is None or sy is None:
            continue
        is_focus = first["scorecardId"] == focus_round
        cx, cy = sx * SS, sy * SS
        if is_focus:
            size = 6 * SS
            d.rectangle(
                (cx - size - SS, cy - size - SS, cx + size + SS, cy + size + SS),
                outline=(255, 255, 255, 240),
                width=2 * SS,
            )
            d.rectangle(
                (cx - size, cy - size, cx + size, cy + size),
                fill=(255, 255, 255, 240),
                outline=(0, 0, 0, 230),
                width=max(1, SS // 2),
            )
        else:
            size = 4 * SS
            d.rectangle(
                (cx - size, cy - size, cx + size, cy + size),
                fill=(255, 255, 255, 160),
            )

    overlay = overlay_hi.resize((W, H), Image.LANCZOS)
    composed = Image.alpha_composite(img, overlay)

    # Legend (bottom-right)
    legend_items = [
        ((255, 255, 255), "■", "Tee"),
        (ORDER_COLORS[1], "●", "1st shot"),
        (ORDER_COLORS[2], "●", "2nd"),
        (ORDER_COLORS[3], "●", "3rd"),
        (ORDER_COLORS[4], "●", "4th"),
        (ORDER_COLORS[5], "●", "5th"),
        (ORDER_COLORS[6], "●", "6th+"),
        (PUTT_COLOR, "●", "Putt"),
    ]
    lf = _font(13)
    lw, lh = 110, 18 * len(legend_items) + 12
    lx, ly = composed.width - lw - 10, composed.height - lh - 10
    legend_bg = Image.new("RGBA", (lw, lh), (0, 0, 0, 170))
    lb = ImageDraw.Draw(legend_bg)
    for i, (color, _, label) in enumerate(legend_items):
        y = 6 + i * 18
        if label == "Tee":
            lb.rectangle((8, y + 3, 16, y + 11), fill=color + (255,), outline=(0, 0, 0))
        else:
            lb.ellipse((7, y + 2, 17, y + 12), fill=color + (255,), outline=(0, 0, 0))
        lb.text((24, y), label, fill=(255, 255, 255), font=lf)
    composed.paste(legend_bg, (lx, ly), legend_bg)

    # Title bar
    bar = Image.new("RGBA", (composed.width, 40), (0, 0, 0, 170))
    bd = ImageDraw.Draw(bar)
    n_rounds = len(by_round)
    n_shots = len(hole["shots"])
    focus_label = ""
    if focus_round in by_round:
        ts = max(s["shotTime"] for s in by_round[focus_round]) / 1000
        offset = by_round[focus_round][0].get("shotTimeZoneOffset", 0) / 1000
        dt = datetime.fromtimestamp(ts, tz=timezone(timedelta(seconds=offset)))
        focus_label = f"  ·  viewing {dt:%Y-%m-%d}"
    bd.text(
        (10, 10),
        f"Hole {hole['holeNumber']}  ·  {n_rounds} rounds  ·  {n_shots} shots{focus_label}",
        fill=(255, 255, 255),
        font=_font(18),
    )
    final = Image.new("RGBA", (composed.width, composed.height + 40))
    final.paste(bar, (0, 0))
    final.paste(composed, (0, 40))

    final.convert("RGB").save(out_path, "JPEG", quality=88)
    print(f"  wrote {out_path}  ({n_rounds} rounds, {n_shots} shots, focus={focus_round})")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("hole", nargs="?", type=int, help="hole number; default = all 18")
    p.add_argument("--round", type=int, default=None,
                   help="scorecardId to highlight (default: most recent)")
    args = p.parse_args()

    data = json.loads(SRC.read_text())
    holes = {h["holeNumber"]: h for h in data["holeShots"]}
    target = [args.hole] if args.hole else sorted(holes.keys())
    for n in target:
        out = OUT / f"hole_{n:02d}.jpg"
        draw_hole(holes[n], out, args.round)


if __name__ == "__main__":
    main()
