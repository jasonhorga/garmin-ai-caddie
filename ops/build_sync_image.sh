#!/usr/bin/env bash
# Rebuild the Garmin sync image (aicaddie-sync:latest) from the current checkout.
#
# The sync image = the API image + the headed-Chromium cookie-minting toolchain
# (xvfb + Playwright), see Dockerfile.sync. Because it is layered ON TOP of
# garmin-ai-caddie-api, the API image must be rebuilt first so the sync pipeline
# always matches the deployed API code (notably fetch.fetch_clubs, which refreshes
# the player's real club bag every sync).
#
# Run this on the homeserver after ANY change to the data pipeline / ai_caddie
# code that the cron sync executes — right alongside `docker compose build api`.
#
# Usage:
#   bash ops/build_sync_image.sh           # build + tag aicaddie-sync:latest
#   SYNC_IMAGE_TAG=next bash ops/...        # build a throwaway tag to verify first
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

API_IMAGE="${API_IMAGE:-garmin-ai-caddie-api:latest}"
SYNC_TAG="aicaddie-sync:${SYNC_IMAGE_TAG:-latest}"

echo "[1/2] building API base image (${API_IMAGE}) ..."
docker compose build api

echo "[2/2] layering sync toolchain -> ${SYNC_TAG} ..."
docker build -f Dockerfile.sync --build-arg "API_IMAGE=${API_IMAGE}" -t "${SYNC_TAG}" .

echo "done: ${SYNC_TAG} now tracks $(git rev-parse --short HEAD 2>/dev/null || echo '(unknown rev)')"
