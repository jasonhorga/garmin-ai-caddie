#!/usr/bin/env bash
set -euo pipefail
run=38267523735
evidence=/home/jason/garmin-ai-caddie-data/operations/pr422-prototype-clock-20261012
destination="$evidence/runtime$run"
test ! -e "$destination"
mkdir "$destination"
gh api "repos/jasonhorga/garmin-ai-caddie/actions/runs/$run" > "$destination/run.json"
test "$(jq -r .head_sha "$destination/run.json")" = c345ae15473fc48826f49cb1785026a91d0ca78f
test "$(jq -r .status "$destination/run.json")" = completed
gh api "repos/jasonhorga/garmin-ai-caddie/actions/runs/$run/artifacts" > "$destination/artifacts.json"
gh run download "$run" --repo jasonhorga/garmin-ai-caddie --pattern 'watch-audit-*' --dir "$destination/artifacts"
docker run --rm --network none --name garmin-pr422-clock-runtime-analysis-20261012 \
  --mount "type=bind,src=$evidence,dst=/evidence" \
  --entrypoint /app/.venv/bin/python \
  garmin-ai-caddie-api:cbc17f4e76f085229c3bdb3c74a5067951b217a6-candidate-20261010 \
  /evidence/.codex-pr422-analyze.py "/evidence/runtime$run" \
  c345ae15473fc48826f49cb1785026a91d0ca78f \
  9e03df3072248dd03b0e3915ca413d5c185edaaa 4 74 \
  > "$destination/analysis-summary.log" 2>&1
test -z "$(docker ps -a --filter name=^garmin-pr422-clock-runtime-analysis-20261012$ --format '{{.ID}}')"
printf 'collection=complete container=absent analysis=%s\n' "$destination/analysis.json"
