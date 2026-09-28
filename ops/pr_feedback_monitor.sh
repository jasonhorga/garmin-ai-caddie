#!/usr/bin/env bash
# Lightweight, read-only GitHub PR monitor for the Codex/Claude handoff.
# It records observations; it never merges, edits source, or starts project services.
set -u

REPO="${PR_MONITOR_REPO:-jasonhorga/garmin-ai-caddie}"
DATA_ROOT="${PR_MONITOR_DATA_ROOT:-/home/jason/garmin-ai-caddie-data/operations/pr-feedback-monitor}"
STATE="$DATA_ROOT/state.json"
EVENTS="$DATA_ROOT/events.jsonl"
LOCK="$DATA_ROOT/state.json.lock"
INTERVAL="${PR_MONITOR_INTERVAL_SECONDS:-60}"

umask 077
mkdir -p "$DATA_ROOT/tmp"
touch "$EVENTS"
chmod 600 "$EVENTS"

now_utc() { date -u +%Y-%m-%dT%H:%M:%SZ; }

state_update() {
  local arg_count="$#"
  local filter="${!arg_count}"
  local jq_args=()
  if [ "$arg_count" -gt 1 ]; then
    jq_args=("${@:1:$((arg_count - 1))}")
  fi
  (
    flock -x 9
    tmp="$STATE.tmp.$$"
    if jq "${jq_args[@]}" "$filter" "$STATE" > "$tmp"; then
      mv -f "$tmp" "$STATE"
    else
      rm -f "$tmp"
      return 1
    fi
  ) 9>"$LOCK"
}

state_value() {
  local arg_count="$#"
  local filter="${!arg_count}"
  local jq_args=()
  if [ "$arg_count" -gt 1 ]; then
    jq_args=("${@:1:$((arg_count - 1))}")
  fi
  jq -r "${jq_args[@]}" "$filter" "$STATE" 2>/dev/null || printf ''
}

