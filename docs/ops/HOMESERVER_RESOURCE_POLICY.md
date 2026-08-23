# Homeserver Resource Policy

This is the operational companion to the project `AGENTS.md`. It exists to
prevent another cycle of dozens of Claude directories filling the shared
homeserver.

## Ownership model

The homeserver is an execution plane, not a second source repository. Codex's
local checkout is the integration authority. Claude Fable and Opus are
consultants: they inspect a snapshot and return a report. They do not need a
long-lived implementation worktree merely to think or review.

## Allowed locations

| Work type | Location | Lifetime |
|---|---|---|
| Fable/Opus read-only review | `/dev/shm/aicaddie-review-<id>` or a dedicated temporary snapshot | 24 h |
| One delegated implementation | `/home/jason/codex-runs/aicaddie-impl-<id>` | 7 d after last activity |
| Persistent source/data | `/home/jason/garmin-ai-caddie-data/...` | retained |
| Runtime database/private data | named Docker volumes | retained and never pruned automatically |

The old `.claude/worktrees` directory is archival material, not a place to
start new sessions. New sessions must not add to it.

## Standard review flow

1. Codex records the commit SHA and review purpose.
2. Export a source-only snapshot (exclude `.git`, `.venv`, `node_modules`,
   build output, secrets and private data).
3. Run Fable or Opus against that snapshot with no write permissions.
4. Save the report and evidence in the canonical local repository.
5. Remove the temporary snapshot and close any tunnel/service created for it.

If a reviewer says it needs to edit code, that is no longer a review: Codex
must explicitly delegate one bounded implementation task and assign an expiry.

## Docker rules

- Keep one production image, one current candidate and one rollback image.
- Every temporary container/image/volume gets a session prefix and expiry.
- Use project-scoped `docker compose down --remove-orphans` for temporary
  stacks. Use `--volumes` only for a stack whose data is explicitly marked
  disposable.
- Run `docker builder prune --force --filter until=168h` weekly, after checking
  that no build is active. Never run global `docker system prune`.
- Named volumes are data, not cache. They require a separate manifest and
  approval before removal.

## Retention classes

The word "old" is not a deletion rule. Every artifact must be assigned one of
these classes before it is created:

| Class | Keep | Examples | Default action |
|---|---|---|---|
| **P0 protected** | Indefinitely, with a restorable backup | committed/pushed source, raw Garmin/user round data, databases, credentials, migration/restore scripts, production data | Never prune automatically |
| **P1 release evidence** | Until the release gate is closed, then archive per release policy | approved screenshots, test reports, SHA/digest manifests, IPA/dSYM, rollback notes, incident logs | Keep at least the current and previous release |
| **P2 temporary work** | Until its TTL expires | Fable/Opus snapshots, one delegated implementation worktree, stopped test containers, preview servers, tunnels | Owner deletes and records the result |
| **P3 rebuildable cache** | Only while it saves more time than disk | BuildKit layers, `.venv`, `node_modules`, Swift `DerivedData`, browser/package caches | Scheduled or capacity-triggered pruning |

The class follows the data, not the tool that created it. A file produced by
Claude can be P0 (for example, a unique Garmin fixture); a Docker object can
be P0 (a database volume) or P3 (a build layer).

## Source snapshots and GitHub are not interchangeable

GitHub is a source backup only after all of the following are true:

1. The intended commit is pushed and its SHA is recorded (prefer a release tag
   for a rollback point).
2. `git status --short` is empty, or every local change has been committed,
   exported as a reviewed patch, or copied to a persistent data directory.
3. Untracked and ignored files have been classified. This includes fixtures,
   approved images, generated contracts, Garmin raw/decoded data and local
   migration material.
4. A clean checkout from the remote can be restored and its relevant checks
   pass. A remote repository does not replace a backup of user data or secrets.

An old source snapshot may therefore be removed only after a manifest records
its path, size, source SHA (if any), unique files and exported patch/evidence.
If it is byte-for-byte redundant with a tagged commit, delete the directory and
keep the manifest. If it contains an uncommitted delta, preserve that delta
first. If its purpose is visual or forensic evidence, extract the evidence into
P1 storage instead of retaining an entire worktree.

The existing Claude snapshot pile is not evidence that all 79 directories are
valuable. It is evidence that the lifecycle was wrong: read-only reviews were
given persistent worktrees and private environments. New Fable/Opus reviews
must use one source-only snapshot under `/dev/shm` with a 24-hour TTL. They do
not create `.venv`, install dependencies, build images or start services.

## Docker deletion gates

Temporary test containers are normally P2 and may be removed after their exit
code, image digest, logs and creation session are recorded. Before removing a
container, check its mounts: deleting a container does not delete its named
volume, but a later volume prune can destroy the data.

An image may be removed only when it is not used by a running container, is not
the production/current-candidate/rollback image, and can be rebuilt from a
recorded source SHA, lockfiles, build arguments and CI evidence. Keep one
rollback image even when the current image is healthy. BuildKit cache is the
normal first cleanup target; it is not a substitute for image or data
retention.

