#!/usr/bin/env bash
# Block until one CI/release run or one PR-feedback event has a conclusion.
#
# The command is intended to run on the homeserver. It owns the polling,
# writes detailed output to a durable log, and prints exactly one summary line
# when it returns. This keeps the Codex control thread from repeatedly
# querying GitHub or the homeserver while a run is in flight.
set -u

REPO="${WAIT_REPO:-jasonhorga/garmin-ai-caddie}"
DATA_ROOT="${WAIT_DATA_ROOT:-/home/jason/garmin-ai-caddie-data/operations/blocking-waits}"
EVENT_FILE="${WAIT_EVENT_FILE:-/home/jason/garmin-ai-caddie-data/operations/pr-feedback-monitor/events.jsonl}"
POLL_SECONDS="${WAIT_POLL_SECONDS:-15}"
TIMEOUT_SECONDS="${WAIT_TIMEOUT_SECONDS:-0}"
SELF_COMMIT_LOGIN="${WAIT_SELF_COMMIT_LOGIN:-jasonhorga}"
SELF_COMMIT_EMAIL="${WAIT_SELF_COMMIT_EMAIL:-jasonhe@gmail.com}"
MODE=""
RUN_ID=""
PR_NUMBER=""
LOG_FILE=""
EVENT_TAIL_PID=""

usage() {
  cat <<'USAGE'
Usage:
  ops/wait_for_conclusion.sh --run RUN_ID [options]
  ops/wait_for_conclusion.sh --release RUN_ID [options]
  ops/wait_for_conclusion.sh --pr PR_NUMBER [options]
  ops/wait_for_conclusion.sh --feedback [options]

Modes:
  --run ID       Block on a GitHub Actions run.
  --release ID   Alias for --run, labelled as a release wait.
  --pr NUMBER    Block on the next event for a PR in the existing monitor
                 JSONL stream (comments, reviews, commits, heads, or CI).
  --feedback     Block on the next event for any PR in that stream.

Options:
  --repo OWNER/REPO       Repository (default: $WAIT_REPO or this project).
  --data-root PATH        Durable log directory (default: $WAIT_DATA_ROOT).
  WAIT_LATEST_RESULT_FILE Environment override for the atomically replaced
                          one-line latest-result file (default: data-root).
  --event-file PATH       PR monitor JSONL stream (default: $WAIT_EVENT_FILE).
  --poll-seconds N        Internal wait/read interval (default: 15).
  --timeout-seconds N     0 means wait forever (default: 0).
  --log PATH              Exact log path; otherwise one is created in data-root.
  WAIT_SELF_COMMIT_LOGIN / WAIT_SELF_COMMIT_EMAIL identify Codex's commit
                         identity for ignoring self-generated docs-only runs.
  -h, --help              Show this help.

Output is one line:
  status=... conclusion=... failed_jobs=... log=/absolute/path/to/log
USAGE
}

is_uint() {
  [[ "${1:-}" =~ ^[0-9]+$ ]]
}

die_usage() {
  printf 'error: %s\n' "$1" >&2
  usage >&2
  exit 2
}