ensure_state_shape() {
  state_update '.seenIssueCommentIds //= []
    | .seenReviewCommentIds //= []
    | .seenReviewIds //= []
    | .seenCommitShas //= []
    | .pullCommits //= {}
    | .workflowRuns //= {}
    | .workflowRunsInitialized //= false
    | .lastWorkflowScanAt //= ""
    | .openPulls //= {}
    | .recentlyClosed //= {}
    | if (.schema // "") == "garmin-ai-caddie-pr-feedback-monitor-v1" then
        .lastProcessedReviewCommentId = ((.seenReviewCommentIds // [] | map(tonumber) | max) // 0)
        | .lastProcessedReviewId = ((.seenReviewIds // [] | map(tonumber) | max) // 0)
        | .schema = "garmin-ai-caddie-pr-feedback-monitor-v2"
      else
        .lastProcessedReviewCommentId //= ((.seenReviewCommentIds // [] | map(tonumber) | max) // 0)
        | .lastProcessedReviewId //= ((.seenReviewIds // [] | map(tonumber) | max) // 0)
        | .schema //= "garmin-ai-caddie-pr-feedback-monitor-v2"
      end
    | .schema = "garmin-ai-caddie-pr-feedback-monitor-v4"'
}

seen_id() {
  local field="$1" id="$2" baseline="$3"
  jq -e --arg id "$id" --argjson baseline "${baseline:-0}" \
    "((.${field} // []) | map(tostring) | index(\$id)) != null or ((\$id | tonumber) <= \$baseline)" \
    "$STATE" >/dev/null 2>&1
}

record_event() {
  local event_json="$1"
  printf '%s\n' "$event_json" >> "$EVENTS"
  printf '[%s] %s\n' "$(now_utc)" "$event_json"
}

log_message() {
  printf '[%s] %s\n' "$(now_utc)" "$1"
}

mark_seen() {
  local field="$1" id="$2" baseline_field="$3"
  state_update --arg id "$id" --arg field "$field" --arg baseline_field "$baseline_field" '
    .[$field] = (((.[$field] // []) + [$id] | map(tostring) | unique)[-5000:])
    | .[$baseline_field] = ((.[$baseline_field] // 0) as $old | ([$id | tonumber, $old] | max))'
}

api_array() {
  local endpoint="$1"
  local raw
  raw="$(gh api --paginate --slurp "$endpoint" 2>/dev/null)" || return 1
  jq -c 'add // []' <<<"$raw" 2>/dev/null || return 1
}

api_workflow_runs() {
  local since="$1"
  local raw
  # Workflow runs are repository-wide. The encoded comparison operator keeps
  # the query intact when gh builds the request URL.
  raw="$(gh api --paginate --slurp \
    "repos/$REPO/actions/runs?per_page=100&created=%3E%3D$since" 2>/dev/null)" || return 1
  jq -c '[.[]?.workflow_runs[]?] | unique_by(.id)' <<<"$raw" 2>/dev/null || return 1
}

pr_number_from_url() {
  local url="$1"
  if [[ "$url" =~ /(issues|pulls)/([0-9]+) ]]; then
    printf '%s\n' "${BASH_REMATCH[2]}"
  else
    printf '\n'
  fi
}

lookback_days="${PR_MONITOR_LOOKBACK_DAYS:-7}"
since_date="$(date -u -d "$lookback_days days ago" +%Y-%m-%d 2>/dev/null || date -u +%Y-%m-%d)"
scan_dir=""
cleanup_scan() {
  if [ -n "$scan_dir" ] && [ -d "$scan_dir" ]; then
    rm -rf "$scan_dir"
  fi
}
trap cleanup_scan EXIT
trap 'cleanup_scan; exit 130' INT
trap 'cleanup_scan; exit 143' TERM

ensure_state_shape

while :; do
  previous_scan="$(state_value '.lastScanAt // ""')"
  if [ -z "$previous_scan" ]; then
    previous_scan="$(date -u -d "$lookback_days days ago" +%Y-%m-%dT00:00:00Z 2>/dev/null || now_utc)"
  fi
  comment_since="$(date -u -d "$previous_scan - 60 seconds" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || printf '%s' "$previous_scan")"
  scan_started="$(now_utc)"
  scan_dir="$(mktemp -d "$DATA_ROOT/tmp/scan.XXXXXX")"
  scan_ok=1
  if ! open_json="$(gh pr list --repo "$REPO" --state open --limit 1000 --json number,headRefOid,updatedAt,state,mergeCommit 2>/dev/null)"; then
    scan_ok=0
    open_json='[]'
  fi
  if ! recent_json="$(gh pr list --repo "$REPO" --state all --search "updated:>=$since_date" --limit 1000 --json number,headRefOid,updatedAt,state,mergeCommit 2>/dev/null)"; then
    scan_ok=0
    recent_json='[]'
  fi
  # Keep PR/comment classification independent from the lookback window. A
  # repository-wide issue-comment stream can contain a comment on an old PR;
  # the full number index lets us retain it without scanning that PR's detail
  # endpoints on every poll.
  if ! all_pr_json="$(gh pr list --repo "$REPO" --state all --limit 1000 --json number 2>/dev/null)"; then
    scan_ok=0
    all_pr_json='[]'
  fi
  # Use updatedAt rather than merge/close dates so a new comment on an old
  # PR enters the scan window. The high limit avoids silently dropping PRs
  # when a repository has a busy review burst.
  if ! prs="$(jq -s 'add | unique_by(.number)' <(printf '%s\n' "$open_json") <(printf '%s\n' "$recent_json") 2>/dev/null)"; then
    scan_ok=0
    prs='[]'
  fi
  if ! pr_index="$(jq -c 'map({key:(.number|tostring),value:true}) | from_entries' <<<"$prs" 2>/dev/null)"; then
    scan_ok=0
    pr_index='{}'
  fi
  if ! all_pr_index="$(jq -c 'map({key:(.number|tostring),value:true}) | from_entries' <<<"$all_pr_json" 2>/dev/null)"; then
    scan_ok=0
    all_pr_index='{}'
  fi

  # Comments are repository-wide resources. Fetching the two incremental
  # streams once per scan covers old PRs that receive a new comment without
  # making one request per historical PR.
  issue_comments_file="$scan_dir/issues-comments.json"
  inline_comments_file="$scan_dir/pulls-comments.json"
  if ! api_array "repos/$REPO/issues/comments?since=$comment_since&per_page=100" > "$issue_comments_file"; then
    scan_ok=0
  fi
  if ! api_array "repos/$REPO/pulls/comments?since=$comment_since&per_page=100" > "$inline_comments_file"; then
    scan_ok=0
  fi
  if [ "$scan_ok" -ne 1 ]; then
    log_message "monitor_error: PR list or incremental comment stream unavailable; retaining cursor $previous_scan"
    rm -rf "$scan_dir"
    scan_dir=""
    sleep "$INTERVAL"
    continue
  fi
  workflow_fetch_failed=0
  workflow_runs_file="$scan_dir/workflow-runs.json"
  workflow_since="$(date -u -d "$lookback_days days ago" +%Y-%m-%d 2>/dev/null || printf '%s' "$since_date")"
  if ! api_workflow_runs "$workflow_since" > "$workflow_runs_file"; then
    workflow_fetch_failed=1
    printf '[]\n' > "$workflow_runs_file"
  fi

  # Track repository-wide Actions runs as well as PR check snapshots. A
  # merge-triggered push run may no longer update the PR, so it cannot be
  # recovered from `gh pr checks` alone. The first successful observation is
  # a silent baseline; later status/conclusion transitions are durable events.
  workflow_initialized="$(state_value '.workflowRunsInitialized // false')"
  while IFS= read -r run_row; do
    run_id="$(jq -r '.id // empty' <<<"$run_row")"
    [ -n "$run_id" ] || continue
    run_sha="$(jq -r '.head_sha // empty' <<<"$run_row")"
    api_run_prs="$(jq -c '[.pull_requests[]?.number] | map(select(. != null)) | unique' <<<"$run_row")"
    sha_run_prs="$(jq -c --arg sha "$run_sha" '[.[] | select((.headRefOid // "") == $sha or (.mergeCommit.oid // "") == $sha) | .number] | unique' <<<"$prs")"
    run_prs="$(jq -cn --argjson a "$api_run_prs" --argjson b "$sha_run_prs" '$a + $b | unique')"
    current_run="$(jq -c --argjson prs "$run_prs" '{
      id:(.id|tostring),
      name:(.name // ""),
      event:(.event // ""),
      status:(.status // ""),
      conclusion:(.conclusion // ""),
      headBranch:(.head_branch // ""),
      headSha:(.head_sha // ""),
      runAttempt:(.run_attempt // 0),
      createdAt:(.created_at // ""),
      updatedAt:(.updated_at // ""),
      url:(.html_url // ""),
      pullRequests:$prs
    }' <<<"$run_row")"
    old_run="$(state_value --arg id "$run_id" '.workflowRuns[$id] // empty')"
    if [ "$workflow_initialized" = "true" ]; then
      if [ -z "$old_run" ] || [ "$old_run" = "null" ]; then
        record_event "$(jq -c --argjson run "$current_run" '{kind:"ci_run_added",runId:$run.id,name:$run.name,event:$run.event,status:$run.status,conclusion:$run.conclusion,headBranch:$run.headBranch,headSha:$run.headSha,runAttempt:$run.runAttempt,createdAt:$run.createdAt,updatedAt:$run.updatedAt,pullRequests:$run.pullRequests,url:$run.url}' <<<"{}")"
      elif jq -n -e --argjson old "$old_run" --argjson new "$current_run" '$old.status != $new.status or $old.conclusion != $new.conclusion or $old.runAttempt != $new.runAttempt or $old.headSha != $new.headSha' >/dev/null 2>&1; then
        record_event "$(jq -cn --argjson old "$old_run" --argjson new "$current_run" '{kind:"ci_run_changed",runId:$new.id,name:$new.name,event:$new.event,status:$new.status,conclusion:$new.conclusion,headBranch:$new.headBranch,headSha:$new.headSha,runAttempt:$new.runAttempt,createdAt:$new.createdAt,updatedAt:$new.updatedAt,pullRequests:$new.pullRequests,previous:{status:$old.status,conclusion:$old.conclusion,runAttempt:$old.runAttempt,headSha:$old.headSha},url:$new.url}')"
      fi
    fi
    state_update --arg id "$run_id" --argjson run "$current_run" '
      .workflowRuns = (((.workflowRuns // {}) + {($id):$run})
        | to_entries
        | sort_by(.value.updatedAt // .value.createdAt // "")
        | .[-5000:]
        | from_entries)'
  done < <(jq -c '.[]' "$workflow_runs_file")
  if [ "$workflow_fetch_failed" -eq 0 ]; then
    state_update --arg now "$scan_started" '.workflowRunsInitialized = true | .lastWorkflowScanAt = $now'
  fi
  review_fetch_failed=0
  commit_fetch_failed=0

  while IFS= read -r row; do
    comment_pr="$(pr_number_from_url "$(jq -r '.issue_url // ""' <<<"$row")")"
    [ -n "$comment_pr" ] || continue
    jq -e --arg n "$comment_pr" '.[$n] == true' <<<"$all_pr_index" >/dev/null 2>&1 || continue
    id="$(jq -r '.id // empty' <<<"$row")"
    [ -n "$id" ] || continue
    issue_baseline="$(state_value '.lastProcessedIssueCommentId // 0')"
    if ! seen_id seenIssueCommentIds "$id" "$issue_baseline"; then
      record_event "$(jq -c --arg n "$comment_pr" '{kind:"issue_comment",pr:($n|tonumber),id:(.id|tostring),author:(.user.login // ""),createdAt:.created_at,body:(.body // ""),url:(.html_url // "")}' <<<"$row")"
      mark_seen seenIssueCommentIds "$id" lastProcessedIssueCommentId
    fi
  done < <(jq -c '.[]' "$issue_comments_file")

  while IFS= read -r row; do
    comment_pr="$(pr_number_from_url "$(jq -r '.pull_request_url // ""' <<<"$row")")"
    [ -n "$comment_pr" ] || continue
    jq -e --arg n "$comment_pr" '.[$n] == true' <<<"$all_pr_index" >/dev/null 2>&1 || continue
    id="$(jq -r '.id // empty' <<<"$row")"
    [ -n "$id" ] || continue
    review_baseline="$(state_value '.lastProcessedReviewCommentId // 0')"
    if ! seen_id seenReviewCommentIds "$id" "$review_baseline"; then
      record_event "$(jq -c --arg n "$comment_pr" '{kind:"review_comment",pr:($n|tonumber),id:(.id|tostring),author:(.user.login // ""),createdAt:.created_at,path:(.path // ""),line:.line,body:(.body // ""),url:(.html_url // "")}' <<<"$row")"
      mark_seen seenReviewCommentIds "$id" lastProcessedReviewCommentId
    fi
  done < <(jq -c '.[]' "$inline_comments_file")

  while IFS= read -r pr_row; do
    [ -n "$pr_row" ] || continue
    number="$(jq -r '.number' <<<"$pr_row")"
    head="$(jq -r '.headRefOid // ""' <<<"$pr_row")"
    updated="$(jq -r '.updatedAt // ""' <<<"$pr_row")"
    pr_state="$(jq -r '.state // ""' <<<"$pr_row")"
    merge_commit="$(jq -r '.mergeCommit.oid // ""' <<<"$pr_row")"
    [ "$number" != "null" ] || continue

    old_head="$(state_value --arg n "$number" '.openPulls[$n].head // ""')"
    old_updated="$(state_value --arg n "$number" '.openPulls[$n].updatedAt // ""')"
    commit_initialized="$(state_value --arg n "$number" '.pullCommits[$n].initialized // false')"
    if [ -n "$head" ] && [ -n "$old_head" ] && [ "$head" != "$old_head" ]; then
      record_event "$(jq -cn --arg n "$number" --arg old "$old_head" --arg new "$head" \
        '{kind:"head_changed",pr:($n|tonumber),previousHead:$old,head:$new,at:(now|todateiso8601)}')"
    fi

    # An unchanged closed/merged PR cannot have received a new comment. Keep
    # its metadata and known checks current without spending three API calls
    # on every historical PR on every poll. Open PRs are always scanned.
    if [ "$pr_state" != "OPEN" ] && [ -n "$old_updated" ] && [ "$updated" = "$old_updated" ] && [ "$commit_initialized" = "true" ] && [[ "$updated" < "$previous_scan" ]]; then
      old_checks="$(state_value --arg n "$number" '.openPulls[$n].checks // []' | jq -c '.' 2>/dev/null || printf '[]')"
      state_update --arg n "$number" --arg head "$head" --arg updated "$updated" --arg state "$pr_state" --arg merge "$merge_commit" --argjson checks "$old_checks" \
        '.openPulls[$n] = ((.openPulls[$n] // {}) + {head:$head,updatedAt:$updated,state:$state,mergeCommit:$merge,checks:$checks})
         | if $state == "MERGED" then .openPulls[$n].reviewState = "merged" else . end
         | if $state == "MERGED" or $state == "CLOSED" then
             .recentlyClosed[$n] = ((.recentlyClosed[$n] // {}) + {head:$head,state:(if $state == "MERGED" then "merged" else "closed" end),mergeCommit:$merge})
           else . end'
      continue
    fi

    should_scan_reviews=0
    if [ "$pr_state" = "OPEN" ] || [ "$updated" = "$previous_scan" ] || [[ "$updated" > "$previous_scan" ]]; then
      should_scan_reviews=1
    fi
    should_scan_commits=0
    if [ "$pr_state" = "OPEN" ] || [ "$updated" = "$previous_scan" ] || [[ "$updated" > "$previous_scan" ]] || [ "$commit_initialized" != "true" ]; then
      should_scan_commits=1
    fi
    if [ "$should_scan_reviews" -eq 1 ]; then
      reviews_file="$scan_dir/reviews-$number.json"
      if ! api_array "repos/$REPO/pulls/$number/reviews?per_page=100" > "$reviews_file"; then
        review_fetch_failed=1
        printf '[]\n' > "$reviews_file"
      fi
      submitted_review_baseline="$(state_value '.lastProcessedReviewId // 0')"
      while IFS= read -r row; do
        id="$(jq -r '.id // empty' <<<"$row")"
        [ -n "$id" ] || continue
        if ! seen_id seenReviewIds "$id" "$submitted_review_baseline"; then
          record_event "$(jq -c --arg n "$number" '{kind:"submitted_review",pr:($n|tonumber),id:(.id|tostring),author:(.user.login // ""),submittedAt:.submitted_at,state:(.state // ""),body:(.body // ""),url:(.html_url // "")}' <<<"$row")"
          mark_seen seenReviewIds "$id" lastProcessedReviewId
        fi
    done < <(jq -c '.[]' "$reviews_file")
    fi

    # Track every full commit SHA on open or recently changed PRs. The first
    # successful observation is a silent baseline so upgrading this monitor
    # does not replay historical commits as new feedback.
    if [ "$should_scan_commits" -eq 1 ]; then
      commits_file="$scan_dir/commits-$number.json"
      if ! api_array "repos/$REPO/pulls/$number/commits?per_page=100" > "$commits_file"; then
        commit_fetch_failed=1
        printf '[]\n' > "$commits_file"
      else
        known_global_commits="$(state_value '.seenCommitShas // []' | jq -c 'map(tostring)' 2>/dev/null || printf '[]')"
        known_pr_commits="$(state_value --arg n "$number" '.pullCommits[$n].shas // []' | jq -c 'map(tostring)' 2>/dev/null || printf '[]')"
        commit_shas="$(jq -c '[.[] | .sha? | select(type == "string") | select(length > 0)] | unique' "$commits_file" 2>/dev/null || printf '[]')"

        while IFS= read -r commit_row; do
          sha="$(jq -r '.sha // empty' <<<"$commit_row")"
          [ -n "$sha" ] || continue
          if jq -e --arg sha "$sha" 'index($sha) != null' <<<"$known_pr_commits" >/dev/null 2>&1; then
            continue
          fi
          if [ "$commit_initialized" = "true" ] && ! jq -e --arg sha "$sha" 'index($sha) != null' <<<"$known_global_commits" >/dev/null 2>&1; then
            record_event "$(jq -c --arg n "$number" \
              '{kind:"commit_added",pr:($n|tonumber),sha:(.sha // ""),author:(.author.login // .commit.author.name // ""),timestamp:(.commit.author.date // .commit.committer.date // ""),authoredAt:(.commit.author.date // ""),committedAt:(.commit.committer.date // ""),subject:((.commit.message // "") | split("\n")[0]),url:(.html_url // "")}' \
              <<<"$commit_row")"
          fi
          known_pr_commits="$(jq -c --arg sha "$sha" '. + [$sha] | unique' <<<"$known_pr_commits")"
          known_global_commits="$(jq -c --arg sha "$sha" '. + [$sha] | unique' <<<"$known_global_commits")"
        done < <(jq -c '.[]' "$commits_file")

        state_update --arg n "$number" --arg head "$head" --argjson shas "$commit_shas" \
          '.seenCommitShas = (((.seenCommitShas // []) + $shas | map(tostring) | unique)[-20000:])
           | .pullCommits[$n] = ((.pullCommits[$n] // {}) + {initialized:true,head:$head,shas:($shas[-5000:]),observedAt:(now|todateiso8601)})'
      fi
    fi

    old_checks="$(state_value --arg n "$number" '.openPulls[$n].checks // []' | jq -c '.' 2>/dev/null || printf '[]')"
    if [ "$should_scan_reviews" -eq 1 ]; then
      checks_raw="$(gh pr checks "$number" --repo "$REPO" --json name,state,workflow,link 2>/dev/null || true)"
      if jq -e 'type == "array"' <<<"$checks_raw" >/dev/null 2>&1; then
        checks="$(jq -c 'sort_by(.name)' <<<"$checks_raw")"
      else
        checks="$old_checks"
      fi
      # GitHub can return an empty result while checks are unavailable.
      if [ "$checks" = '[]' ] && [ "$old_checks" != '[]' ]; then
        checks="$old_checks"
      fi
    else
      checks="$old_checks"
    fi
    if [ "$checks" != "$old_checks" ] && [ "$old_checks" != '[]' ]; then
      record_event "$(jq -cn --arg n "$number" --argjson checks "$checks" '{kind:"ci_changed",pr:($n|tonumber),checks:$checks,at:(now|todateiso8601)}')"
    fi
    state_update --arg n "$number" --arg head "$head" --arg updated "$updated" --arg state "$pr_state" --arg merge "$merge_commit" --argjson checks "$checks" \
      '.openPulls[$n] = ((.openPulls[$n] // {}) + {head:$head,updatedAt:$updated,state:$state,mergeCommit:$merge,checks:$checks})
       | if $state == "MERGED" then .openPulls[$n].reviewState = "merged" else . end
       | if $state == "MERGED" or $state == "CLOSED" then
           .recentlyClosed[$n] = ((.recentlyClosed[$n] // {}) + {head:$head,state:(if $state == "MERGED" then "merged" else "closed" end),mergeCommit:$merge})
         else . end'
  done < <(jq -c '.[]' <<<"$prs")

  # Keep the scan start as the cursor. Comments created while this scan was
  # running are therefore included in the next incremental sweep. If a
  # submitted-review or commit fetch failed, retain the previous cursor so
  # that the affected PR is retried instead of silently losing its window.
  next_cursor="$scan_started"
  if [ "$review_fetch_failed" -ne 0 ] || [ "$commit_fetch_failed" -ne 0 ]; then
    if [ "$review_fetch_failed" -ne 0 ]; then
      log_message "monitor_warning: submitted-review fetch failed; retaining cursor $previous_scan"
    fi
    if [ "$commit_fetch_failed" -ne 0 ]; then
      log_message "monitor_warning: PR commit fetch failed; retaining cursor $previous_scan"
    fi
    next_cursor="$previous_scan"
  fi
  if [ "$workflow_fetch_failed" -ne 0 ]; then
    log_message "monitor_warning: workflow-run fetch failed; retaining workflow baseline/cursor for retry"
  fi
  state_update --arg now "$next_cursor" '.lastScanAt = $now'
  rm -rf "$scan_dir"
  scan_dir=""
  sleep "$INTERVAL"
done
