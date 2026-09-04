from __future__ import annotations

import argparse
from datetime import UTC, datetime
import os
from pathlib import Path
from pathlib import PurePosixPath
import sqlite3
import subprocess
import tarfile
from tempfile import TemporaryDirectory
from typing import Any
from urllib.parse import unquote


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
    Path("data") / "decisions",  # P2: the live caddie decisions ledger (decisions.jsonl) — was omitted
]

GEOMETRY_OUTPUT_PATHS = [
    Path("output") / "prodgeometry_hazards",
    Path("output") / "prodgeometry",
]

IDENTITY_SQLITE_MEMBER = Path("data") / "identity.db"
IDENTITY_POSTGRES_MEMBER = Path("data") / "identity.pg_dump"


def _is_secret_path(path: Path | PurePosixPath) -> bool:
    """Return whether a path is credential material that must never enter a snapshot."""
    return any(
        part == ".garmin_tokens" or part == ".env" or part.startswith(".env.")
        for part in path.parts
    )


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
        dirnames[:] = [
            dirname
            for dirname in dirnames
            if not (root_path / dirname).is_symlink()
            and not _is_secret_path((root_path / dirname).relative_to(source_root))
        ]
        for filename in filenames:
            path = root_path / filename
            relative = path.relative_to(source_root)
            if _is_regular_file(path) and not _is_secret_path(relative):
                files.append(relative)
    return sorted(files)


def _is_regular_file(path: Path) -> bool:
    return not path.is_symlink() and path.is_file()


def _sqlite_path(database_url: str, source_root: Path) -> Path:
    for prefix in ("sqlite+pysqlite:///", "sqlite:///"):
        if database_url.startswith(prefix):
            raw_path = unquote(database_url[len(prefix) :].split("?", 1)[0])
            if not raw_path or raw_path == ":memory:":
                raise RuntimeError("an in-memory SQLite identity database cannot be backed up")
            path = Path(raw_path)
            return path if path.is_absolute() else source_root / path
    raise RuntimeError("unsupported SQLite database URL")


def _backup_sqlite(source: Path, destination: Path) -> None:
    if not _is_regular_file(source):
        raise RuntimeError("configured SQLite identity database does not exist")
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_uri = f"{source.resolve().as_uri()}?mode=ro"
    with sqlite3.connect(source_uri, uri=True) as source_db, sqlite3.connect(destination) as backup_db:
        source_db.backup(backup_db)


def _libpq_database_url(database_url: str) -> str:
    for prefix in ("postgresql+psycopg://", "postgresql+psycopg2://"):
        if database_url.startswith(prefix):
            return "postgresql://" + database_url[len(prefix) :]
    if database_url.startswith(("postgresql://", "postgres://")):
        return database_url
    raise RuntimeError("unsupported PostgreSQL database URL")


def _backup_postgres(database_url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    # Keep credentials out of argv/process listings. libpq accepts a connection URI in PGDATABASE.
    environment["PGDATABASE"] = _libpq_database_url(database_url)
    try:
        completed = subprocess.run(
            [
                "pg_dump",
                "--format=custom",
                "--no-owner",
                "--no-privileges",
                "--file",
                str(destination),
            ],
            check=False,
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("pg_dump is required to back up the configured PostgreSQL identity database") from exc
    if completed.returncode != 0 or not _is_regular_file(destination):
        raise RuntimeError("pg_dump failed; no snapshot was created")


def audit_snapshot(snapshot: Path | str) -> dict[str, Any]:
    """Audit the finished tar, rather than trusting the pre-archive file selection.

    ``secretFree`` is DERIVED from this scan of the archive that was actually written — it is never
    a constant. Every member is checked; the offenders are collected and the audit then fails closed
    (``RuntimeError``) instead of returning a manifest that claims a clean snapshot. A manifest can
    therefore only ever carry ``secretFree: true`` for an archive in which this scan found nothing.
    The scan is path-based (the credential material this exporter can emit is whole files:
    ``.garmin_tokens``, ``.env*``), so it proves "no credential FILE was archived", not "no secret
    string exists anywhere inside an archived evidence file".
    """
    names: list[str] = []
    secret_members: list[str] = []
    identity_backup = "none"
    with tarfile.open(snapshot, "r:gz") as archive:
        for member in archive.getmembers():
            path = PurePosixPath(member.name)
            if _is_secret_path(path):
                secret_members.append(member.name)
                continue
            if not member.isfile():
                raise RuntimeError(f"snapshot contains unsupported member type: {member.name}")
            names.append(member.name)
            if path == PurePosixPath(IDENTITY_SQLITE_MEMBER.as_posix()):
                identity_backup = "sqlite"
            elif path == PurePosixPath(IDENTITY_POSTGRES_MEMBER.as_posix()):
                identity_backup = "postgresql"
    secret_free = not secret_members
    if not secret_free:
        raise RuntimeError(f"snapshot contains forbidden credential path: {secret_members[0]}")
    return {
        "secretFree": secret_free,
        "fileCount": len(names),
        "identityBackup": identity_backup,
    }


def export_snapshot(
    *,
    source_root: Path | str = ".",
    output_path: Path | str,
    include_clubs: bool = False,
    database_url: str | None = None,
) -> dict[str, Any]:
    root = Path(source_root)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    files = _iter_files(root, include_clubs)
    configured_database_url = database_url if database_url is not None else os.environ.get("AI_CADDIE_DATABASE_URL")

    try:
        with TemporaryDirectory(prefix="ai-caddie-identity-backup-") as temp_dir:
            identity_backup: tuple[Path, Path] | None = None
            if configured_database_url:
                if configured_database_url.startswith("sqlite"):
                    backup_path = Path(temp_dir) / "identity.db"
                    _backup_sqlite(_sqlite_path(configured_database_url, root), backup_path)
                    identity_backup = (backup_path, IDENTITY_SQLITE_MEMBER)
                elif configured_database_url.startswith(("postgresql", "postgres://")):
                    backup_path = Path(temp_dir) / "identity.pg_dump"
                    _backup_postgres(configured_database_url, backup_path)
                    identity_backup = (backup_path, IDENTITY_POSTGRES_MEMBER)
                else:
                    raise RuntimeError("unsupported AI_CADDIE_DATABASE_URL; identity backup would be incomplete")
            else:
                sqlite_source = root / IDENTITY_SQLITE_MEMBER
                if _is_regular_file(sqlite_source):
                    backup_path = Path(temp_dir) / "identity.db"
                    _backup_sqlite(sqlite_source, backup_path)
                    identity_backup = (backup_path, IDENTITY_SQLITE_MEMBER)

            with tarfile.open(output, "w:gz") as archive:
                for relative in files:
                    archive.add(root / relative, arcname=relative.as_posix(), recursive=False)
                if identity_backup is not None:
                    source, member = identity_backup
                    archive.add(source, arcname=member.as_posix(), recursive=False)
    except Exception:
        output.unlink(missing_ok=True)
        raise

    try:
        audit = audit_snapshot(output)
    except Exception:
        output.unlink(missing_ok=True)
        raise

    included_roots = {relative.parts[0] for relative in files if relative.parts}
    if audit["identityBackup"] != "none":
        included_roots.add("data")
    return {
        "schema": "ai-caddie-export-snapshot-v1",
        "createdAt": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "snapshotPath": _display_path(output),
        "sizeBytes": output.stat().st_size,
        "fileCount": audit["fileCount"],
        "includedRoots": sorted(included_roots),
        "identityBackup": audit["identityBackup"],
        "secretFree": audit["secretFree"],
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
