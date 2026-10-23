#!/usr/bin/env bash
# Build the Garmin sync application image bound to the exact API revision that
# is deployed. The headed Chromium dependencies come from SYNC_DEPS_IMAGE.
#
# The cron job resolves the active API container's immutable
# `ai.caddie.source-revision` label and accepts only
# `aicaddie-sync:<same-full-SHA>`. Keeping that contract here prevents a
# successful-looking `:latest` build from being rejected at the next run.
# The API image must already be built/deployed and labelled; this script checks
# that identity while Dockerfile.sync copies application code from API_IMAGE.
#
# Usage on the homeserver:
#   API_IMAGE=garmin-ai-caddie-api:<full-SHA> bash ops/build_sync_image.sh
#   API_IMAGE=... SYNC_DEPS_IMAGE=aicaddie-sync-deps:<hash> bash ops/build_sync_image.sh
#   SYNC_IMAGE_TAG=verify API_IMAGE=... bash ops/build_sync_image.sh
#
# When SYNC_DEPS_IMAGE is omitted this script finds a local sync-deps image
# whose ai.caddie.api-dependencies-hash matches the API image's dependency
# hash. It prints the exact build command when no matching image exists and
# exits instead of allowing Docker to pull an unlabelled or :local image.
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

API_DEPENDENCIES_HASH="$(docker image inspect --format '{{index .Config.Labels "ai.caddie.dependencies-hash"}}' "$API_IMAGE" 2>/dev/null || true)"
if ! [[ "$API_DEPENDENCIES_HASH" =~ ^[0-9a-f]{64}$ ]]; then
  echo "error: API image '$API_IMAGE' has no ai.caddie.dependencies-hash label; this is a pre-457 image" >&2
  echo "refusing to rebuild sync dependencies; use an existing matching aicaddie-sync:${API_SOURCE_REVISION} image or rebuild the API with the named dependency image first" >&2
  exit 1
fi

SOURCE_REVISION="${SOURCE_REVISION:-}"
TREE_REVISION=""
if git -C . rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  TREE_REVISION="$(git rev-parse HEAD 2>/dev/null || true)"
fi
if [[ -n "$SOURCE_REVISION" ]] && ! [[ "$SOURCE_REVISION" =~ ^[0-9a-f]{40}$ ]]; then
  echo "error: SOURCE_REVISION must be a 40-hex source revision" >&2
  exit 1
fi
if [[ -n "$TREE_REVISION" ]] && ! [[ "$TREE_REVISION" =~ ^[0-9a-f]{40}$ ]]; then
  echo "error: git HEAD is not a 40-hex source revision" >&2
  exit 1
fi
if [[ -n "$SOURCE_REVISION" && -n "$TREE_REVISION" && "$TREE_REVISION" != "$SOURCE_REVISION" ]]; then
  echo "error: SOURCE_REVISION does not match git HEAD" >&2
  exit 1
fi
if [[ -n "$SOURCE_REVISION" && "$SOURCE_REVISION" != "$API_SOURCE_REVISION" ]]; then
  echo "error: SOURCE_REVISION '$SOURCE_REVISION' does not match API image revision '$API_SOURCE_REVISION'" >&2
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

SYNC_DEPS_IMAGE="${SYNC_DEPS_IMAGE:-}"
if [[ -z "$SYNC_DEPS_IMAGE" ]]; then
  mapfile -t sync_dependency_candidates < <(
    docker image ls aicaddie-sync-deps --format '{{.Repository}}:{{.Tag}}' 2>/dev/null || true
  )
  for candidate in "${sync_dependency_candidates[@]}"; do
    candidate_api_hash="$(docker image inspect --format '{{index .Config.Labels "ai.caddie.api-dependencies-hash"}}' "$candidate" 2>/dev/null || true)"
    if [[ "$candidate_api_hash" == "$API_DEPENDENCIES_HASH" ]]; then
      SYNC_DEPS_IMAGE="$candidate"
      break
    fi
  done
  if [[ -z "$SYNC_DEPS_IMAGE" ]]; then
    SYNC_DEPS_HASH="$(python3 -c "from ops.agenthub_deploy import sync_dependency_hash; print(sync_dependency_hash('${API_DEPENDENCIES_HASH}'))")"
    SYNC_DEPS_IMAGE="aicaddie-sync-deps:${SYNC_DEPS_HASH}"
    echo "error: sync dependency image '$SYNC_DEPS_IMAGE' is missing locally" >&2
    echo "build it first with:" >&2
    echo "  docker build -f Dockerfile.sync-deps --build-arg API_IMAGE=garmin-ai-caddie-deps:${API_DEPENDENCIES_HASH} --label ai.caddie.dependencies-hash=${SYNC_DEPS_HASH} --label ai.caddie.api-dependencies-hash=${API_DEPENDENCIES_HASH} -t ${SYNC_DEPS_IMAGE} ." >&2
    exit 1
  fi
fi

SYNC_API_DEPENDENCIES_HASH="$(docker image inspect --format '{{index .Config.Labels "ai.caddie.api-dependencies-hash"}}' "$SYNC_DEPS_IMAGE" 2>/dev/null || true)"
if [[ "$SYNC_API_DEPENDENCIES_HASH" != "$API_DEPENDENCIES_HASH" ]]; then
  echo "error: sync dependency image '$SYNC_DEPS_IMAGE' has api-dependencies-hash '${SYNC_API_DEPENDENCIES_HASH:-missing}', expected '$API_DEPENDENCIES_HASH' from API image '$API_IMAGE'" >&2
  echo "use the existing aicaddie-sync:${API_SOURCE_REVISION} image for this API revision or build a sync dependency image with the matching label" >&2
  exit 1
fi
if ! docker image inspect "$SYNC_DEPS_IMAGE" >/dev/null 2>&1; then
  echo "error: sync dependency image '$SYNC_DEPS_IMAGE' does not exist locally; build the labelled dependency image first" >&2
  exit 1
fi

echo "building sync toolchain from ${API_IMAGE} (revision=${API_SOURCE_REVISION}) -> ${SYNC_TAG} ..."
BUILD_ARGS=()
BUILD_ARGS+=(--build-arg "SYNC_DEPS_IMAGE=${SYNC_DEPS_IMAGE}")
BUILD_ARGS+=(--build-arg "API_IMAGE=${API_IMAGE}")

docker build \
  -f Dockerfile.sync \
  "${BUILD_ARGS[@]}" \
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
