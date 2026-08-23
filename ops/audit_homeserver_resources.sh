#!/usr/bin/env bash
set -euo pipefail

# Read-only capacity report. Run on homeserver; it never deletes resources.
PROJECT_ROOT="${AICADDIE_REMOTE_ROOT:-/home/jason/codex-runs/garmin-ai-caddie-p0-watch-20260822}"
WARN_GIB="${AICADDIE_WARN_GIB:-15}"
STOP_GIB="${AICADDIE_STOP_GIB:-10}"

free_kib="$(df -Pk / | awk 'NR==2 {print $4}')"
free_gib=$((free_kib / 1024 / 1024))

printf 'timestamp_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf 'project_root=%s\n' "$PROJECT_ROOT"
df -hP /
printf 'free_gib=%s\n' "$free_gib"

if (( free_gib < STOP_GIB )); then
  printf 'capacity_state=STOP_HEAVY_WORK\n' >&2
elif (( free_gib < WARN_GIB )); then
  printf 'capacity_state=NO_PARALLEL_HEAVY_WORK\n' >&2
else
  printf 'capacity_state=OK\n'
fi

if command -v docker >/dev/null 2>&1; then
  docker system df
  printf 'running_containers=%s\n' "$(docker ps -q | wc -l)"
  printf 'all_containers=%s\n' "$(docker ps -aq | wc -l)"
  printf 'volumes=%s\n' "$(docker volume ls -q | wc -l)"
fi

if command -v tmux >/dev/null 2>&1; then
  printf '%s\n' '-- tmux sessions --'
  tmux list-sessions -F '#{session_name}' 2>/dev/null || true
fi

if [[ -d "$PROJECT_ROOT/.claude/worktrees" ]]; then
  printf 'worktree_dirs=%s\n' "$(find "$PROJECT_ROOT/.claude/worktrees" -mindepth 1 -maxdepth 1 -type d | wc -l)"
  printf 'venv_dirs=%s\n' "$(find "$PROJECT_ROOT/.claude/worktrees" -mindepth 2 -maxdepth 2 -type d -name .venv | wc -l)"
fi
