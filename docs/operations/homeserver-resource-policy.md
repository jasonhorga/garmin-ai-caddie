# Homeserver Resource Policy

This project uses the homeserver as a shared execution and hosting machine.
The policy applies to Codex, Claude Code, Fable, Opus, Gemini, CI helpers, and
any automation that connects over SSH.

## Ownership and paths

- Persistent Garmin data, evidence, manifests, and operational reports live
  under `/home/jason/garmin-ai-caddie-data/`.
- A disposable implementation checkout may live under
  `/home/jason/codex-runs/<project>-<session>-<date>/`.
- Read-only review snapshots expire after 24 hours. Implementation snapshots
  expire seven days after their last activity unless explicitly renewed.
- Never put the only copy of source, credentials, or user data in
  `codex-runs`, `/tmp`, `/dev/shm`, a container layer, or a worktree.
- Use one shared remote environment or image. Do not create a private `.venv`
  in every worktree. Rebuildable `node_modules`, `.venv`, `__pycache__`, build
  output, and `.codex-tmp` are disposable and must not be treated as source.

## Shared Python runtime

The homeserver uses one shared, lock-backed runtime for this repository. The
preferred implementation is the project API image: its `/app/.venv` is used as
the read-only Python runtime while a source checkout is mounted separately. If
an image cannot be used, the only permitted host virtualenv is
`/home/jason/garmin-ai-caddie-data/venvs/garmin-ai-caddie-ci`; it is rebuilt
from the committed lockfile and is never copied into a worktree.

Rules for every Codex, Claude, Gemini, or SSH session:

- Do not run `python -m venv`, `uv venv`, `uv sync`, or dependency installers
  inside a review snapshot or implementation worktree.
- Do not mutate the shared runtime concurrently. The implementation owner
  acquires the project environment lock before a dependency rebuild; reviews
  use the immutable image or read-only packages.
- Rebuild only when `pyproject.toml`, `uv.lock`, the base image, or the Python
  ABI changes. Record the source SHA and environment/image identifier in the
  session handoff.
- Every test handoff must state which shared image or environment was used. A
  temporary environment is allowed only for a bounded documented fallback and
  must be removed in the same session.

This keeps dependencies reusable without allowing one branch's editable
installation to silently change another branch's tests.

## Capacity gates

- Check `df -h`, `free -h`, `swapon --show`, running processes, containers,
  tmux sessions, and listeners before heavy work.
- At 15 GiB free, do not start parallel builds or reviews.
- At 10 GiB free, stop new heavy work and produce an allowlist cleanup.
- At 5 GiB free, only recovery and cleanup are permitted.
- Do not run recursive whole-home `du`/`find` scans over SSH. Prefer Docker
  accounting, bounded metadata queries, and explicit paths; every remote
  command must terminate with the SSH session or be intentionally supervised.

## Temporary resources

- Put project temporary files in `/home/jason/garmin-ai-caddie-data/tmp/` or a
  uniquely named `/tmp/aicaddie-<session>-*` directory.
- `/dev/shm` is for short-lived files only; remove them at the end of the run.
- Name every tmux session, port, container, volume, and tunnel with the same
  session identifier. The creator records creation, owner, expiry, and cleanup
  in a manifest.
- Never use global `docker system prune`, global volume prune, `git clean -fdx`,
  or broad `rm -rf`. Cleanup is always an explicit allowlist.

## Docker and logs

- Keep the current production image, one verified rollback image, the sync
  image used by cron, and all named production volumes.
- BuildKit cache and unreferenced test images may be pruned only after a
  before/after manifest. Anonymous volumes are removable only when they have
  zero links and no owner.
- Container restart policies must be bounded (`on-failure:N`) for application
  services. A dependency readiness check and a migration lock must run before
  application startup. JSON logs are capped and rotated.
- The homeserver currently has `/swap.img` plus `/swap-extra.img` (8 GiB
  total) with `vm.swappiness=20`. Swap is an outage buffer, not a substitute
  for bounded retries or capacity cleanup.

## Required handoff

Every agent reports the exact snapshot path, resources created, expiry, cleanup
result, and commit or artifact returned. Before deleting anything, write a
timestamped manifest under
`/home/jason/garmin-ai-caddie-data/cleanup-manifests/` and verify no process or
open file references the allowlist.
