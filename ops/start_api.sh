#!/usr/bin/env sh
set -eu

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
app_root="$(CDPATH= cd -- "$script_dir/.." && pwd)"
cd "$app_root"

if [ -n "${AI_CADDIE_PRIVATE_ROOT:-}" ]; then
  private_root="${AI_CADDIE_PRIVATE_ROOT}"
  case "$private_root" in
    /*) ;;
    *) private_root="$app_root/$private_root" ;;
  esac
  if [ "$private_root" = "$app_root" ]; then
    echo "FATAL [start_api.sh]: AI_CADDIE_PRIVATE_ROOT must not be the application root." >&2
    exit 1
  fi
  mkdir -p "$private_root/data" "$private_root/.garmin_tokens" "$private_root/output" "$private_root/logs" "$private_root/backups"
  for name in data .garmin_tokens output logs backups; do
    rm -rf "$app_root/$name"
    ln -s "$private_root/$name" "$app_root/$name"
  done
  if [ -f "$private_root/clubs.json" ]; then
    rm -f "$app_root/clubs.json"
    ln -s "$private_root/clubs.json" "$app_root/clubs.json"
  fi
fi

# Fail-closed guard: this entrypoint binds 0.0.0.0 (public). Refuse to start with no
# auth posture, so a deploy that forgot AI_CADDIE_ADMIN_TOKEN / SECURITY_PROFILE can
# never come up anonymously-owner-readable+writable on a public interface. Set an
# explicit AI_CADDIE_ALLOW_OPEN=1 to override (e.g. a deliberately public read demo).
_profile="$(printf '%s' "${AI_CADDIE_SECURITY_PROFILE:-}" | tr '[:upper:]' '[:lower:]')"
case "$_profile" in
  private|staging|production)
    # An admin-required profile still needs a NON-EMPTY admin token: an empty token under a
    # prod-like profile (e.g. a deploy that forgot the .env override) would leave the owner
    # protected only by an empty/default credential. Fail closed.
    if [ -z "${AI_CADDIE_ADMIN_TOKEN:-}" ]; then
      echo "FATAL [start_api.sh]: profile '$_profile' requires a non-empty AI_CADDIE_ADMIN_TOKEN." >&2
      echo "  set AI_CADDIE_ADMIN_TOKEN in the environment / .env, or AI_CADDIE_ALLOW_OPEN=1 for a deliberate open demo." >&2
      exit 1
    fi
    ;;
  *)
    if [ -z "${AI_CADDIE_ADMIN_TOKEN:-}" ] && [ "${AI_CADDIE_ALLOW_OPEN:-}" != "1" ]; then
      echo "FATAL [start_api.sh]: refusing to bind 0.0.0.0 with no auth — anonymous callers would map to the owner." >&2
      echo "  set AI_CADDIE_SECURITY_PROFILE=private (and AI_CADDIE_ADMIN_TOKEN), or AI_CADDIE_ALLOW_OPEN=1 to override." >&2
      exit 1
    fi
    ;;
esac

# Bring the identity DB schema up to date (Postgres in prod; the SQLite default
# is created here too). Idempotent; fail-closed so a broken migration stops boot.
uv run --frozen alembic upgrade head
uv run --frozen python -m server_v2.identity_seed

exec uv run --frozen uvicorn server_v2.main:app --host 0.0.0.0 --port "${PORT:-9000}"
