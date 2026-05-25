from __future__ import annotations

import argparse
from pathlib import Path
import tarfile


DATA_PATHS = [
    Path("data") / "summary.json",
    Path("data") / "scorecards",
    Path("data") / "shots",
    Path("data") / "snapshots",
    Path("data") / "sync",
    Path("data") / "annotations",
    Path("data") / "media",
    Path("data") / "mobile_events",
]


def _iter_files(source_root: Path, include_clubs: bool) -> list[Path]:
    files: list[Path] = []
    for relative in DATA_PATHS:
        path = source_root / relative
        if path.is_file():
            files.append(relative)
        elif path.is_dir():
            files.extend(sorted(item.relative_to(source_root) for item in path.rglob("*") if item.is_file()))
    if include_clubs and (source_root / "clubs.json").is_file():
        files.append(Path("clubs.json"))
    return sorted(set(files))


def export_snapshot(
    *,
    source_root: Path | str = ".",
    output_path: Path | str,
    include_clubs: bool = False,
) -> Path:
    root = Path(source_root)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, "w:gz") as archive:
        for relative in _iter_files(root, include_clubs):
            archive.add(root / relative, arcname=relative.as_posix(), recursive=False)
    return output


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
