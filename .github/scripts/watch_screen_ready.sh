#!/usr/bin/env bash
# Gate a Watch runtime screenshot on the routed `-uitest-screen` view having rendered.
#
#   watch_screen_ready.sh reset <udid> <bundle-id>                 # before each launch
#   watch_screen_ready.sh wait  <udid> <bundle-id> <mode> [secs]   # after the launch
#
# WatchUITestRoot (DEBUG) writes Documents/uitest-screen-rendered ("screen=<mode>") when the routed
# view appears, and Documents/uitest-screen-unknown for an unrouted mode. `wait` returns after a
# short settle once the marker names this mode, and fails on timeout or an unknown screen, so a
# launch logo can no longer pass as a screenshot (live Native 37426762320, score-recommendation).
set -euo pipefail

action="${1:?usage: watch_screen_ready.sh reset|wait <udid> <bundle-id> [mode] [secs]}"
udid="${2:?udid required}"
bundle_id="${3:?bundle id required}"
container="$(xcrun simctl get_app_container "$udid" "$bundle_id" data)"
rendered="$container/Documents/uitest-screen-rendered"
unknown="$container/Documents/uitest-screen-unknown"

case "$action" in
  reset)
    rm -f "$rendered" "$unknown"
    ;;
  wait)
    mode="${4:?mode required}"
    timeout_s="${5:-30}"
    deadline=$((SECONDS + timeout_s))
    while ((SECONDS < deadline)); do
      if [[ -f "$unknown" ]]; then
        echo "::error::Watch screen '$mode' is not routed by WatchUITestRoot ($(cat "$unknown"))"
        exit 1
      fi
      if grep -qx "screen=$mode" "$rendered" 2>/dev/null; then
        # The marker is written on appear; give SwiftUI a moment to commit the first frame.
        sleep 2
        exit 0
      fi
      sleep 0.5
    done
    echo "::error::Watch screen '$mode' did not render within ${timeout_s}s"
    exit 1
    ;;
  *)
    echo "unknown action: $action" >&2
    exit 2
    ;;
esac
