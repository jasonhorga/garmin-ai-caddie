#!/usr/bin/env bash
set -euo pipefail

OUT_DIR="${1:-backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
SNAPSHOT="${OUT_DIR}/ai-caddie-snapshot-${STAMP}.tar.gz"
MANIFEST="${OUT_DIR}/latest.json"

mkdir -p "${OUT_DIR}"
uv run python ops/export_snapshot.py --source-root . --output "${SNAPSHOT}"
uv run python - "${SNAPSHOT}" "${STAMP}" "${MANIFEST}" <<'PY'
from __future__ import annotations

import json
import hashlib
from pathlib import Path
import sys

snapshot = Path(sys.argv[1])
created_at = sys.argv[2]
manifest = Path(sys.argv[3])

digest = hashlib.sha256()
with snapshot.open("rb") as handle:
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(chunk)

payload = {
    "schema": "ai-caddie-backup-manifest-v1",
    "snapshot": snapshot.as_posix(),
    "snapshotPath": snapshot.as_posix(),
    "createdAt": created_at,
    "sizeBytes": snapshot.stat().st_size,
    "sha256": digest.hexdigest(),
    "secretFree": True,
}
manifest.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
printf '%s\n' "${SNAPSHOT}"
