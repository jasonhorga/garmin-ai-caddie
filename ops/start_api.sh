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

# A Compose `depends_on` health condition only gates the initial `up`; it does
# not protect a manually restarted API after the database has gone away. Wait
# for a bounded period before invoking uv/migrations so a dependency outage is
# cheap and observable instead of repeatedly compiling the whole application.
wait_for_postgres() {
  database_url="${AI_CADDIE_DATABASE_URL:-}"
  case "$database_url" in
    postgresql+psycopg://*|postgresql+psycopg2://*) ;;
    *) return 0 ;;
  esac

  if ! command -v pg_isready >/dev/null 2>&1; then
    echo "FATAL [start_api.sh]: pg_isready is required for a PostgreSQL deployment." >&2
    return 1
  fi

  # Parse only the non-secret connection target. Do not pass the database URL
  # (which may contain a password) as a process argument.
  target="$(printf '%s\n' "$database_url" | python -c '
import sys
from urllib.parse import unquote, urlsplit

raw = sys.stdin.read().strip()
scheme, remainder = raw.split("://", 1)
scheme = scheme.split("+", 1)[0]
parts = urlsplit(f"{scheme}://{remainder}")
host = parts.hostname or ""
port = parts.port or 5432
user = unquote(parts.username or "")
database = unquote(parts.path.lstrip("/") or "")
if not host or not user or not database:
    raise SystemExit("invalid PostgreSQL connection target")
print(f"{host}\t{port}\t{user}\t{database}")
')"
  IFS="	" read -r db_host db_port db_user db_name <<EOF
$target
EOF

  attempts="${AI_CADDIE_DB_READY_ATTEMPTS:-12}"
  delay="${AI_CADDIE_DB_READY_DELAY_SECONDS:-5}"
  attempt=1
  while ! pg_isready -q -h "$db_host" -p "$db_port" -U "$db_user" -d "$db_name"; do
    if [ "$attempt" -ge "$attempts" ]; then
      echo "FATAL [start_api.sh]: PostgreSQL was not ready after $attempts attempts." >&2
      return 1
    fi
    echo "waiting for PostgreSQL ($attempt/$attempts)" >&2
    sleep "$delay"
    attempt=$((attempt + 1))
  done
}

wait_for_postgres

# Serialize schema/identity initialization when two old containers happen to
# share the same persistent volume. The lock is released before uvicorn starts.
migration_lock="${AI_CADDIE_MIGRATION_LOCK:-${AI_CADDIE_PRIVATE_ROOT:-/tmp}/.migration.lock}"
if command -v flock >/dev/null 2>&1; then
  mkdir -p "$(dirname "$migration_lock")"
  exec 9>"$migration_lock"
  lock_timeout="${AI_CADDIE_MIGRATION_LOCK_TIMEOUT_SECONDS:-60}"
  if ! flock -w "$lock_timeout" 9; then
    echo "FATAL [start_api.sh]: migration lock was not acquired within ${lock_timeout}s." >&2
    exit 1
  fi
fi

# Bring the identity DB schema up to date (Postgres in prod; the SQLite default
# is created here too). Idempotent; fail-closed so a broken migration stops boot.
migration_timeout="${AI_CADDIE_MIGRATION_TIMEOUT_SECONDS:-120}"
timeout "${migration_timeout}s" uv run --frozen alembic upgrade head
timeout "${migration_timeout}s" uv run --frozen python -m server_v2.identity_seed

# The lock only protects schema/identity initialization. Do not inherit it
# into the long-lived API process, otherwise a second container can be
# needlessly blocked for the entire lifetime of the first one.
if command -v flock >/dev/null 2>&1; then
  flock -u 9
  exec 9>&-
fi

exec uv run --frozen uvicorn server_v2.main:app --host 0.0.0.0 --port "${PORT:-9000}"
