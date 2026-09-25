#!/usr/bin/env bash
# Build the Garmin sync image from the exact API image that is deployed.
#
# The cron job resolves the active API container's immutable
# `ai.caddie.source-revision` label and accepts only
# `aicaddie-sync:<same-full-SHA>`. Keeping that contract here prevents a
# successful-looking `:latest` build from being rejected at the next run.
# The API image must already be built/deployed and labelled; this script only
# adds the headed-Chromium (xvfb + Playwright) layer.
#
# Usage on the homeserver:
#   API_IMAGE=garmin-ai-caddie-api:<full-SHA> bash ops/build_sync_image.sh
#   SYNC_IMAGE_TAG=verify API_IMAGE=... bash ops/build_sync_image.sh
#
# A custom tag is useful for inspection, but the canonical full-SHA tag is
# always created as well. Set PUBLISH_LATEST=1 only when a compatibility alias
# is deliberately wanted; cron never relies on that moving alias.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

# Prefer the image used by the production API container. An explicit
# API_IMAGE is required when building a candidate before it is started; there
# is intentionally no silent fallback to a moving `:latest` tag. When more
# than one release container is running, the production host port (or an
# explicit container name) is required so a review candidate cannot silently
# become the sync source.
API_IMAGE="${API_IMAGE:-}"
if [[ -z "$API_IMAGE" ]]; then
  API_CONTAINER="${AICADDIE_API_CONTAINER:-}"
  if [[ -z "$API_CONTAINER" ]]; then
    API_PORT="${AICADDIE_API_PORT:-39055}"
    mapfile -t port_matches < <(
      docker ps --filter "publish=${API_PORT}" --format '{{.Names}}' \
        | awk '/^aicaddie-release-/'
    )
    if [[ "${#port_matches[@]}" -eq 1 ]]; then
      API_CONTAINER="${port_matches[0]}"
    elif [[ "${#port_matches[@]}" -gt 1 ]]; then
      echo "error: multiple release containers publish port ${API_PORT}; set AICADDIE_API_CONTAINER explicitly" >&2
      printf '  %s\n' "${port_matches[@]}" >&2
      exit 1
    else
      mapfile -t release_matches < <(
        docker ps --format '{{.Names}}' | awk '/^aicaddie-release-/'
      )
      if [[ "${#release_matches[@]}" -eq 1 ]]; then
        API_CONTAINER="${release_matches[0]}"
      elif [[ "${#release_matches[@]}" -eq 0 ]]; then
        echo "error: no active API container found; set API_IMAGE or AICADDIE_API_CONTAINER" >&2
        exit 1
      else
        echo "error: multiple release containers are running and none publishes port ${API_PORT}; set AICADDIE_API_CONTAINER explicitly" >&2
        printf '  %s\n' "${release_matches[@]}" >&2
        exit 1
      fi
    fi
  fi
  if [[ -n "$API_CONTAINER" ]]; then
    if ! docker inspect "$API_CONTAINER" >/dev/null 2>&1; then
      echo "error: API container '$API_CONTAINER' does not exist" >&2
      exit 1
    fi
    if [[ "$(docker inspect --format '{{.State.Running}}' "$API_CONTAINER")" != "true" ]]; then
      echo "error: API container '$API_CONTAINER' is not running" >&2
      exit 1
    fi
    API_IMAGE="$(docker inspect --format '{{.Config.Image}}' "$API_CONTAINER" 2>/dev/null || true)"
  fi
fi

if [[ -z "$API_IMAGE" ]]; then
  echo "error: no active API container found; set API_IMAGE or AICADDIE_API_CONTAINER explicitly" >&2
  exit 1
fi

if ! docker image inspect "$API_IMAGE" >/dev/null 2>&1; then
  echo "error: API image '$API_IMAGE' does not exist locally; build/deploy the labelled API image first" >&2
  exit 1
fi

API_SOURCE_REVISION="$(docker image inspect --format '{{index .Config.Labels "ai.caddie.source-revision"}}' "$API_IMAGE" 2>/dev/null || true)"
if ! [[ "$API_SOURCE_REVISION" =~ ^[0-9a-f]{40}$ ]]; then
  echo "error: API image '$API_IMAGE' has no valid ai.caddie.source-revision label; refusing an unbound sync image" >&2
  exit 1
fi

if [[ -n "${API_CONTAINER:-}" ]]; then
  CONTAINER_SOURCE_REVISION="$(docker inspect --format '{{index .Config.Labels "ai.caddie.source-revision"}}' "$API_CONTAINER" 2>/dev/null || true)"
  if [[ "$CONTAINER_SOURCE_REVISION" != "$API_SOURCE_REVISION" ]]; then
    echo "error: API container '$API_CONTAINER' revision '${CONTAINER_SOURCE_REVISION:-unknown}' does not match image '$API_IMAGE' revision '$API_SOURCE_REVISION'" >&2
    exit 1
  fi
fi

SYNC_IMAGE_TAG="${SYNC_IMAGE_TAG:-$API_SOURCE_REVISION}"
SYNC_TAG="aicaddie-sync:${SYNC_IMAGE_TAG}"
CANONICAL_TAG="aicaddie-sync:${API_SOURCE_REVISION}"

echo "building sync toolchain from ${API_IMAGE} (revision=${API_SOURCE_REVISION}) -> ${SYNC_TAG} ..."
docker build \
  -f Dockerfile.sync \
  --build-arg "API_IMAGE=${API_IMAGE}" \
  --label "ai.caddie.source-revision=${API_SOURCE_REVISION}" \
  -t "${SYNC_TAG}" .

# A verification tag must not leave the cron-required tag missing.
if [[ "$SYNC_TAG" != "$CANONICAL_TAG" ]]; then
  docker tag "$SYNC_TAG" "$CANONICAL_TAG"
fi

if [[ "${PUBLISH_LATEST:-0}" == "1" ]]; then
  docker tag "$CANONICAL_TAG" aicaddie-sync:latest
fi

SYNC_SOURCE_REVISION="$(docker image inspect --format '{{index .Config.Labels "ai.caddie.source-revision"}}' "$CANONICAL_TAG" 2>/dev/null || true)"
if [[ "$SYNC_SOURCE_REVISION" != "$API_SOURCE_REVISION" ]]; then
  echo "error: built sync image revision '${SYNC_SOURCE_REVISION:-unknown}' does not match API revision '$API_SOURCE_REVISION'" >&2
  exit 1
fi

echo "done: ${CANONICAL_TAG} is bound to API revision ${API_SOURCE_REVISION}"
