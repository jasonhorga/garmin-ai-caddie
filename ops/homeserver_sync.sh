#!/usr/bin/env bash
# Homeserver Garmin sync entrypoint.
#
# This is intentionally a one-shot container runner. It binds the sync image
# to the currently active production API revision before touching the shared
# data volume, and emits a deduplicated alert when that contract is broken.
set -uo pipefail

LOG="${AICADDIE_SYNC_LOG:-$HOME/aicaddie-sync.log}"
LOCK="${AICADDIE_SYNC_LOCK:-/tmp/aicaddie-sync.lock}"
ALERT_STATE="${AICADDIE_SYNC_ALERT_STATE:-$HOME/.cache/aicaddie-sync-alert.state}"
ALERT_WEBHOOK_URL="${AICADDIE_SYNC_ALERT_WEBHOOK_URL:-}"
ALERT_COOLDOWN_SECONDS="${AICADDIE_SYNC_ALERT_COOLDOWN_SECONDS:-21600}"
API_CONTAINER="${AICADDIE_API_CONTAINER:-}"
API_PORT="${AICADDIE_API_PORT:-39055}"
SYNC_IMAGE="${AICADDIE_SYNC_IMAGE:-}"
PRIVATE_VOLUME="${AICADDIE_PRIVATE_VOLUME:-garmin-ai-caddie_ai-caddie-private}"
PLAYWRIGHT_VOLUME="${AICADDIE_PLAYWRIGHT_VOLUME:-aicaddie-pw-profile}"

if ! [[ "$ALERT_COOLDOWN_SECONDS" =~ ^[0-9]+$ ]]; then
  ALERT_COOLDOWN_SECONDS=21600
fi

mkdir -p "$(dirname "$LOG")" "$(dirname "$ALERT_STATE")"
exec 9>"$LOCK"
if ! flock -n 9; then
  printf '%s skip: another sync holds the lock\n' "$(date -Is)" >>"$LOG"
  exit 0
fi

if docker info >/dev/null 2>&1; then
  DOCKER=(docker)
else
  DOCKER=(sudo docker)
fi

docker_call() {
  "${DOCKER[@]}" "$@"
}

log_line() {
  printf '%s %s\n' "$(date -Is)" "$1" >>"$LOG"
}

alert_event() {
  local event="$1"
  local message="$2"
  local now fingerprint previous_event previous_fingerprint previous_time
  now="$(date +%s)"
  fingerprint="$(printf '%s\n' "$event:$message" | sha256sum | awk '{print $1}')"
  previous_event=""
  previous_fingerprint=""
  previous_time="0"
  if [[ -f "$ALERT_STATE" ]]; then
    IFS='|' read -r previous_event previous_fingerprint previous_time <"$ALERT_STATE" || true
  fi

  # Always leave a syslog trail; rate-limit only external/user-facing alerts.
  logger -t aicaddie-sync -- "$message" 2>/dev/null || true
  if [[ "$event" == "sync_failed" && "$previous_event" == "$event" \
      && "$previous_fingerprint" == "$fingerprint" \
      && "$previous_time" =~ ^[0-9]+$ \
      && $((now - previous_time)) -lt ${ALERT_COOLDOWN_SECONDS:-21600} ]]; then
    return 0
  fi

  if [[ -n "$ALERT_WEBHOOK_URL" ]]; then
    payload="$(AICADDIE_ALERT_EVENT="$event" AICADDIE_ALERT_MESSAGE="$message" \
      python3 -c 'import json, os; print(json.dumps({"event": os.environ["AICADDIE_ALERT_EVENT"], "message": os.environ["AICADDIE_ALERT_MESSAGE"]}))' \
      2>/dev/null || true)"
    if [[ -n "$payload" ]]; then
      curl --fail --silent --show-error --max-time 10 \
        -H 'Content-Type: application/json' \
        --data "$payload" "$ALERT_WEBHOOK_URL" >/dev/null 2>&1 || true
    fi
  fi

  if command -v notify-send >/dev/null 2>&1 \
      && [[ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]] \
      && [[ -n "${DBUS_SESSION_BUS_ADDRESS:-}" ]]; then
    timeout 10 notify-send -u critical "Garmin AI Caddie sync" "$message" >/dev/null 2>&1 || true
  fi

  printf '%s|%s|%s\n' "$event" "$fingerprint" "$now" >"$ALERT_STATE"
}

fail_sync() {
  local reason="$1"
  log_line "SYNC FAILED ($reason)"
  alert_event sync_failed "$reason"
  tail -n 3000 "$LOG" >"$LOG.tmp" && mv "$LOG.tmp" "$LOG"
  exit 1
}

log_line "sync start"

