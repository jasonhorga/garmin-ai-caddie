#!/usr/bin/env bash
set -euo pipefail

OUT_DIR="${1:-backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
SNAPSHOT="${OUT_DIR}/ai-caddie-snapshot-${STAMP}.tar.gz"

mkdir -p "${OUT_DIR}"
uv run python ops/export_snapshot.py --source-root . --output "${SNAPSHOT}"
printf '%s\n' "${SNAPSHOT}"