while (($#)); do
  case "$1" in
    --run)
      (($# >= 2)) || die_usage "--run needs a run id"
      MODE="ci"
      RUN_ID="$2"
      shift 2
      ;;
    --release)
      (($# >= 2)) || die_usage "--release needs a run id"
      MODE="release"
      RUN_ID="$2"
      shift 2
      ;;
    --pr)
      (($# >= 2)) || die_usage "--pr needs a pull request number"
      MODE="pr"
      PR_NUMBER="$2"
      shift 2
      ;;
    --feedback|--all-prs)
      MODE="feedback"
      shift
      ;;
    --repo)
      (($# >= 2)) || die_usage "--repo needs OWNER/REPO"
      REPO="$2"
      shift 2
      ;;
    --data-root)
      (($# >= 2)) || die_usage "--data-root needs a path"
      DATA_ROOT="$2"
      shift 2
      ;;
    --event-file)
      (($# >= 2)) || die_usage "--event-file needs a path"
      EVENT_FILE="$2"
      shift 2
      ;;
    --poll-seconds)
      (($# >= 2)) || die_usage "--poll-seconds needs an integer"
      POLL_SECONDS="$2"
      shift 2
      ;;
    --timeout-seconds)
      (($# >= 2)) || die_usage "--timeout-seconds needs an integer"
      TIMEOUT_SECONDS="$2"
      shift 2
      ;;
    --log)
      (($# >= 2)) || die_usage "--log needs a path"
      LOG_FILE="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die_usage "unknown argument: $1"
      ;;
  esac
done

[[ -n "$MODE" ]] || die_usage "one of --run, --release, or --pr is required"
if [[ "$MODE" == "pr" ]]; then
  is_uint "$PR_NUMBER" || die_usage "PR number must be an integer"
elif [[ "$MODE" != "feedback" ]]; then
  is_uint "$RUN_ID" || die_usage "run id must be an integer"
fi
is_uint "$POLL_SECONDS" || die_usage "poll interval must be an integer"
is_uint "$TIMEOUT_SECONDS" || die_usage "timeout must be an integer"
(( POLL_SECONDS > 0 )) || die_usage "poll interval must be greater than zero"

umask 077
mkdir -p "$DATA_ROOT"
LATEST_RESULT_FILE="${WAIT_LATEST_RESULT_FILE:-$DATA_ROOT/latest-result.txt}"
latest_result_parent="${LATEST_RESULT_FILE%/*}"
[[ "$latest_result_parent" != "$LATEST_RESULT_FILE" ]] && mkdir -p "$latest_result_parent"
if [[ -z "$LOG_FILE" ]]; then
  subject="${MODE}-${RUN_ID:-pr-${PR_NUMBER}}"
  subject="${subject//[^A-Za-z0-9_.-]/_}"
  LOG_FILE="$DATA_ROOT/wait-${subject}-$(date -u +%Y%m%dT%H%M%SZ)-$$.log"
else
  log_parent="${LOG_FILE%/*}"
  [[ "$log_parent" != "$LOG_FILE" ]] && mkdir -p "$log_parent"
fi
touch "$LOG_FILE"

log() {
  printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >>"$LOG_FILE"
}

deadline=""
if (( TIMEOUT_SECONDS > 0 )); then
  deadline=$(( $(date +%s) + TIMEOUT_SECONDS ))
fi

timed_out() {
  [[ -n "$deadline" ]] && (( $(date +%s) >= deadline ))
}

finish() {
  local status="$1" conclusion="$2" failed_jobs="$3" exit_code="${4:-0}"
  # The only normal stdout emitted by this command is this summary line. Keep
  # the same line in a durable, atomically replaced file for tmux callers.
  local summary="status=$status conclusion=$conclusion failed_jobs=$failed_jobs log=$LOG_FILE"
  local result_tmp="${LATEST_RESULT_FILE}.tmp.$$"
  printf '%s\n' "$summary" >"$result_tmp"
  mv -f "$result_tmp" "$LATEST_RESULT_FILE"
  printf '%s\n' "$summary"
  exit "$exit_code"
}

cleanup() {
  if [[ -n "$EVENT_TAIL_PID" ]] && kill -0 "$EVENT_TAIL_PID" 2>/dev/null; then
    kill "$EVENT_TAIL_PID" 2>/dev/null || true
    wait "$EVENT_TAIL_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

summarize_run() {
  local summarize_run_id="$1"
  log "reading terminal run summary run=$summarize_run_id"
  run_json="$LOG_FILE.run-${summarize_run_id}.json"
  set +e
  gh run view "$summarize_run_id" --repo "$REPO" --json status,conclusion,jobs,url,headBranch,headSha >"$run_json" 2>>"$LOG_FILE"
  view_rc=$?
  if (( view_rc != 0 )) || ! jq -e . "$run_json" >/dev/null 2>>"$LOG_FILE"; then
    log "unable to read final run state (gh run view exit=$view_rc)"
    finish error gh_error unknown 1
  fi

  status="$(jq -r '.status // "unknown"' "$run_json" 2>>"$LOG_FILE")"
  conclusion="$(jq -r '.conclusion // "unknown"' "$run_json" 2>>"$LOG_FILE")"

  if run_is_self_docs_only "$run_json"; then
    log "ignoring self-generated docs-only CI run=$summarize_run_id head=$(jq -r '.headSha // empty' "$run_json")"
    rm -f "$run_json"
    return 42
  fi

  failed_jobs="$(jq -r '
    if (.jobs | type) != "array" then "unknown"
    else
      [.jobs[] | select((.conclusion // "") != "" and
        (.conclusion // "") != "success" and
        (.conclusion // "") != "skipped" and
        (.conclusion // "") != "neutral") | .name]
      | unique | if length == 0 then "none" else join(",") end
    end
  ' "$run_json" 2>>"$LOG_FILE")"
  [[ -n "$failed_jobs" ]] || failed_jobs="unknown"

  {
    printf '\n--- final run JSON ---\n'
    cat "$run_json"
    printf '\n--- complete run log ---\n'
  } >>"$LOG_FILE"
  set +e
  gh run view "$summarize_run_id" --repo "$REPO" --log >>"$LOG_FILE" 2>&1
  log_rc=$?
  log "complete run log exit=$log_rc"
  rm -f "$run_json"

  if [[ "$status" == "completed" && "$conclusion" == "success" ]]; then
    finish "$status" "$conclusion" "$failed_jobs" 0
  fi
  finish "$status" "$conclusion" "$failed_jobs" 1
}

commit_is_self_docs_only() {
  local commit_sha="$1"
  local commit_json="$LOG_FILE.commit-${commit_sha}.json"
  [[ "$commit_sha" =~ ^[0-9a-fA-F]{7,64}$ ]] || return 1
  if ! gh api "repos/$REPO/commits/$commit_sha" >"$commit_json" 2>>"$LOG_FILE"; then
    log "unable to inspect commit for self-run filtering sha=$commit_sha"
    rm -f "$commit_json"
    return 1
  fi
  jq -e --arg login "$SELF_COMMIT_LOGIN" --arg email "$SELF_COMMIT_EMAIL" '
    ((.author.login // "") == $login or
      (.committer.login // "") == $login or
      (.commit.author.email // "") == $email or
      (.commit.committer.email // "") == $email) and
    ((.files // []) | length > 0) and
    all(.files[]?.filename;
      . == "AGENTS.md" or startswith("docs/") or
      test("^\\.codex-[^/]+\\.md$"))
  ' "$commit_json" >/dev/null 2>>"$LOG_FILE"
  local result=$?
  rm -f "$commit_json"
  return "$result"
}

run_is_self_docs_only() {
  local run_json="$1"
  local head_branch head_sha
  head_branch="$(jq -r '.headBranch // empty' "$run_json" 2>>"$LOG_FILE")"
  head_sha="$(jq -r '.headSha // empty' "$run_json" 2>>"$LOG_FILE")"
  [[ "$head_branch" == "main" ]] || return 1
  [[ -n "$head_sha" ]] || return 1
  commit_is_self_docs_only "$head_sha"
}

wait_for_run() {
  log "waiting mode=$MODE repo=$REPO run=$RUN_ID"
  set +e
  gh run watch "$RUN_ID" --repo "$REPO" --interval "$POLL_SECONDS" --exit-status >>"$LOG_FILE" 2>&1
  watch_rc=$?
  log "gh run watch exit=$watch_rc"
  summarize_run "$RUN_ID"
  summary_rc=$?
  if (( summary_rc == 42 )); then
    finish ignored self_docs_only none 0
  fi
  return "$summary_rc"
}

event_matches_pr() {
  local event="$1"
  if [[ "$MODE" == "feedback" ]]; then
    jq -e '((.kind? // "") | length > 0)' <<<"$event" >/dev/null 2>>"$LOG_FILE"
    return
  fi
  jq -e --argjson pr "$PR_NUMBER" '
    ((.pr? == $pr) or
      (((.pullRequests? // []) |
        map(if type == "number" then . else (tonumber? // -1) end) |
        index($pr)) != null)) and
    ((.kind? // "") | length > 0)
  ' <<<"$event" >/dev/null 2>>"$LOG_FILE"
}

event_is_conclusive() {
  local event="$1"
  jq -e '
    (.kind // "") as $kind |
    if ($kind == "ci_run_added" or $kind == "ci_run_changed") then
      (((.conclusion // "") | length) > 0 or (.status // "") == "completed")
    elif $kind == "ci_changed" then
      ((.checks // []) | length) > 0 and
      all(.checks[]?;
        ((.state // "") | ascii_upcase) as $state |
        ($state != "IN_PROGRESS" and $state != "QUEUED" and
         $state != "PENDING" and $state != "WAITING" and
         $state != "EXPECTED")
      )
    else
      true
    end
  ' <<<"$event" >/dev/null 2>>"$LOG_FILE"
}

wait_for_pr_event() {
  event_parent="${EVENT_FILE%/*}"
  [[ "$event_parent" == "$EVENT_FILE" ]] && event_parent="."
  mkdir -p "$event_parent"
  touch "$EVENT_FILE"
  start_line=$(( $(wc -l <"$EVENT_FILE") + 1 ))
  log "waiting mode=$MODE repo=$REPO pr=${PR_NUMBER:-all} event_file=$EVENT_FILE start_line=$start_line"

  # The existing monitor owns GitHub polling and appends deduplicated events.
  # This waiter only follows that durable stream, so it does not create a
  # second monitor or duplicate API traffic.
  coproc EVENT_TAIL { exec tail -n +"$start_line" -F "$EVENT_FILE" 2>>"$LOG_FILE"; }
  EVENT_TAIL_PID="$EVENT_TAIL_PID"
  event_fd="${EVENT_TAIL[0]}"
  while :; do
    if timed_out; then
      log "timeout waiting for PR event"
      finish timeout timeout none 124
    fi
    if IFS= read -r -t "$POLL_SECONDS" -u "$event_fd" event_line; then
      printf '%s\n' "$event_line" >>"$LOG_FILE"
      if event_matches_pr "$event_line" && event_is_conclusive "$event_line"; then
        event_kind="$(jq -r '.kind // "pr_feedback"' <<<"$event_line" 2>>"$LOG_FILE")"
        event_pr="$(jq -r 'if .pr? then (.pr|tostring) elif (.pullRequests? // []) | length > 0 then (.pullRequests[0]|tostring) else "all" end' <<<"$event_line" 2>>"$LOG_FILE")"
        log "matched PR event kind=$event_kind"
        event_run_id="$(jq -r '.runId // empty' <<<"$event_line" 2>>"$LOG_FILE")"
        if [[ "$event_kind" == "ci_run_added" || "$event_kind" == "ci_run_changed" ]] && [[ -n "$event_run_id" ]]; then
          event_head_branch="$(jq -r '.headBranch // empty' <<<"$event_line" 2>>"$LOG_FILE")"
          event_head_sha="$(jq -r '.headSha // empty' <<<"$event_line" 2>>"$LOG_FILE")"
          event_pr_count="$(jq -r '((.pullRequests // []) | length)' <<<"$event_line" 2>>"$LOG_FILE")"
          if [[ "$event_head_branch" == "main" && "$event_pr_count" == "0" && -n "$event_head_sha" ]] && commit_is_self_docs_only "$event_head_sha"; then
            log "ignored self-generated docs-only CI event run=$event_run_id head=$event_head_sha"
            continue
          fi
          # A terminal Actions event is a run conclusion. Reuse the same
          # summary path as --run so failed job names and the full run log are
          # available in the one-line result.
          summarize_run "$event_run_id"
        elif [[ "$event_kind" == "ci_changed" ]]; then
          event_failed_jobs="$(jq -r '
            [.checks[]? | select(((.state // "") | ascii_upcase) as $state |
              ($state != "SUCCESS" and $state != "SKIPPED" and $state != "NEUTRAL")) | .name]
            | unique | if length == 0 then "none" else join(",") end
          ' <<<"$event_line" 2>>"$LOG_FILE")"
          [[ -n "$event_failed_jobs" ]] || event_failed_jobs="unknown"
          finish completed ci_checks_terminal "$event_failed_jobs" 0
        else
          finish observed "pr_feedback:${event_kind}:pr${event_pr}" none 0
        fi
      fi
    elif ! kill -0 "$EVENT_TAIL_PID" 2>/dev/null; then
      log "event stream exited before a matching event"
      finish error event_stream_closed unknown 1
    fi
  done
}

if [[ "$MODE" == "pr" || "$MODE" == "feedback" ]]; then
  wait_for_pr_event
else
  wait_for_run
fi
