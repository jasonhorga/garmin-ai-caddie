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
    if counts["executed"] != 10 or counts["skipped"] or not list(output.glob("*--*.png")):
        raise ValueError(f"Incomplete actual simulator evidence: tests={counts}")


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("resolve", "collect", "sheets"))
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
    else:
        sheets(args.input, args.output)


if __name__ == "__main__":
    main()
