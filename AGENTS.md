# Garmin AI Caddie Agent Policy

This file is the project-specific execution policy. It supplements the
shared `/home/ubuntu/HOMESERVER.md` runbook. It is intentionally short: it
defines ownership and resource lifetime, not a new product plan.

## 1. Agent roles

- **Codex (primary):** owns product decisions in scope, repository edits,
  integration, verification, deployment and release claims.
- **Fable:** design exploration, S70 comparison and adversarial product
  reasoning. Read-only by default. Fable output is advice/evidence, not an
  implementation branch.
- **Opus:** bounded code review and correctness audit. Read-only by default;
  it may not create a candidate service, install dependencies or modify the
  canonical checkout.
- **Claude Code implementation session:** allowed only when Codex explicitly
  delegates a bounded coding task. Its result must return as a patch/commit
  to Codex; the session is not a second owner.

## 2. Review versus implementation

- A Fable/Opus review must use a read-only snapshot or a checked-out commit
  under `/dev/shm` (or another explicitly temporary directory), with
  `.venv`, `node_modules`, build products and credentials excluded.
- Do **not** create a persistent Git worktree for a read-only review.
- A coding worktree is one named directory per delegated task, with an owner,
  purpose, creation time and expiry time recorded before it starts.
- At most one active Garmin implementation worktree and one active review
  snapshot may exist at a time. Parallel opinions use the same snapshot.
- Never install a private `.venv` in every worktree. Use the shared remote
  environment/cache or a named Docker image.

## 3. Lifetime and cleanup

- Review snapshots expire after 24 hours; implementation worktrees expire
  seven days after the last activity unless Codex explicitly renews them.
- Temporary Docker containers, anonymous volumes, preview servers and
  tunnels must carry the same session name and be removed by the creator.
- Persistent source data and user data live under the project data directory,
  never only inside `codex-runs`, a Git worktree or `/tmp`.
- Cleanup is allow-list based. Never use global `git clean`, `docker system
  prune`, volume prune, or broad `rm -rf` for this project.

## 4. Capacity gates

- Run a read-only capacity check before any remote build, browser suite or
  image generation.
- At `<15 GiB` free: no new parallel review/build session.
- At `<10 GiB` free: stop starting heavy work and produce a cleanup list.
- At `<5 GiB` free: only recovery/cleanup work is allowed.
- BuildKit cache may be pruned on a schedule; containers, images, named
  volumes and source worktrees require an explicit manifest and approval.

## 5. Persistent execution state

Read [`docs/operations/PROJECT_STATE.md`](docs/operations/PROJECT_STATE.md)
before resuming work after a context compaction or session restart. It is the
durable live source of truth for the active queue, completed evidence, blockers,
and next action. Keep long reviews and historical plans as reference; do not
recreate a competing master checklist in chat.

## 6. Required handoff

Every delegated session must report:

1. read-only or modifying;
2. exact snapshot/worktree path;
3. resources created (containers, volumes, ports, tunnels, caches);
4. expiry and cleanup result;
5. commit/patch or review artifact returned to Codex.

No review is complete until its resource list is closed or explicitly
handed back to Codex.
