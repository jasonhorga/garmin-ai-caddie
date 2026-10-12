#!/usr/bin/env bash
set -euo pipefail
evidence=/home/jason/garmin-ai-caddie-data/operations/pr422-prototype-clock-20261012
destination="$evidence/native38251072892"
test ! -e "$destination"
mkdir "$destination"
gh api repos/jasonhorga/garmin-ai-caddie/actions/runs/38251072892 > "$destination/run.json"
test "$(jq -r .head_sha "$destination/run.json")" = 9e03df3072248dd03b0e3915ca413d5c185edaaa
test "$(jq -r .conclusion "$destination/run.json")" = success
gh api repos/jasonhorga/garmin-ai-caddie/actions/runs/38251072892/artifacts > "$destination/artifacts.json"
gh run download 38251072892 --repo jasonhorga/garmin-ai-caddie --pattern watch-snapshots --dir "$destination"
docker run --rm --network none --name garmin-pr422-clock-native-sheets-20261012 \
  --mount "type=bind,src=$evidence,dst=/evidence" \
  --entrypoint /bin/sh \
  garmin-ai-caddie-api:cbc17f4e76f085229c3bdb3c74a5067951b217a6-candidate-20261010 \
  -c '/app/.venv/bin/python /evidence/.codex-pr422-native-sheets.py /evidence/native38251072892 9e03df3072248dd03b0e3915ca413d5c185edaaa 38251072892 && /app/.venv/bin/python /evidence/watch_simulator_audit.py physical --input /evidence/native38251072892/prototype-comparisons/faces --output /evidence/native38251072892/prototype-physical' \
  > "$destination/comparisons.log" 2>&1
cat "$destination/comparisons.log"
test -z "$(docker ps -a --filter name=^garmin-pr422-clock-native-sheets-20261012$ --format '{{.ID}}')"
printf 'cleanup=complete container=absent source_snapshot=none outputs=%s\n' "$destination"
