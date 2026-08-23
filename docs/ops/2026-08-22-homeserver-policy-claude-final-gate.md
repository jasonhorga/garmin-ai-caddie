## VERDICT: revise

Both drafts are substantially improved — the `/dev/shm` memory caveat, checksum-plus-test-restore gate, scheduler quiesce, Compose project-name pin, and the `:latest` rollback carve-out all read correctly now. Five concrete items remain.

**1. Caddy step contradicts itself: bind-mount change requires recreation, not reload**
`HOMESERVER_GARMIN_LAYOUT_DRAFT.md:63` says "update the container bind mount to the new absolute path; validate then reload", and `:114-115` says "reload (never an unplanned restart)". A Docker bind-mount source path cannot be changed on a live container — it requires `up -d`/recreate, i.e. a restart. As written the step is unexecutable. Specify a planned recreate window (and the expected downtime), or keep the existing mount source and defer the path change.

**2. `services/` mode `0750` vs. the Caddy container's runtime UID**
`:45-47` mandates `0750` for `services/`, but preflight only *records* the Caddy runtime user (`:88`). If that UID is not `jason` and not in the group, the bind-mounted Caddyfile becomes unreadable after the move. Add the decision rule — what mode/ownership applies when the runtime UID mismatches — rather than leaving it to discovery mid-migration.

**3. Log move (step 8) happens after schedulers are restored (step 6)**
`:110-116`: step 4 quiesces cron, step 6 restores it and runs a full cycle, step 8 then moves `aicaddie-sync*.log` and `prepare-recent.log`. A sync run in flight during step 8 holds the old inode, and the next run recreates the old path as a regular file, silently defeating the symlink. Step 8 needs its own quiesce-and-confirm-no-run-in-flight gate.

**4. Compose file location is undefined but gates the whole migration**
Step 2 (`:104-105`) makes pinning the Compose project name blocking ("Nothing moves before this check"), and policy §5.8 scopes the pin to "moving its compose directory" — but neither the target layout tree nor the migration table names where the compose file lives or whether it moves. If it stays in `/home/codex/garmin-ai-caddie`, say so and state that the pin is precautionary; if it moves, it needs a table row.

**5. The host policy file is never installed by the migration order**
`HOMESERVER_AI_OPERATIONS_DRAFT.md:22` requires every agent to read `/home/jason/HOMESERVER_AI_OPERATIONS.md` before any operation, and §10 authorizes creating "host policy files" — but migration steps 1–8 only create the empty tree (`:106`). Add an explicit step that installs the host policy file and the project `POLICY.md`/`README.md` shown at `:11-12`, and state what agents follow in the window before it exists.

Both drafts are coherent, internally consistent on the resolved items, and ready for the user to review.