if [[ -z "$API_CONTAINER" ]]; then
  mapfile -t port_matches < <(
    docker_call ps --filter "publish=${API_PORT}" --format '{{.Names}}' \
      | awk '/^aicaddie-release-/'
  )
  if [[ "${#port_matches[@]}" -eq 1 ]]; then
    API_CONTAINER="${port_matches[0]}"
  elif [[ "${#port_matches[@]}" -gt 1 ]]; then
    fail_sync "multiple release containers publish port ${API_PORT}; set AICADDIE_API_CONTAINER"
  else
    mapfile -t release_matches < <(
      docker_call ps --format '{{.Names}}' | awk '/^aicaddie-release-/'
    )
    if [[ "${#release_matches[@]}" -eq 1 ]]; then
      API_CONTAINER="${release_matches[0]}"
    elif [[ "${#release_matches[@]}" -eq 0 ]]; then
      fail_sync "no active aicaddie-release API container"
    else
      fail_sync "multiple release containers and none publishes port ${API_PORT}; set AICADDIE_API_CONTAINER"
    fi
  fi
fi

if ! docker_call inspect "$API_CONTAINER" >/dev/null 2>&1; then
  fail_sync "API container $API_CONTAINER does not exist"
fi
if [[ "$(docker_call inspect --format '{{.State.Running}}' "$API_CONTAINER")" != "true" ]]; then
  fail_sync "API container $API_CONTAINER is not running"
fi

API_SOURCE_REVISION="$(docker_call inspect --format '{{index .Config.Labels "ai.caddie.source-revision"}}' "$API_CONTAINER" 2>/dev/null || true)"
if ! [[ "$API_SOURCE_REVISION" =~ ^[0-9a-f]{40}$ ]]; then
  fail_sync "API container $API_CONTAINER has no valid source revision"
fi

if [[ -z "$SYNC_IMAGE" ]]; then
  SYNC_IMAGE="aicaddie-sync:${API_SOURCE_REVISION}"
fi
if ! docker_call image inspect "$SYNC_IMAGE" >/dev/null 2>&1; then
  fail_sync "$SYNC_IMAGE is missing; API revision=$API_SOURCE_REVISION; refusing stale/latest image"
fi
SYNC_SOURCE_REVISION="$(docker_call image inspect --format '{{index .Config.Labels "ai.caddie.source-revision"}}' "$SYNC_IMAGE" 2>/dev/null || true)"
if [[ "$SYNC_SOURCE_REVISION" != "$API_SOURCE_REVISION" ]]; then
  fail_sync "sync revision=${SYNC_SOURCE_REVISION:-unknown} does not match API revision=$API_SOURCE_REVISION"
fi
log_line "verified API revision=$API_SOURCE_REVISION sync_image=$SYNC_IMAGE"

if [[ "${AICADDIE_SYNC_CHECK_ONLY:-0}" == "1" ]]; then
  log_line "sync contract ok (check-only)"
  exit 0
fi

INNER='
set -e
private_root=/var/lib/ai-caddie
mkdir -p "$private_root/data" "$private_root/.garmin_tokens" "$private_root/output" "$private_root/logs" "$private_root/backups"
for name in data .garmin_tokens output logs backups; do
  rm -rf "/app/$name"
  ln -s "$private_root/$name" "/app/$name"
done
if [ -f "$private_root/clubs.json" ]; then rm -f /app/clubs.json; ln -s "$private_root/clubs.json" /app/clubs.json; fi
exec xvfb-run -a uv run --frozen --group auth python -m ai_caddie.pipeline --shots --geometry-limit 0
'

docker_call rm -f aicaddie-sync >/dev/null 2>&1 || true
if docker_call run --rm --init --name aicaddie-sync \
    --pull=never \
    -v "${PRIVATE_VOLUME}:/var/lib/ai-caddie" \
    -v "${PLAYWRIGHT_VOLUME}:/root/.cache/garmin_pw_profile" \
    -e AI_CADDIE_PRIVATE_ROOT=/var/lib/ai-caddie \
    -e AI_CADDIE_AUTH_REFRESH=playwright \
    -e AI_CADDIE_DATA_MODE=local_or_fixture \
    "$SYNC_IMAGE" sh -c "$INNER" >>"$LOG" 2>&1; then
  log_line "sync ok"
  if [[ -f "$ALERT_STATE" ]]; then
    alert_event sync_recovered "Garmin sync recovered with API revision=$API_SOURCE_REVISION"
    rm -f "$ALERT_STATE"
  fi
  log_line "done"
  rc=0
else
  rc=$?
  log_line "SYNC FAILED (exit $rc) - see lines above"
  alert_event sync_failed "sync container exited $rc for API revision=$API_SOURCE_REVISION"
fi

tail -n 3000 "$LOG" >"$LOG.tmp" && mv "$LOG.tmp" "$LOG"
exit "$rc"
