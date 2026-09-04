# Claude Code project rules

Read `AGENTS.md` before taking any action. Codex is the primary owner of
this repository.

For Fable or Opus review/brainstorm tasks:

- treat the checkout as read-only;
- do not invoke a worktree-creation skill or create a persistent directory
  under `.claude/worktrees`;
- inspect a source-only snapshot under `/dev/shm` and return a report;
- do not install dependencies, build Docker images, start services, or edit
  files unless Codex explicitly reclassifies the task as one bounded
  implementation task.

For an explicitly delegated implementation task, use one named temporary
worktree with an expiry and report every resource created. Never create a
per-worktree `.venv`; use the shared remote environment/cache.
