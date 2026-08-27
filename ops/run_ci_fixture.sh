#!/usr/bin/env bash
set -euo pipefail

# This entry point is intentionally opt-in. It can only run in CI or when a developer
# explicitly opts into the debug fixture profile; it never falls back to local/production data.
if [[ "${CI:-}" != "true" && "${AI_CADDIE_DEBUG_FIXTURE:-}" != "1" ]]; then
  echo "CI fixture mode requires CI=true or AI_CADDIE_DEBUG_FIXTURE=1" >&2
  exit 64
fi
if [[ -z "${AI_CADDIE_ADMIN_TOKEN:-}" ]]; then
  echo "AI_CADDIE_ADMIN_TOKEN is required for the private CI fixture" >&2
  exit 64
fi

export AI_CADDIE_DATA_MODE=fixture
export AI_CADDIE_SECURITY_PROFILE=private
export AI_CADDIE_BUILD_REVISION="${AI_CADDIE_BUILD_REVISION:-ci-fixture-20260827-v1}"
export AI_CADDIE_FIXTURE_MODE=1

fixture_host="${AI_CADDIE_FIXTURE_HOST:-127.0.0.1}"
case "$fixture_host" in
  127.0.0.1|localhost|::1) ;;
  *) echo "fixture host must be loopback" >&2; exit 64 ;;
esac

exec uv run uvicorn server_v2.main:app \
  --host "$fixture_host" \
  --port "${AI_CADDIE_FIXTURE_PORT:-9000}"