Never use a global `docker system prune`, `docker volume prune`, or an
unreviewed `rm -rf` for this project. Cleanup must use a generated allow-list
and a manifest stored outside the disposable worktree.

## Other resources covered by the same policy

- Swift/Xcode `.build`, `DerivedData`, archives, IPA and dSYM/symbol maps;
- `node_modules`, Python/uv/pip caches, Playwright browser binaries and
  screenshots/videos;
- stopped containers, dangling images, BuildKit cache, anonymous volumes and
  preview databases;
- tmux sessions, dev servers, cloudflared/Tailscale tunnels and port forwards;
- Garmin raw downloads, decoded DSKIMG/topo/geometry/course-package caches,
  generated tiles and map evidence;
- PostgreSQL/private volumes, backups, sync logs, CI artifacts, cookies,
  tokens and `.env` files.

Generated output is not automatically disposable: a map corpus, user round or
approved screenshot can be the only reproducible evidence. Classify it before
pruning; keep caches centrally and keep irreplaceable inputs in the persistent
project-data directory.

## Session close-out contract

Every remote session must finish with a short record containing:

```text
owner/session:
purpose:
source_sha:
created_resources:
protected_resources:
deletion_allowlist:
expires_at:
cleanup_result:
```

The creator owns cleanup of P2/P3 resources. Codex remains the integration
owner and is the only default agent allowed to modify the canonical checkout,
merge patches, publish artifacts or decide that a release/rollback point is
safe to discard.

## Monitoring and stop conditions

At the beginning and end of every heavy session record:

```text
df -hP /
docker system df
tmux list-sessions
docker ps -a
```

The operator must stop creating heavy work below 10 GiB free and must not
start a build below 5 GiB. A weekly report should include worktree count,
`.venv` count, Docker cache, stopped containers and dangling volumes. The
report is diagnostic only; deletion always uses a reviewed allow-list.

## Current exception

The existing 79 snapshots under
`/home/jason/codex-runs/garmin-ai-caddie-p0-watch-20260822/.claude/worktrees`
are temporarily retained while their unique deltas, fixtures and evidence are
classified. They are not a permanent retention commitment. Their old `.venv`
directories were removed on 2026-08-22 under an explicit allow-list. After the
source/fixture manifest is reviewed, redundant snapshots may be deleted in
batches while the manifest and any exported patch remain in persistent data.
No new session may repopulate that tree.

## Concrete Capacity Budgets

The 2026-08-22 audit found that the expensive resources were duplicated
environments, not the source files themselves: fourteen old run-local Python
environments occupied about 6.6 GiB by `du` (shared layers meant roughly 3 GiB
was released from the root filesystem), while a single untagged Docker image
and BuildKit cache consumed another roughly 0.9 GiB. To prevent recurrence:

One additional operational cause was found: several bind-mounted build
directories were written by `root` from inside a container. That is why a
normal `jason` cleanup could not remove some old `.venv` files. Builds must run
with an explicit matching UID/GID (or in an isolated volume); a cleanup that
needs elevated rights must still use the generated allow-list and record the
exact paths, never fall back to a broad privileged `rm`.

- `/home/jason/codex-runs` is a staging area, not a source archive. A review
  snapshot has a 24-hour TTL; an implementation snapshot has a seven-day TTL.
  The owner must either export a patch/evidence bundle or remove it at expiry.
- No session may run `uv sync`, `python -m venv`, `npm install`, or Xcode build
  inside every copied snapshot. Use the shared remote environment or one
  explicitly named implementation directory. A `.venv` under a review tree is
  a policy violation.
- Shared re-creatable caches are capped operationally at about 1 GiB for pnpm,
  500 MiB for uv/pip, 300 MiB for npm, and one Playwright browser installation.
  Prune only the cache class, never the project data directory.
- Docker keeps one production API, one current candidate, one review image
  while it is actively inspected, and one API rollback; sync keeps current plus
  one rollback. Every other image needs a manifest and explicit deletion
  decision. A dangling image with no container reference is safe to remove
  after its digest is recorded.
- `docker builder prune --force --filter until=168h` is the scheduled cache
  cleanup. `docker system prune` and `docker volume prune` remain forbidden.
- System journal is shared with other projects. Do not vacuum it from a
  project session; configure and approve a host-level retention limit
  separately. Until then it is reported, not silently deleted.
- Cleanup manifests are small but must not grow without bound: keep the
  current run plus the previous three audit manifests, and archive/delete
  older diagnostic-only manifests after their retention window. Never store
  raw `docker inspect` environment output in a manifest.

The read-only inventory helpers are `ops/audit_homeserver_resources.sh`,
`ops/audit_homeserver_worktrees.sh`, and
`ops/audit_homeserver_codex_runs.sh`. They write manifests outside disposable
worktrees and never delete resources.
