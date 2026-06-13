from __future__ import annotations

import argparse
from datetime import UTC, datetime
import os
from pathlib import Path
import tarfile
from typing import Any


DATA_PATHS = [
    Path("data") / "summary.json",
    Path("data") / "scorecards",
    Path("data") / "shots",
    Path("data") / "players",
    Path("data") / "snapshots",
    Path("data") / "sync",
    Path("data") / "annotations",
    Path("data") / "media",
    Path("data") / "mobile_events",
    Path("data") / "weather",
    Path("data") / "reports",
    Path("data") / "decision_audits",
]

GEOMETRY_OUTPUT_PATHS = [
    Path("output") / "prodgeometry_hazards",
    Path("output") / "prodgeometry",
]


def _display_path(path: Path) -> str:
    return path.name if path.is_absolute() else path.as_posix()


def _iter_files(source_root: Path, include_clubs: bool) -> list[Path]:
    files: list[Path] = []
    for relative in DATA_PATHS:
        path = source_root / relative
        if path.is_symlink():
            continue
        if path.is_file():
            files.append(relative)
        elif path.is_dir():
            files.extend(_iter_regular_files(source_root, path))
    for relative in GEOMETRY_OUTPUT_PATHS:
        path = source_root / relative
        if path.is_symlink():
            continue
        if path.is_dir():
            files.extend(relative for relative in _iter_regular_files(source_root, path) if relative.suffix == ".json")
    if include_clubs and _is_regular_file(source_root / "clubs.json"):
        files.append(Path("clubs.json"))
    return sorted(set(files))


def _iter_regular_files(source_root: Path, directory: Path) -> list[Path]:
    files: list[Path] = []
    for root, dirnames, filenames in os.walk(directory, followlinks=False):
        root_path = Path(root)
        dirnames[:] = [dirname for dirname in dirnames if not (root_path / dirname).is_symlink()]
        for filename in filenames:
            path = root_path / filename
            if _is_regular_file(path):
                files.append(path.relative_to(source_root))
    return sorted(files)


def _is_regular_file(path: Path) -> bool:
    return not path.is_symlink() and path.is_file()


def export_snapshot(
    *,
    source_root: Path | str = ".",
    output_path: Path | str,
    include_clubs: bool = False,
) -> dict[str, Any]:
    root = Path(source_root)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    files = _iter_files(root, include_clubs)
    with tarfile.open(output, "w:gz") as archive:
        for relative in files:
            archive.add(root / relative, arcname=relative.as_posix(), recursive=False)
    included_roots = {relative.parts[0] for relative in files if relative.parts}
    return {
        "schema": "ai-caddie-export-snapshot-v1",
        "createdAt": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "snapshotPath": _display_path(output),
        "sizeBytes": output.stat().st_size,
        "fileCount": len(files),
        "includedRoots": sorted(included_roots),
        "secretFree": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Export a private AI Caddie data snapshot.")
    parser.add_argument("--source-root", default=".", help="Repository root containing data/")
    parser.add_argument("--output", required=True, help="Output .tar.gz path")
    parser.add_argument("--include-clubs", action="store_true", help="Include local clubs.json")
    args = parser.parse_args()
    export_snapshot(
        source_root=args.source_root,
        output_path=args.output,
        include_clubs=args.include_clubs,
    )


if __name__ == "__main__":
    main()
