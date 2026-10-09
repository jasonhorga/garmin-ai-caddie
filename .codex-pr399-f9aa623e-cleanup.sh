#!/usr/bin/env bash
set -euo pipefail
snapshot=/dev/shm/garmin-ai-caddie-pr399-f9aa623e-20261009
evidence=/home/jason/garmin-ai-caddie-data/operations/pr399-f9aa623e-20261009
test "$snapshot" = /dev/shm/garmin-ai-caddie-pr399-f9aa623e-20261009
test -d "$snapshot"
test -f "$evidence/review-manifest.md"
test -f "$evidence/source.tar.gz"
exec >"$evidence/cleanup.log" 2>&1
date -u
df -BG /home/jason /dev/shm
du -sb "$snapshot"
sha256sum "$evidence/source.tar.gz"
if docker inspect codex-pr399-f9aa623e-contracts-20261009 >/dev/null 2>&1; then
  printf 'abort: owned contract container still present\n'
  exit 1
fi
set +e
lsof -nP +D "$snapshot"
open_exit=$?
set -e
if (( open_exit != 1 )); then
  printf 'abort: open-file check returned %s\n' "$open_exit"
  exit 1
fi
ps -eo pid,args | awk 'index($0,"garmin-ai-caddie-pr399-f9aa623e-20261009") && !index($0,"awk") {print; found=1} END {exit found ? 1 : 0}'
rm -r -- /dev/shm/garmin-ai-caddie-pr399-f9aa623e-20261009
test ! -e /dev/shm/garmin-ai-caddie-pr399-f9aa623e-20261009
df -BG /home/jason /dev/shm
docker inspect --format '{{.Name}} running={{.State.Running}} status={{.State.Status}}' aicaddie-release-3614bf6f-production-20261008
printf 'snapshot=removed container=absent source_tar=retained evidence=retained\n'
