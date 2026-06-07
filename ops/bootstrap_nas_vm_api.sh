#!/usr/bin/env bash
set -euo pipefail

repo_url="https://github.com/jasonhorga/garmin-ai-caddie.git"
branch="integration/v2"
workdir="${AI_CADDIE_VM_WORKDIR:-$HOME/garmin-ai-caddie}"
api_base_url="${AI_CADDIE_API_BASE_URL:-}"
install_system=0

usage() {
  cat <<'USAGE'
Usage: ops/bootstrap_nas_vm_api.sh [options]

Options:
  --api-base-url URL     Public HTTPS origin to write into .env when known.
  --workdir PATH         Repo checkout path on the VM. Default: ~/garmin-ai-caddie
  --branch NAME          Git branch to deploy. Default: integration/v2
  --repo-url URL         Git repo URL. Default: https://github.com/jasonhorga/garmin-ai-caddie.git
  --install-system       Install Docker, git, curl, and openssl with apt-get.
  -h, --help             Show this help.

This script is for a NAS VM that is reachable only from the home LAN. It starts
the API on 127.0.0.1:9000 through Docker Compose. Publish that local port with
Cloudflare Tunnel or Tailscale Funnel; do not expose SSH through a home proxy.
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --api-base-url)
      api_base_url="${2:?missing value for --api-base-url}"
      shift 2
      ;;
    --workdir)
      workdir="${2:?missing value for --workdir}"
      shift 2
      ;;
    --branch)
      branch="${2:?missing value for --branch}"
      shift 2
      ;;
    --repo-url)
      repo_url="${2:?missing value for --repo-url}"
      shift 2
      ;;
    --install-system)
      install_system=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

run_root() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  else
    sudo "$@"
  fi
}

have() {
  command -v "$1" >/dev/null 2>&1
}

if [ "$install_system" -eq 1 ]; then
  if ! have apt-get; then
    echo "--install-system currently supports Debian/Ubuntu VMs with apt-get." >&2
    exit 2
  fi
  run_root apt-get update
  run_root apt-get install -y ca-certificates curl git openssl docker.io
  if ! run_root apt-get install -y docker-compose-plugin; then
    run_root apt-get install -y docker-compose-v2
  fi
  run_root systemctl enable --now docker
fi

for required in git curl openssl docker; do
  if ! have "$required"; then
    echo "Missing $required. Re-run with --install-system on Debian/Ubuntu, or install it first." >&2
    exit 2
  fi
done

if ! docker compose version >/dev/null 2>&1; then
  if ! run_root docker compose version >/dev/null 2>&1; then
    echo "Missing Docker Compose plugin. Re-run with --install-system or install docker-compose-plugin." >&2
    exit 2
  fi
fi

compose() {
  if docker info >/dev/null 2>&1; then
    docker compose "$@"
  else
    run_root docker compose "$@"
  fi
}

if [ ! -d "$workdir/.git" ]; then
  mkdir -p "$(dirname "$workdir")"
  git clone --branch "$branch" "$repo_url" "$workdir"
else
  git -C "$workdir" fetch origin "$branch"
  git -C "$workdir" checkout "$branch"
  git -C "$workdir" pull --ff-only origin "$branch"
fi

cd "$workdir"

if [ ! -f .env ]; then
  cp .env.example .env
fi

set_env() {
  key="$1"
  value="$2"
  tmp="$(mktemp)"
  awk -v key="$key" -v value="$value" '
    BEGIN { found = 0 }
    index($0, key "=") == 1 {
      print key "=" value
      found = 1
      next
    }
    { print }
    END {
      if (!found) {
        print key "=" value
      }
    }
  ' .env > "$tmp"
  mv "$tmp" .env
}

current_token="$(sed -n 's/^AI_CADDIE_ADMIN_TOKEN=//p' .env | tail -1)"
case "$current_token" in
  ""|"replace-with-random-admin-token"|"local-admin-token")
    set_env AI_CADDIE_ADMIN_TOKEN "$(openssl rand -hex 32)"
    ;;
esac

set_env AI_CADDIE_SECURITY_PROFILE private
set_env AI_CADDIE_DATA_MODE local_or_fixture
set_env AI_CADDIE_API_PUBLISH_HOST 127.0.0.1
if [ -n "$api_base_url" ]; then
  set_env VITE_AI_CADDIE_API_BASE_URL "$api_base_url"
fi
chmod 600 .env

compose up -d --build api

for attempt in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:9000/api/v2/health >/dev/null; then
    break
  fi
  if [ "$attempt" -eq 60 ]; then
    compose logs api
    echo "API did not become healthy on http://127.0.0.1:9000" >&2
    exit 1
  fi
  sleep 2
done

compose exec -T api sh -lc 'ops/smoke_private_trial.sh http://127.0.0.1:9000'

cat <<EOF

AI Caddie API is running on this VM:
  http://127.0.0.1:9000

Next:
  1. Publish http://127.0.0.1:9000 with Cloudflare Tunnel or Tailscale Funnel.
  2. Set GitHub repo variable AI_CADDIE_API_BASE_URL to the public HTTPS origin.
  3. Set GitHub repo secret AI_CADDIE_ADMIN_TOKEN to the value in:
     $workdir/.env

Do not paste AI_CADDIE_ADMIN_TOKEN into chat.
EOF
