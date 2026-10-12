#!/usr/bin/env python3
"""Issue #417: reproducible device selection, public evidence and face comparisons."""
from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

FACE_TYPES = {
    "41mm": ("Apple Watch Series 9 (41mm)", "Apple Watch Series 8 (41mm)"),
    "42mm": ("Apple Watch Series 10 (42mm)",),
    "45mm": ("Apple Watch Series 9 (45mm)", "Apple Watch Series 8 (45mm)"),
    "46mm": ("Apple Watch Series 10 (46mm)",),
    "49mm": ("Apple Watch Ultra 2 (49mm)", "Apple Watch Ultra (49mm)"),
}
FACES = tuple(FACE_TYPES)
# This temporary #422 candidate carries five prototype-only methods, not the older whole-round
# product test suite. A filtered/empty XCTest run cannot become complete prototype coverage.
EXPECTED_AUDIT_TESTS = 5


def newest_watch_runtime(runtimes: list[dict]) -> dict:
    candidates = [r for r in runtimes if r.get("isAvailable") is True
                  and ".watchOS-" in r.get("identifier", "")]
    if not candidates:
        raise ValueError("No available watchOS simulator runtime")
    return max(candidates, key=lambda r: tuple(int(v) for v in r["version"].split(".")))


def face_type(face: str, types: list[dict]) -> dict:
    for name in FACE_TYPES[face]:
        for device in types:
            if device.get("name") == name:
                return device
    raise ValueError(f"Required {face} Watch device type is unavailable")


def resolve(face: str, output: Path) -> None:
    def inventory(kind: str) -> dict:
        return json.loads(subprocess.check_output(["xcrun", "simctl", "list", kind, "-j"]))
    runtime = newest_watch_runtime(inventory("runtimes")["runtimes"])
    device = face_type(face, inventory("devicetypes")["devicetypes"])
    # Do not silently downgrade the runtime if a requested face cannot run on the newest one.
    udid = subprocess.check_output([
        "xcrun", "simctl", "create", f"AI Caddie Audit {face}",
        device["identifier"], runtime["identifier"],
    ], text=True).strip()
    metadata = {"face": face, "device": device["name"], "udid": udid,
                "runtime": runtime["name"], "runtimeVersion": runtime["version"],
                "source": os.environ.get("GITHUB_SHA", "unknown"),
                "prototypeBaseSource": os.environ.get("PROTOTYPE_BASE_SHA", "unknown"),
                "run": os.environ.get("GITHUB_RUN_ID", "unknown"),
                "xcode": subprocess.check_output(["xcodebuild", "-version"], text=True).strip()}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"{face}: {device['name']} / {runtime['name']}")


def sanitize(text: str) -> str:
    for key in ("GITHUB_WORKSPACE", "RUNNER_TEMP", "HOME"):
        prefix = os.environ.get(key)
        if prefix:
            text = text.replace(prefix, f"[{key}]")
    text = re.sub(r"/Users/[^/\s]+", "[RUNNER]", text)
    return text


def test_counts(text: str) -> dict[str, int]:
    # Count terminal methods, not repeated suite totals or merely started tests. A skipped or
    # empty UI run must not become a green screenshot-collection claim.
    results = dict(re.findall(
        r"Test Case '-\[AICaddieWatchUITests\.WatchWholeRoundAuditUITests (test\w+)\]' "
        r"(passed|failed|skipped)", text
    ))
    return {"executed": len(results), **{
        status: sum(value == status for value in results.values())
        for status in ("passed", "failed", "skipped")
    }}


