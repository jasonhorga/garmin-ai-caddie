#!/usr/bin/env bash
# Mandatory post-switch gate for the homeserver API deployment.
#
# The API container must already be switched to the production host port and
# healthy. This script makes the deployment incomplete unless the matching
# immutable sync image is built immediately afterwards.
set -euo pipefail

script_dir="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(CDPATH= cd -- "$script_dir/.." && pwd)"
api_port="${AICADDIE_API_PORT:-39055}"
api_container="${AICADDIE_API_CONTAINER:-}"

if [[ -z "$api_container" ]]; then
  mapfile -t matches < <(
    docker ps --filter "publish=${api_port}" --format '{{.Names}}' \
      | awk '/^aicaddie-release-/'
  )
  if [[ "${#matches[@]}" -ne 1 ]]; then
    echo "error: expected exactly one release container on port ${api_port}; set AICADDIE_API_CONTAINER explicitly" >&2
    printf '  %s\n' "${matches[@]:-<none>}" >&2
    exit 1
  fi
  api_container="${matches[0]}"
fi

if ! docker inspect "$api_container" >/dev/null 2>&1; then
  echo "error: API container '$api_container' does not exist" >&2
  exit 1
fi
if [[ "$(docker inspect --format '{{.State.Running}}' "$api_container")" != "true" ]]; then
  echo "error: API container '$api_container' is not running" >&2
  exit 1
fi

health_url="${AICADDIE_API_HEALTH_URL:-http://127.0.0.1:${api_port}/api/v2/health}"
if ! curl --fail --silent --show-error --max-time "${AICADDIE_API_HEALTH_TIMEOUT_SECONDS:-15}" "$health_url" >/dev/null; then
  echo "error: API health check failed for '$api_container' at ${health_url}" >&2
  exit 1
fi

source_revision="$(docker inspect --format '{{index .Config.Labels "ai.caddie.source-revision"}}' "$api_container")"
sync_image="aicaddie-sync:${source_revision}"
if [[ "${AICADDIE_DEPLOY_GATE_CHECK_ONLY:-0}" == "1" ]]; then
  sync_revision="$(docker image inspect --format '{{index .Config.Labels "ai.caddie.source-revision"}}' "$sync_image" 2>/dev/null || true)"
  if [[ "$sync_revision" != "$source_revision" ]]; then
    echo "error: check-only gate found ${sync_image} revision '${sync_revision:-unknown}', expected '$source_revision'" >&2
    exit 1
  fi
  echo "deployment gate check complete: ${api_container} is healthy and ${sync_image} matches"
  exit 0
fi

# Do not allow a caller's candidate API_IMAGE override to bypass the active
# container binding in this post-deploy path.
env -u API_IMAGE \
  AICADDIE_API_CONTAINER="$api_container" \
  AICADDIE_API_PORT="$api_port" \
  bash "$repo_root/ops/build_sync_image.sh"

if ! docker image inspect "$sync_image" >/dev/null 2>&1; then
  echo "error: deployment gate could not find ${sync_image}" >&2
  exit 1
fi

echo "deployment complete: ${api_container} is healthy and ${sync_image} is ready"
