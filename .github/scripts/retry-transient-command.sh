#!/usr/bin/env bash
set -uo pipefail

if [[ "$#" -lt 2 ]]; then
  echo "usage: $0 <log-prefix> <command> [args...]" >&2
  exit 2
fi

log_prefix=$1
shift
delay=${RETRY_DELAY_SECONDS:-60}
max_attempts=${RETRY_MAX_ATTEMPTS:-0}
attempt=0

while true; do
  attempt=$((attempt + 1))
  log_file="${log_prefix}.attempt-${attempt}.log"

  set +e
  "$@" 2>&1 | tee "$log_file"
  status=${PIPESTATUS[0]}
  set -e

  if [[ "$status" -eq 0 ]]; then
    exit 0
  fi

  # A product/UI assertion is deterministic evidence for this attempt. A recovered 429/503 may
  # still appear earlier in the same long Xcode log; it must not cause the entire simulator journey
  # to restart after a later layout or behavior failure.
  if grep -Eqi \
    'XCTAssert[^[:cntrl:]]*failed|Test Case[^[:cntrl:]]*failed|Testing failed:|BUILD FAILED' \
    "$log_file"; then
    exit "$status"
  fi

  if ! grep -Eqi \
    'NSURLErrorDomain Code=-1200|error code: -1200|SSL[^[:cntrl:]]*-9816|HTTP[^[:cntrl:]]*(429|503)|RESOURCE_EXHAUSTED|UNAVAILABLE|rate.?limit|service unavailable' \
    "$log_file"; then
    exit "$status"
  fi

  if [[ "$max_attempts" -gt 0 && "$attempt" -ge "$max_attempts" ]]; then
    echo "transient failure persisted through $attempt attempts" >&2
    exit "$status"
  fi

  echo "explicit transient failure on attempt $attempt; retrying in ${delay}s" >&2
  sleep "$delay"
done
