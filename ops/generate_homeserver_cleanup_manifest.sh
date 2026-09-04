#!/usr/bin/env bash
set -euo pipefail

# Generate metadata only. This script never stops/removes a container, image,
# volume, worktree, process, tunnel or server.
OUT_ROOT="${AICADDIE_MANIFEST_ROOT:-/home/jason/garmin-ai-caddie-data/cleanup-manifests}"
STAMP="${AICADDIE_MANIFEST_STAMP:-$(date -u +%Y-%m-%dT%H%M%SZ)}"
OUT="$OUT_ROOT/$STAMP-disk-audit"

umask 077
mkdir -p "$OUT"

{
  printf 'timestamp_utc=%s\n' "$STAMP"
  printf 'host=%s\n' "$(hostname)"
  printf 'user=%s\n' "$(id -un)"
  printf 'root_disk='; df -hP / | tail -n 1
  printf '\n[docker_system_df]\n'
  docker system df
  printf '\n[tmux]\n'
  tmux list-sessions -F '#{session_name}|#{session_created}|#{session_attached}' 2>/dev/null || true
  printf '\n[listening_sockets]\n'
  ss -ltn 2>/dev/null || true
} > "$OUT/summary.txt"

docker ps -a --no-trunc \
  --format '{{.Names}}|{{.State}}|{{.Status}}|{{.Image}}|{{.ID}}|{{.CreatedAt}}' \
  > "$OUT/containers.tsv"
docker image ls --no-trunc \
  --format '{{.Repository}}|{{.Tag}}|{{.ID}}|{{.CreatedAt}}|{{.Size}}|{{.Containers}}' \
  > "$OUT/images.tsv"
docker volume ls --format '{{.Name}}|{{.Driver}}|{{.Labels}}' \
  > "$OUT/volumes.tsv"

docker ps -a --filter status=exited --format '{{.Names}}' > "$OUT/stopped-container.paths"

WORKTREES="${AICADDIE_WORKTREES:-/home/jason/codex-runs/garmin-ai-caddie-p0-watch-20260822/.claude/worktrees}"
if [[ -d "$WORKTREES" ]]; then
  find "$WORKTREES" -mindepth 1 -maxdepth 1 -type d -print0 |
    while IFS= read -r -d '' dir; do
      size="$(du -sh "$dir" 2>/dev/null | awk '{print $1}')"
      mtime="$(stat -c '%y' "$dir" 2>/dev/null || true)"
      pointer=""
      if [[ -f "$dir/.git" ]]; then
        pointer="$(sed -n '1p' "$dir/.git")"
      fi
      printf '%s|%s|%s|%s\n' "$(basename "$dir")" "$size" "$mtime" "$pointer"
    done | sort > "$OUT/worktrees.tsv"
  find "$WORKTREES" -mindepth 2 -maxdepth 2 -type d -name .venv -print |
    sort > "$OUT/venv.paths"
fi

printf '%s\n' "$OUT"