def collect(face: str, udid: str, outcome: str, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    if udid:
        root = Path.home() / "Library/Developer/CoreSimulator/Devices" / udid / "data"
        for directory in root.glob("Containers/Data/Application/*/Documents/watch-audit"):
            for source in directory.iterdir():
                if source.suffix in (".png", ".json"):
                    shutil.copy2(source, output / source.name)
    log = Path(os.environ["RUNNER_TEMP"]) / "watch-audit-xcode.log"
    counts = test_counts(log.read_text(errors="replace")) if log.exists() else test_counts("")
    if log.exists():
        (output / "test.log").write_text(sanitize(log.read_text(errors="replace")))
    selection = os.environ.get("AUDIT_SELECTION", "full")
    expected = {"prototype-elements": 5}.get(selection, EXPECTED_AUDIT_TESTS)
    (output / "result.json").write_text(json.dumps({
        "face": face, "outcome": outcome,
        "screenshots": len(list(output.glob("*--*.png"))),
        "source": os.environ.get("GITHUB_SHA", "unknown"),
        "prototypeBaseSource": os.environ.get("PROTOTYPE_BASE_SHA", "unknown"),
        "run": os.environ.get("GITHUB_RUN_ID", "unknown"),
        "tests": counts,
        "selection": selection,
        "expectedMethods": expected,
        "observations": len(list(output.glob("observation--*.json"))),
    }, indent=2) + "\n")
    if counts["executed"] != expected or counts["skipped"] or not list(output.glob("*--*.png")):
        raise ValueError(f"Incomplete actual simulator evidence: selection={selection} expected={expected} tests={counts}")


def grouped_steps(root: Path) -> dict[str, dict[str, dict[str, Path]]]:
    flows: dict[str, dict[str, dict[str, Path]]] = {}
    for face in FACES:
        for image in sorted((root / f"watch-audit-{face}").glob("*--*.png")):
            flow, step = image.stem.split("--", 1)
            flows.setdefault(flow, {}).setdefault(step, {})[face] = image
    return flows


def sheets(root: Path, output: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont
    output.mkdir(parents=True, exist_ok=True)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 18)
    except OSError:
        font = ImageFont.load_default(size=18)
    coverage = []
    for flow, steps in sorted(grouped_steps(root).items()):
        # Keep contact sheets reviewable: at most six steps per sheet; never rescale the faces.
        items = sorted(steps.items())
        for offset in range(0, len(items), 6):
            page = items[offset:offset + 6]
            sheet = Image.new("RGB", (450 * len(FACES), 565 * len(page)), "#141414")
            draw = ImageDraw.Draw(sheet)
            for row, (step, images) in enumerate(page):
                for col, face in enumerate(FACES):
                    x, y = col * 450, row * 565
                    draw.text((x + 8, y + 5), f"{face} | {flow}", font=font, fill="white")
                    draw.text((x + 8, y + 27), step[:48], font=font, fill="white")
                    source = images.get(face)
                    if source:
                        image = Image.open(source).convert("RGB")
                        sheet.paste(image, (x + (450 - image.width) // 2, y + 59))
                    else:
                        draw.text((x + 20, y + 180), "NOT CAPTURED", font=font, fill="#ff655b")
                coverage.append({"flow": flow, "step": step,
                                 "capturedFaces": sorted(images),
                                 "missingFaces": [f for f in FACES if f not in images]})
            sheet.save(output / f"{flow}-{offset // 6 + 1:02d}.png")
    (output / "coverage.json").write_text(json.dumps(coverage, indent=2) + "\n")
    if not coverage:
        raise ValueError("No actual simulator screenshots were captured")


PHYSICAL_RENDER = {
    # Screenshot pixels / native display density. The dimensions describe the visible panel,
    # rather than the bezel, so a reviewer can print/view the PNG at the recorded DPI.
    "41mm": {"dpi": 326, "displayMm": [27.5, 33.4]},
    "42mm": {"dpi": 326, "displayMm": [29.1, 34.8]},
    "45mm": {"dpi": 326, "displayMm": [30.9, 37.7]},
    "46mm": {"dpi": 326, "displayMm": [32.4, 38.7]},
    "49mm": {"dpi": 338, "displayMm": [30.8, 37.7]},
}


def physical(root: Path, output: Path) -> None:
    """Emit print-scale and bright-glare variants for every real simulator screenshot."""
    from PIL import Image, ImageEnhance, ImageDraw, ImageFont

    output.mkdir(parents=True, exist_ok=True)
    manifest = {"kind": "physical-scale-and-glare", "faces": {},
                "hardwareSunlightProven": False,
                "scaleRule": "Print at 100%; verify the 5mm bar. Browser zoom alone is not physical scale."}
    cards = []
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 16)
    except OSError:
        font = ImageFont.load_default()
    for face, spec in PHYSICAL_RENDER.items():
        source_dir = root / f"watch-audit-{face}"
        destination = output / face
        destination.mkdir(parents=True, exist_ok=True)
        images = sorted(source_dir.glob("*.png"))
        manifest["faces"][face] = {
            **spec,
            "sourceImages": len(images),
            "physicalImages": len(images),
            "glareImages": len(images),
        }
        for source in images:
            image = Image.open(source).convert("RGB")
            width_mm = image.width * 25.4 / spec["dpi"]
            height_mm = image.height * 25.4 / spec["dpi"]
            manifest["faces"][face]["actualScreenshotMm"] = [
                round(width_mm, 3), round(height_mm, 3)]
            # Keep the simulator pixels unchanged; the DPI tag and scale bar make physical size
            # explicit without resampling away a one-pixel text/edge defect.
            bar = max(1, round(5 * spec["dpi"] / 25.4))
            canvas = Image.new("RGB", (image.width, image.height + 34), "#111111")
            canvas.paste(image, (0, 0))
            draw = ImageDraw.Draw(canvas)
            draw.rectangle((8, image.height + 8, 8 + bar, image.height + 12), fill="#ffd447")
            draw.text((16 + bar, image.height + 4),
                      f"{face}  5 mm bar  {spec['displayMm'][0]}×{spec['displayMm'][1]} mm @ {spec['dpi']} dpi",
                      font=font, fill="white")
            canvas.save(destination / f"{source.stem}-physical.png", dpi=(spec["dpi"], spec["dpi"]))

            # A conservative bright/glare simulation: lift luminance and add a diagonal white
            # reflection. It is a review aid, not a photometric claim about sunlight.
            bright = ImageEnhance.Brightness(image).enhance(1.28)
            glare = Image.new("RGBA", bright.size, (255, 255, 255, 0))
            glare_draw = ImageDraw.Draw(glare)
            width, height = bright.size
            glare_draw.polygon([(int(width * 0.54), 0), (width, 0),
                                (width, int(height * 0.28)),
                                (int(width * 0.76), int(height * 0.20))],
                               fill=(255, 255, 255, 68))
            bright = Image.alpha_composite(bright.convert("RGBA"), glare).convert("RGB")
            bright_canvas = Image.new("RGB", (bright.width, bright.height + 34), "#111111")
            bright_canvas.paste(bright, (0, 0))
            draw = ImageDraw.Draw(bright_canvas)
            draw.rectangle((8, bright.height + 8, 8 + bar, bright.height + 12), fill="#ffd447")
            draw.text((16 + bar, bright.height + 4), f"{face}  bright/glare review aid",
                      font=font, fill="white")
            bright_canvas.save(destination / f"{source.stem}-glare.png",
                               dpi=(spec["dpi"], spec["dpi"]))
            cards.append(
                f'<article><h2>{html.escape(face)} · {html.escape(source.stem)}</h2>'
                f'<p>{width_mm:.2f} × {height_mm:.2f} mm · original pixels; simulated glare</p>'
                f'<div class="pair"><img style="width:{width_mm:.6f}mm" '
                f'src="{html.escape(face)}/{html.escape(source.stem)}-physical.png">'
                f'<img style="width:{width_mm:.6f}mm" '
                f'src="{html.escape(face)}/{html.escape(source.stem)}-glare.png"></div></article>'
            )
    (output / "physical-review.html").write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<title>Watch #417 physical-scale evidence</title><style>'
        '@page{size:A4;margin:12mm}body{font:12px system-ui;color:#111}'
        'article{break-inside:avoid;border-top:1px solid #ccc;padding:4mm 0}'
        'h2{font-size:12px;margin:0}p{font-size:10px;margin:2mm 0}'
        '.pair{display:flex;align-items:flex-start;gap:5mm}img{height:auto;max-width:none}'
        '.ruler{width:5mm;height:1mm;background:#111;margin:3mm 0}'
        '</style><h1>Physical-scale review</h1>'
        '<p>Print at 100% / actual size, with fit-to-page disabled. Verify this 5mm ruler '
        'using a physical ruler. Browser CSS mm and enlarged chat images are not proof of wrist scale.</p>'
        '<div class="ruler"></div><p>The image itself is not resampled. Bright/glare versions '
        'are inspection aids, not measured sunlight or OLED luminance. Hardware first-try success, '
        'Crown, gloves, wet fingers and arm-length readability remain unproved.</p>'
        + "".join(cards) + '</html>', encoding="utf-8")
    (output / "physical-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    if not any(output.rglob("*-physical.png")):
        raise ValueError("No physical-scale screenshots were generated")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("resolve", "collect", "sheets", "physical"))
    parser.add_argument("--face", choices=FACES)
    parser.add_argument("--udid", default="")
    parser.add_argument("--outcome", default="unknown")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.operation == "resolve":
        resolve(args.face, args.output)
    elif args.operation == "collect":
        collect(args.face, args.udid, args.outcome, args.output)
    elif args.operation == "sheets":
        sheets(args.input, args.output)
    else:
        physical(args.input, args.output)


if __name__ == "__main__":
    main()
