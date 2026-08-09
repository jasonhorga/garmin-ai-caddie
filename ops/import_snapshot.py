from __future__ import annotations

import argparse
from pathlib import Path, PurePosixPath
import shutil
import tarfile

SUPPORTED_OUTPUT_DIRS = {
    ("output", "prodgeometry_hazards"),
    ("output", "prodgeometry"),
}


def _is_secret_path(path: PurePosixPath) -> bool:
    return any(
        part == ".garmin_tokens" or part == ".env" or part.startswith(".env.")
        for part in path.parts
    )


def _is_supported_output_path(path: PurePosixPath) -> bool:
    if len(path.parts) < 3:
        return False
    return path.parts[:2] in SUPPORTED_OUTPUT_DIRS and path.suffix == ".json"


def _validate_member_name(name: str) -> None:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"unsafe snapshot path: {name}")
    if not path.parts:
        raise ValueError("empty snapshot path")
    if _is_secret_path(path):
        raise ValueError(f"credential material is not accepted in snapshots: {name}")
    if path.parts[0] == "output":
        if not _is_supported_output_path(path):
            raise ValueError(f"unsupported snapshot path: {name}")
        return
    if path.parts[0] != "data" and name != "clubs.json":
        raise ValueError(f"unsupported snapshot path: {name}")


def import_snapshot(tarball: Path | str, *, target_root: Path | str = ".") -> Path:
    root = Path(target_root)
    root.mkdir(parents=True, exist_ok=True)
    root_resolved = root.resolve()
    with tarfile.open(tarball, "r:gz") as archive:
        for member in archive.getmembers():
            _validate_member_name(member.name)
            if not member.isfile() and not member.isdir():
                raise ValueError(f"unsupported snapshot member type: {member.name}")
            target = (root / member.name).resolve()
            if root_resolved not in [target, *target.parents]:
                raise ValueError(f"snapshot path escapes target root: {member.name}")
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                continue
            with source, target.open("wb") as handle:
                shutil.copyfileobj(source, handle)
    return root


def main() -> None:
    parser = argparse.ArgumentParser(description="Import a private AI Caddie data snapshot.")
    parser.add_argument("tarball", help="Snapshot .tar.gz path")
    parser.add_argument("--target-root", default=".", help="Repository root to restore into")
    args = parser.parse_args()
    import_snapshot(args.tarball, target_root=args.target_root)


if __name__ == "__main__":
    main()
