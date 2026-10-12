# Watch #417 feedback collection recovery

The repository's installed gh-feedback instance was running without
`GH_FEEDBACK_EXTENDED_EVENTS=1`. Its default stream includes PR comments but
excludes comments on plain issues, explaining why #417's widened audit request
did not wake the project waiter. Both owner comments and the later touch-probe
request were read manually and processed; the audit evidence remains on #417.

On 2026-10-12 at05:27 UTC Codex enabled that existing supported option for the
`garmin-ai-caddie` instance. The configuration diff is exactly one added line;
the original file is retained for recovery. No shared-toolkit code, systemd
timer, event file or feedback cursor was replaced, and no second monitor or
persistent tmux was started. The existing collector ran once with `--force`,
exited0 and completed its silent extended-event baseline. One bounded catch-up
read accounts for comments arriving during that baseline; it is not a polling
loop. Future plain-issue delivery remains to be confirmed from an actual event.

The repository keeps `ops/wait_for_conclusion.sh` and the same-turn blocking
wait method. Its feedback mode accepts extended kinds. A plain-issue event's
raw JSON carries `issue`, rather than `pr`; the legacy one-line summary can
label it `prall`, so identify/deduplicate the item from the completed wait log.
The shared waiter was not substituted. Avoid bookkeeping-only commits or any
CI-result feedback loop.

Persistent operations record:
`/home/jason/garmin-ai-caddie-data/operations/watch417-feedback-20261012/`.
It contains the before configuration, resource/change manifest and collector
baseline log. The current target is
`/home/jason/.config/gh-feedback/garmin-ai-caddie.env`.
To reverse the option, restore the recorded before file to that exact target;
do not reset any event stream or reader cursor. The flag is project-owned
configuration, not an expiring preview resource. No credentials were copied.
