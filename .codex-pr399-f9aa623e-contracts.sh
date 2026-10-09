#!/usr/bin/env bash
set -euo pipefail
snapshot=/dev/shm/garmin-ai-caddie-pr399-f9aa623e-20261009
evidence=/home/jason/garmin-ai-caddie-data/operations/pr399-f9aa623e-20261009
test ! -e "$snapshot"
test -d "$evidence" || mkdir -p "$evidence"
gh api repos/jasonhorga/garmin-ai-caddie/tarball/f9aa623e8415e1dc36ff9bba1f1c960affaad1bd > "$evidence/source.tar.gz"
mkdir -p "$snapshot"
tar -xzf "$evidence/source.tar.gz" --strip-components=1 --no-same-owner --no-same-permissions \
  --exclude='*/.git' --exclude='*/.venv' --exclude='*/node_modules' --exclude='*/.env*' -C "$snapshot"
test -f "$snapshot/tests/test_mobile_contracts.py"
mkdir -p "$snapshot/data"
docker run --rm --network none --read-only \
  --name codex-pr399-f9aa623e-contracts-20261009 \
  --mount type=bind,source="$snapshot",target=/review,readonly \
  --tmpfs /tmp:rw,nosuid,nodev --tmpfs /review/data:rw,nosuid,nodev \
  --workdir /review -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/review/src:/review \
  -e AI_CADDIE_DATA_DIR=/review/data \
  garmin-ai-caddie-api:3614bf6f3805479f8d13de65eeec4f0ad7871f22-candidate-20261006 \
  /app/.venv/bin/python -m unittest discover -s tests -p test_mobile_contracts.py \
  > "$evidence/contracts.log" 2>&1
tail -n 5 "$evidence/contracts.log"
du -sb "$snapshot"
sha256sum "$evidence/source.tar.gz"
