#!/usr/bin/env bash
set -euo pipefail
evidence=/home/jason/garmin-ai-caddie-data/operations/pr399-f9aa623e-20261009
test -f "$evidence/source.tar.gz"
mkdir -p "$evidence/native-artifacts"
gh run download 37923571557 --repo jasonhorga/garmin-ai-caddie \
  --name design-snapshots --name watch-snapshots --name native-build-evidence \
  --dir "$evidence/native-artifacts"
gh run view 37923571557 --repo jasonhorga/garmin-ai-caddie --attempt 1 --log \
  > "$evidence/native-run.log"
rg "Test Suite '(AICaddieTests|AICaddieWatchAppTests|All tests)'|Executed [0-9]+ tests|OfflineStorageMaintenanceTests.*(passed|failed)|testRenderSettingsOfflineCourses.*(passed|failed)|Process completed with exit code" \
  "$evidence/native-run.log" | tail -n 40
jq . "$evidence/native-artifacts/native-build-evidence/native_build_evidence.json"
find "$evidence/native-artifacts" -type f -name '*.png' | wc -l
baseline=/home/jason/garmin-ai-caddie-data/operations/pr397-58928fac-20261009/native-artifacts
current="$evidence/native-artifacts"
(
  cd "$baseline"
  find design-snapshots watch-snapshots -type f -name '*.png' -print0 | LC_ALL=C sort -z | xargs -0 sha256sum
) > "$evidence/native-baseline-sha256.txt"
(
  cd "$current"
  find design-snapshots watch-snapshots -type f -name '*.png' -print0 | LC_ALL=C sort -z | xargs -0 sha256sum
) > "$evidence/native-sha256.txt"
awk '
  NR == FNR { old[$2] = $1; oldCount++; next }
  { currentCount++; seen[$2] = 1 }
  !($2 in old) { print "ADDED", $2, $1; added++; next }
  old[$2] != $1 { print "CHANGED", $2, old[$2], $1; changed++; next }
  { same++ }
  END {
    for (name in old) if (!(name in seen)) { print "REMOVED", name, old[name]; removed++ }
    printf "SUMMARY baseline=%d current=%d identical=%d changed=%d added=%d removed=%d\n", oldCount, currentCount, same, changed, added, removed
  }
' "$evidence/native-baseline-sha256.txt" "$evidence/native-sha256.txt" > "$evidence/native-hash-comparison.txt"
cat "$evidence/native-hash-comparison.txt"
