You are performing a read-only operational review of the two draft policy
files in this directory. Do not edit files, start services, run Docker cleanup,
or inspect secrets.

Read:
- HOMESERVER_AI_OPERATIONS_DRAFT.md
- HOMESERVER_GARMIN_LAYOUT_DRAFT.md

The previous review focused too narrowly on migration data-loss hazards. This
review must focus first on resource validity and lifecycle:

1. Which large Homeserver resources are still valid, which are candidates for
   removal, and what evidence is required before removing them.
2. How detached tmux sessions, review APIs, Cloudflare/Tailscale tunnels,
   preview servers, Docker containers, and their directories get an owner,
   URL/route, last-use timestamp, expiry, and cleanup decision.
3. How all AI tools and SSH sessions avoid placing generated files at the
   /home/jason top level, while preserving unrelated projects.
4. How the rules distinguish a review transcript from a source worktree,
   evidence archive, public demo, persistent data, and a running service.
5. Whether the proposed 24-hour TTL and >100 MiB audit rule are practical,
   and whether active traffic can be used as the sole reason to retain a
   service.

Known facts to assess, without inventing more:
- aicaddie-review-f463725-tunnel has run since 2026-08-01, exposes a quick
  Cloudflare URL, proxies 127.0.0.1:39022 to container
  aicaddie-review-real-f463725-api, and the container mounts the production
  private volume. The API and tunnel currently return 200 and recent requests
  exist.
- sat-coach-review-settings-20260822 is another project's detached session;
  its Node API has recent requests and uses /dev/shm. Garmin cleanup must not
  stop it.
- /home/jason/codex-runs is about 6.4 GiB; /home/jason/demos about 271 MiB;
  several Garmin run directories are 0.5-1.0 GiB. The user previously said
  not to delete the Claude worktrees before content-level audit.
- root-level /home/jason contains Garmin scripts/logs/Caddy backups mixed with
  unrelated project files and host dotfiles.

Return a concise Markdown report with exactly these headings:
1. Verdict
2. Valid large resources and evidence
3. Safe cleanup candidates and blockers
4. Required directory/session rules
5. Must-fix wording changes
6. User decisions

Do not recommend deleting a resource solely because its name contains review,
because it is detached, or because it is old. Distinguish a recommendation
from an action; nothing is authorized for deletion by this review.
