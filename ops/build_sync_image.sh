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

# Prefer the image used by the active homeserver API container. An explicit
# API_IMAGE is required when building a candidate before it is started; there
# is intentionally no silent fallback to a moving `:latest` tag.
API_IMAGE="${API_IMAGE:-}"
if [[ -z "$API_IMAGE" ]]; then
  API_CONTAINER="${AICADDIE_API_CONTAINER:-}"
  if [[ -z "$API_CONTAINER" ]]; then
    API_CONTAINER="$(docker ps --format '{{.Names}}' | awk '/^aicaddie-release-/{print; exit}')"
  fi
  if [[ -n "$API_CONTAINER" ]]; then
    API_IMAGE="$(docker inspect --format '{{.Config.Image}}' "$API_CONTAINER" 2>/dev/null || true)"
  fi
fi

if [[ -z "$API_IMAGE" ]]; then
  echo "error: no active API container found; set API_IMAGE to the labelled candidate image explicitly" >&2
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
