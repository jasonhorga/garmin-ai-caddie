#!/usr/bin/env sh
set -eu

if [ -n "${AI_CADDIE_PRIVATE_ROOT:-}" ]; then
  private_root="${AI_CADDIE_PRIVATE_ROOT}"
  mkdir -p "$private_root/data" "$private_root/.garmin_tokens" "$private_root/output" "$private_root/logs" "$private_root/backups"
  for name in data .garmin_tokens output logs backups; do
    rm -rf "/app/$name"
    ln -s "$private_root/$name" "/app/$name"
  done
  if [ -f "$private_root/clubs.json" ]; then
    rm -f /app/clubs.json
    ln -s "$private_root/clubs.json" /app/clubs.json
  fi
fi

exec uv run --frozen uvicorn server_v2.main:app --host 0.0.0.0 --port "${PORT:-9000}"
