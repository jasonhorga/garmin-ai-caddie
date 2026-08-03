#!/usr/bin/env bash
set -uo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
RETRY="$ROOT/.github/scripts/retry-transient-command.sh"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

if [[ ! -x "$RETRY" ]]; then
  echo "FAIL: retry helper is missing or not executable: $RETRY" >&2
  exit 1
fi

cat > "$TMP/transient-then-success.sh" <<'SCRIPT'
#!/usr/bin/env bash
set -u
counter=$1
attempt=0
if [[ -f "$counter" ]]; then
  attempt=$(cat "$counter")
fi
attempt=$((attempt + 1))
printf '%s\n' "$attempt" > "$counter"
if [[ "$attempt" -eq 1 ]]; then
  echo 'NSURLErrorDomain Code=-1200; SSL error -9816' >&2
  exit 65
fi
echo 'success'
SCRIPT
chmod +x "$TMP/transient-then-success.sh"

RETRY_DELAY_SECONDS=0 RETRY_MAX_ATTEMPTS=3 \
  "$RETRY" "$TMP/transient" "$TMP/transient-then-success.sh" "$TMP/transient-count"
[[ "$(cat "$TMP/transient-count")" == "2" ]]

cat > "$TMP/assertion-failure.sh" <<'SCRIPT'
#!/usr/bin/env bash
set -u
counter=$1
attempt=0
if [[ -f "$counter" ]]; then
  attempt=$(cat "$counter")
fi
printf '%s\n' "$((attempt + 1))" > "$counter"
echo 'XCTAssertTrue failed - visible control moved' >&2
exit 65
SCRIPT
chmod +x "$TMP/assertion-failure.sh"

set +e
RETRY_DELAY_SECONDS=0 RETRY_MAX_ATTEMPTS=3 \
  "$RETRY" "$TMP/nontransient" "$TMP/assertion-failure.sh" "$TMP/nontransient-count"
status=$?
set -e

[[ "$status" -eq 65 ]]
[[ "$(cat "$TMP/nontransient-count")" == "1" ]]

cat > "$TMP/assertion-after-transient-log.sh" <<'SCRIPT'
#!/usr/bin/env bash
set -u
counter=$1
attempt=0
if [[ -f "$counter" ]]; then
  attempt=$(cat "$counter")
fi
printf '%s\n' "$((attempt + 1))" > "$counter"
echo 'HTTP 503 was observed earlier but recovered' >&2
echo 'XCTAssertTrue failed - focused caddie surface is missing' >&2
exit 65
SCRIPT
chmod +x "$TMP/assertion-after-transient-log.sh"

set +e
RETRY_DELAY_SECONDS=0 RETRY_MAX_ATTEMPTS=3 \
  "$RETRY" "$TMP/assertion-after-transient" \
  "$TMP/assertion-after-transient-log.sh" "$TMP/assertion-after-transient-count"
mixed_status=$?
set -e

[[ "$mixed_status" -eq 65 ]]
[[ "$(cat "$TMP/assertion-after-transient-count")" == "1" ]]
echo 'PASS: transient failures retry; product assertions fail immediately'
