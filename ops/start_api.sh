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

# Fail-closed guard: this entrypoint binds 0.0.0.0 (public). Refuse to start with no
# auth posture, so a deploy that forgot AI_CADDIE_ADMIN_TOKEN / SECURITY_PROFILE can
# never come up anonymously-owner-readable+writable on a public interface. Set an
# explicit AI_CADDIE_ALLOW_OPEN=1 to override (e.g. a deliberately public read demo).
_profile="$(printf '%s' "${AI_CADDIE_SECURITY_PROFILE:-}" | tr '[:upper:]' '[:lower:]')"
case "$_profile" in
  private|staging|production) ;;            # an admin-required profile is configured — ok
  *)
    if [ -z "${AI_CADDIE_ADMIN_TOKEN:-}" ] && [ "${AI_CADDIE_ALLOW_OPEN:-}" != "1" ]; then
      echo "FATAL [start_api.sh]: refusing to bind 0.0.0.0 with no auth — anonymous callers would map to the owner." >&2
      echo "  set AI_CADDIE_SECURITY_PROFILE=private (and AI_CADDIE_ADMIN_TOKEN), or AI_CADDIE_ALLOW_OPEN=1 to override." >&2
      exit 1
    fi
    ;;
esac

exec uv run --frozen uvicorn server_v2.main:app --host 0.0.0.0 --port "${PORT:-9000}"
