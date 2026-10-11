#!/usr/bin/env python3
"""Issue #417: reproducible device selection, public evidence and face comparisons."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

FACE_TYPES = {
    "41mm": ("Apple Watch Series 9 (41mm)", "Apple Watch Series 8 (41mm)"),
    "46mm": ("Apple Watch Series 10 (46mm)",),
    "49mm": ("Apple Watch Ultra 2 (49mm)", "Apple Watch Ultra (49mm)"),
}
FACES = tuple(FACE_TYPES)
# The class currently contains ten original whole-round methods plus three element/tempo passes.
# Keep this explicit so a silently filtered XCTest run cannot be reported as a complete audit.
EXPECTED_AUDIT_TESTS = 13


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
    (output / "result.json").write_text(json.dumps({
        "face": face, "outcome": outcome,
        "screenshots": len(list(output.glob("*--*.png"))),
        "source": os.environ.get("GITHUB_SHA", "unknown"),
        "run": os.environ.get("GITHUB_RUN_ID", "unknown"),
        "tests": counts,
        "observations": len(list(output.glob("observation--*.json"))),
    }, indent=2) + "\n")
    if counts["executed"] != EXPECTED_AUDIT_TESTS or counts["skipped"] or not list(output.glob("*--*.png")):
        raise ValueError(f"Incomplete actual simulator evidence: expected={EXPECTED_AUDIT_TESTS} tests={counts}")


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
            sheet = Image.new("RGB", (450 * 3, 565 * len(page)), "#141414")
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
    "46mm": {"dpi": 326, "displayMm": [32.4, 38.7]},
    "49mm": {"dpi": 338, "displayMm": [30.8, 37.7]},
}


def physical(root: Path, output: Path) -> None:
    """Emit print-scale and bright-glare variants for every real simulator screenshot."""
    from PIL import Image, ImageEnhance, ImageDraw, ImageFont

    output.mkdir(parents=True, exist_ok=True)
    manifest = {"kind": "physical-scale-and-glare", "faces": {}}
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
