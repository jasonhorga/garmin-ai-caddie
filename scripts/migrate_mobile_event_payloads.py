#!/usr/bin/env python3
"""Bound oversized mobile event decisions in one event-store directory.

The command is deliberately dry-run by default.  ``--apply`` makes one timestamped backup,
rewrites only changed JSON rows, seals/rebuilds the store metadata, and verifies per-round identity
hashes and row counts before returning.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any

from ai_caddie.caddie.mobile_event_store import FileEventStore, bound_mobile_event


def _identity(event: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(event.get("roundId") or ""),
        str(event.get("clientId") or ""),
        str(event.get("eventId") or ""),
    )


def _identity_hash(events: list[dict[str, Any]]) -> str:
    payload = json.dumps(
        [_identity(event) for event in events],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _round_report(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        grouped[str(event.get("roundId") or "")].append(event)
    return {
        round_id: {"rows": len(rows), "identitySha256": _identity_hash(rows)}
        for round_id, rows in sorted(grouped.items())
    }


def migrate(root: Path | str, *, apply: bool = False, timestamp: str | None = None) -> dict[str, Any]:
    root = Path(root).expanduser().resolve(strict=False)
    log = root / "events.jsonl"
    if not log.exists():
        return {"root": str(root), "apply": apply, "changed": 0, "oversized": 0, "bytesBefore": 0, "bytesAfter": 0, "rounds": {}}
    raw = log.read_bytes()
    output: list[bytes] = []
    before_events: list[dict[str, Any]] = []
    after_events: list[dict[str, Any]] = []
    changed = 0
    oversized = 0
    bytes_after = 0
    store = FileEventStore(root)
    for line in raw.splitlines(keepends=True):
        transformed = line
        try:
            row = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            output.append(line)
            bytes_after += len(line)
            continue
        if isinstance(row, dict) and isinstance(row.get("event"), dict):
            event = row["event"]
            before_events.append(event)
            try:
                bounded = bound_mobile_event(store._sanitize_event(event))
            except ValueError:
                bounded = event
            old_size = len(json.dumps(event, ensure_ascii=False, sort_keys=True).encode("utf-8"))
            new_size = len(json.dumps(bounded, ensure_ascii=False, sort_keys=True).encode("utf-8"))
            if old_size > 64 * 1024:
                oversized += 1
            if bounded != event:
                changed += 1
                row = dict(row)
                row["event"] = bounded
                if isinstance(row.get("eventHash"), str):
                    normalized = json.dumps(bounded, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
                    row["eventHash"] = hashlib.sha256(normalized).hexdigest()
                transformed = (json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
            after_events.append(bounded)
            bytes_after += len(transformed)
        else:
            output.append(line)
            bytes_after += len(line)
            continue
        output.append(transformed)

    before_rounds = _round_report(before_events)
    after_rounds = _round_report(after_events)
    if before_rounds != after_rounds:
        raise ValueError("migration_identity_or_row_count_changed")
    report: dict[str, Any] = {
        "root": str(root),
        "apply": apply,
        "changed": changed,
        "oversized": oversized,
        "bytesBefore": len(raw),
        "bytesAfter": bytes_after,
        "rounds": before_rounds,
    }
    if not apply or changed == 0:
        return report

    stamp = timestamp or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup = log.with_name(f"{log.name}.bak-{stamp}")
    if backup.exists():
        raise FileExistsError(backup)
    backup.write_bytes(raw)
    try:
        with tempfile.NamedTemporaryFile("wb", dir=root, prefix="events.migrate-", delete=False) as handle:
            temp_path = Path(handle.name)
            handle.write(b"".join(output))
            handle.flush()
        temp_path.replace(log)
        with store._locked(store.event_lock):
            with log.open("r+b") as handle:
                store._recover_event_log_unlocked(handle=handle)
        store.ensure_round_event_index()
        # Re-read through the production path: every changed row must remain readable and bounded.
        for round_id in before_rounds:
            rows = store.read_rows(round_id)
            if len(rows) != before_rounds[round_id]["rows"]:
                raise ValueError("migration_identity_or_row_count_changed")
    finally:
        if 'temp_path' in locals() and temp_path.exists():
            temp_path.unlink()
    report["backup"] = str(backup)
    report["index"] = str(store.round_index)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="mobile event-store directory")
    parser.add_argument("--apply", action="store_true", help="write a backup and apply the migration")
    args = parser.parse_args()
    print(json.dumps(migrate(args.root, apply=args.apply), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
