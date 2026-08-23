#!/usr/bin/env bash
set -euo pipefail

# Read-only inventory for historical Codex/Claude run directories.  It does
# not inspect file contents or remove anything; the output is a deletion gate.
RUNS="${AICADDIE_CODEX_RUNS:-/home/jason/codex-runs}"
OUT_ROOT="${AICADDIE_MANIFEST_ROOT:-/home/jason/garmin-ai-caddie-data/cleanup-manifests}"
STAMP="${AICADDIE_MANIFEST_STAMP:-$(date -u +%Y-%m-%dT%H%M%SZ)}"
OUT="$OUT_ROOT/$STAMP-codex-runs-audit"

[[ -d "$RUNS" ]] || { printf 'runs_not_found=%s\n' "$RUNS" >&2; exit 2; }
umask 077
mkdir -p "$OUT"

{
  printf 'timestamp_utc=%s\n' "$STAMP"
  printf 'host=%s\n' "$(hostname)"
  printf 'user=%s\n' "$(id -un)"
  printf 'runs_root=%s\n' "$RUNS"
  printf 'root_disk='; df -hP / | tail -n 1
  printf 'runs_disk='; du -sh "$RUNS" 2>/dev/null | awk '{print $1}'
} > "$OUT/summary.txt"

printf 'name\tbytes\tmtime\tnewest_file\tgit\tvenv\tnode_modules\tbuild_artifacts\tevidence_artifacts\tdata_artifacts\tlink_count\tnested_venv_count\tnested_venv_bytes\tnested_worktree_count\tnested_claude_bytes\n' > "$OUT/runs.tsv"

# Return a single apparent byte count without following a directory symlink.
dir_bytes() {
  local path="$1"
  local value
  [[ -d "$path" && ! -L "$path" ]] || { printf '0\n'; return; }
  value="$(du --bytes --summarize "$path" 2>/dev/null | awk 'NR == 1 {print $1}' || true)"
  printf '%s\n' "${value:-0}"
}

for dir in "$RUNS"/*; do
  [[ -d "$dir" ]] || continue
  name="${dir##*/}"
  bytes="$(du -sk "$dir" 2>/dev/null | awk '{print $1 * 1024}')"
  mtime="$(stat -c '%y' "$dir" 2>/dev/null || true)"
  newest="$(find "$dir" -type f -printf '%T@\t%p\n' 2>/dev/null | sort -nr | head -1 | cut -f2- || true)"
  [[ -e "$dir/.git" ]] && git=yes || git=no
  [[ -d "$dir/.venv" ]] && venv=yes || venv=no
  nested_venv_count=0
  nested_venv_bytes=0
  nested_worktree_count=0
  nested_claude_bytes=0
  claude_dir="$dir/.claude"
  worktrees_dir="$claude_dir/worktrees"
  if [[ -d "$claude_dir" && ! -L "$claude_dir" ]]; then
    nested_claude_bytes="$(dir_bytes "$claude_dir")"
    if [[ -d "$worktrees_dir" && ! -L "$worktrees_dir" ]]; then
      nested_worktree_count="$(
        find "$worktrees_dir" -mindepth 1 -maxdepth 1 -type d -printf '.\n' 2>/dev/null |
          wc -l
      )"
      while IFS= read -r -d '' nested_venv; do
        nested_venv_count=$((nested_venv_count + 1))
        venv_bytes="$(dir_bytes "$nested_venv")"
        nested_venv_bytes=$((nested_venv_bytes + venv_bytes))
      done < <(
        find "$worktrees_dir" -mindepth 2 -type d -name .venv -print0 2>/dev/null
      )
    fi
  fi
  [[ -d "$dir/node_modules" ]] && node=yes || node=no
  build=no
  find "$dir" -maxdepth 3 -type d \( -name DerivedData -o -name .build -o -name dist -o -name build -o -name __pycache__ \) -print -quit 2>/dev/null | rg . >/dev/null && build=yes || true
  evidence=no
  find "$dir" -type f \( -iname '*.ipa' -o -iname '*.dSYM.zip' -o -iname '*.png' -o -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.html' \) -print -quit 2>/dev/null | rg . >/dev/null && evidence=yes || true
  data=no
  find "$dir" -type f \( -iname '*.jsonl' -o -iname '*.fit' -o -iname '*.db' -o -iname '*.sqlite' -o -iname '*.zip' -o -iname '*.gz' \) -print -quit 2>/dev/null | rg . >/dev/null && data=yes || true
  links="$(find "$dir" -type l 2>/dev/null | wc -l)"
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$name" "$bytes" "$mtime" "$newest" "$git" "$venv" "$node" \
    "$build" "$evidence" "$data" "$links" "$nested_venv_count" \
    "$nested_venv_bytes" "$nested_worktree_count" "$nested_claude_bytes" >> "$OUT/runs.tsv"
done

# Keep the schema header at the top; sort only data rows.
{ head -n 1 "$OUT/runs.tsv"; tail -n +2 "$OUT/runs.tsv" | sort; } > "$OUT/runs.tsv.sorted"
mv "$OUT/runs.tsv.sorted" "$OUT/runs.tsv"

{
  printf 'directory_count=%s\n' "$(($(wc -l < "$OUT/runs.tsv") - 1))"
  printf '\n[process_use]\n'
  for proc in /proc/[0-9]*; do
    pid="${proc##*/}"
    [[ -r "$proc/cmdline" ]] || continue
    cmdline="$(tr '\0' ' ' < "$proc/cmdline" 2>/dev/null || true)"
    cwd="$(readlink "$proc/cwd" 2>/dev/null || true)"
    case "$cwd" in "$RUNS"/*) printf 'cwd\t%s\t%s\t%s\n' "$pid" "$cwd" "$cmdline";; esac
  done
} > "$OUT/process-use.tsv"

printf '%s\n' "$OUT"
