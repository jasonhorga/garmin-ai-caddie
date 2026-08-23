You are performing a read-only operational review. Do not edit files, create
services, install dependencies, run Docker cleanup, or start a server.

Read these two drafts in /dev/shm/aicaddie-policy-review-20260822:

- HOMESERVER_AI_OPERATIONS_DRAFT.md
- HOMESERVER_GARMIN_LAYOUT_DRAFT.md

Review them as a Homeserver administrator responsible for a shared machine
used by Codex, Claude/Fable/Opus, Gemini, and multiple unrelated projects.
Focus on concrete failure modes: data loss, broken cron/systemd/Docker/Caddy
mounts, symlink traps, permissions, secrets, disk pressure, stale worktrees,
and rules that an AI or plain SSH session cannot realistically discover.

Known current facts to account for:

- The root disk is 98 GiB with about 39 GiB free.
- Five Garmin-related Docker containers are running: production API, current
  candidate API, a review API, Caddy, and PostgreSQL.
- The current cron invokes /home/jason/aicaddie-sync.sh hourly and
  /home/jason/prepare-recent.sh hourly.
- Caddy currently bind-mounts /home/jason/aicaddie-web.Caddyfile and a
  protected /home/codex checkout.
- Garmin persistent data and production backups must not be lost.
- Other projects under /home/jason must not be moved or deleted.
- The user explicitly wants to review and approve the rules before any host
  migration or deletion.

Return a concise but rigorous Markdown report with these headings:

1. Verdict: approve as-is, approve with changes, or reject.
2. Must-fix before user approval (ordered by severity).
3. Recommended but optional improvements.
4. Safe first migration sequence.
5. Docker candidates that are actually safe, unsafe, or need evidence.
6. Exact wording/path changes to make in the drafts.
7. Questions the user must decide (keep this short).

Do not invent facts. Distinguish observations from assumptions. The purpose is
to help the user see the draft before it is applied.
