# Homeserver AI Operations Policy (Draft)

Status: **draft for Claude review and user approval**. Nothing in this file
changes the Homeserver until the user approves the draft and a migration
manifest is generated.

This is a host-level policy for Codex, Claude Code/Fable/Opus, Gemini, other
AI tools, and human SSH sessions acting on their behalf. It applies to every
project under `/home/jason`, not only Garmin AI Caddie.

## 1. Ownership and source of truth

- The Homeserver is an execution and hosting plane, not a second uncontrolled
  source repository.
- Every project gets one explicit root: `/home/jason/<project>`.
- A project root owns its persistent data, evidence, service definitions,
  logs, manifests, and temporary work. Other projects are out of scope.
- The canonical Garmin root will be `/home/jason/garmin-ai-caddie`.
- GitHub is a source backup only after the intended commit, untracked files,
  fixtures, and generated evidence have been classified. It is not a backup
  for user data, databases, credentials, or Garmin raw downloads.
- Before any operation, an agent must read `/home/jason/HOMESERVER_AI_OPERATIONS.md`
  and the nearest project `AGENTS.md`/tool-specific policy file.
- The Garmin code checkout is a sanctioned exception to the project-root rule:
  the current checkout is `/home/codex/garmin-ai-caddie`; it must not be copied
  into every review directory.

## 2. Required session contract

Every AI or SSH session that creates anything must declare these fields in a
small manifest before starting:

```text
owner:
session_id:
project:
purpose:
source_sha_or_input:
location:
created_at_utc:
expires_at_utc:
```

The session must use a unique prefix in temporary directory names, Docker
objects, tmux sessions, ports, and review URLs. At close-out it must report:

```text
created_resources:
protected_resources:
deletion_allowlist:
cleanup_result:
```

No agent may silently leave a process, tunnel, container, volume, worktree, or
large cache behind.

Long-running resources are also indexed in the host-wide registry at
`/home/jason/.local/share/homeserver/resource-registry.tsv`. The registry is
cross-project and is not a Garmin data store. It is the starting list for
audits; a missing row is never, by itself, grounds to stop a resource.

### 2.1 Long-running sessions and public review endpoints

- A detached `tmux` session is not proof that work is still needed. Every
  preview, tunnel, review API, and background service must record `owner`,
  `project`, `purpose`, `upstream`, `public URL or route`, `created_at_utc`,
  `last_verified_use_utc`, and `expires_at_utc` in its session manifest.
- A review preview or tunnel has a 24-hour default TTL after its last verified
  use. It may be renewed only by writing a new expiry and recording why the
  endpoint is still needed. A health check alone does not renew it; a real
  review request or an explicit owner confirmation does.
- Before stopping one, check its route, upstream health, recent access, and
  process/container ownership. Stop only the listed session-owned process and
  its disposable logs/tmp data. Never stop a different project's session from
  a Garmin cleanup.
- An active service that mounts P0 data is protected even when its name contains
  `review`; it requires a separate replacement/rollback change window.
- A running service's protection class is the maximum of its own class and the
  class of every data path or volume it mounts. A review service with a P0
  read-write mount is therefore P0-protected until its exposure and
  replacement/retirement decision are complete.
- Active traffic is necessary but not sufficient evidence that a resource is
  still needed. Health checks, edge probes, scanners, and stale browser tabs
  can all produce traffic. Conversely, no traffic is not sufficient grounds to
  stop a service that mounts P0 data.
- If `last_verified_use_utc` cannot be measured reliably, escalate to the
  owner; do not silently renew or expire the resource.

The host registry row for a long-running resource must include:

```text
owner, project, purpose, resource_kind, location,
route_class (public-unauthenticated | public-authenticated |
             tailnet-private | localhost-only),
public_url_or_route, upstream_and_port, resource_paths, mounts_and_mode,
created_at_utc, last_use_evidence_source, last_verified_use_utc,
expires_at_utc, disposition (keep | replace | retire | convert | awaiting-owner)
```

Existing resources must be retro-registered by an explicit adoption date.
`last_verified_use_utc` must identify its evidence source (API access log,
container log, proxy log, or owner confirmation); an HTTP 200 alone is not
enough to establish continuing need. Tailscale and Cloudflare routes are both
recorded by `route_class`; a public unauthenticated route must never be added
for a new service that mounts P0 data.

## 3. Allowed locations

For a project named `garmin-ai-caddie`:

```text
/home/jason/garmin-ai-caddie/
  persistent/       P0 user/source/runtime data
  evidence/         P1 approved reports, screenshots, release evidence
  archives/         verified compressed historical bundles
  manifests/        inventories, checksums, cleanup allow-lists
  services/         checked-in service/config entrypoints
  logs/             bounded operational logs
  incoming/         untrusted input awaiting classification
  bin/              read-only audit/maintenance helpers
  tmp/              disposable session work only
```

`tmp/` must contain only named subdirectories such as `sessions/`, `reviews/`,
`runs/`, `builds/`, `downloads/`, `extraction/`, `docker/`, and `tunnels/`. Every child
must include a session ID and expiry. `/dev/shm/<project>-review-<id>` is the
preferred location for small, read-only Claude/Gemini review snapshots. It is
a RAM-backed tmpfs, not a cleanup mechanism: a rarely rebooted host will keep
the files, and they consume memory. Before creating one, check both
`df -h /dev/shm` and `free -h`; cap a review snapshot at 2 GiB (or 20% of
`MemAvailable`, whichever is smaller), never create one while a browser suite
or DB-heavy job is running, delete it at the end of the review, and enforce the
24-hour TTL with an explicit allow-list. Check the aggregate `/dev/shm` usage
across all projects before creating a snapshot; the per-snapshot cap is not a
host-wide budget. `/dev/shm` is cleared on reboot but
must never hold the sole copy of anything. Larger or persistent material
belongs under the project root. `/tmp` is for small OS-level scratch files
only, never the sole copy of project data.

Other projects use the same shape under their own root. Do not put one
project's files in another project's `tmp` directory.

The `/home/jason` top level is not a scratch area. It may contain dotfiles,
host configuration, and one root directory per project. New generated logs,
screenshots, review files, scripts, archives, and run outputs must go under
the owning project root. Existing loose files are classified by owner and
reference before moving; no bulk `mv` or name-based cleanup is allowed.

Before the first migration, freeze a dated, read-only inventory of every
top-level entry with one of `Garmin-owned`, `known-unrelated`, or
`unclassified`. A report-only detector compares future inventories with this
baseline and reports new top-level files/directories. Every session must change
directory to its declared `location` before creating anything; agents must not
write project output through a relative path from `$HOME`, `~/.cache`,
`~/.config`, or `~/.local`.

## 4. Retention classes

The class follows the data, not the tool that produced it:

| Class | Keep rule | Examples | Automatic deletion |
|---|---|---|---|
| P0 protected | Indefinitely; verify a restorable backup | Git source/deltas, Garmin raw/decoded inputs, user rounds, databases, credentials, migration/restore scripts, production backups | Never |
| P1 release evidence | Current and previous release; archive older approved evidence | approved screenshots, test reports, IPA/dSYM, digests, rollback notes, incident records | Never without release decision |
| P2 temporary work | Review 24 h; implementation worktree 7 d after last activity; localhost preview 24 h; authenticated/Tailnet-private preview 72 h; public unauthenticated preview 24 h plus explicit owner renewal; stopped test container 24 h | read-only snapshots, bounded implementation worktrees, test containers, preview artifacts | Owner removes from an explicit allow-list |
| P3 rebuildable cache | Keep only while useful; review weekly and under disk pressure | BuildKit, `.venv`, `node_modules`, DerivedData, package/browser caches | Class-specific prune only |

An artifact may be promoted to P0/P1 when it contains unique data or approved
evidence. “Old” alone is never a deletion reason.

TTL enforcement is initially report-only: a read-only audit lists expired P2/P3
items, and an owner must approve the generated allow-list. An item expired for
seven days is escalated to the owner/user with a named due date and disposition.
A future scheduled cleaner may delete only that allow-list; it must never infer
deletion from a directory name or age alone. Read-only reviews record their
snapshot path and expiry in the review report rather than creating a persistent
implementation manifest.

## 5. Docker rules

1. Before a build or cleanup, record `df -hP /`, `docker system df`, `docker
   ps -a`, images, volumes, and active builds in a manifest.
2. Keep exactly the data needed for operation: production image, current
   candidate, one rollback image, and (only while being reviewed) one review
   image. Sync keeps current plus one rollback.
3. A stopped **stateless** test container is P2. Remove it only after recording
   its exit code, logs, image digest, mounts, source SHA, and rebuild command.
4. A named volume is data until proven otherwise. Never use `docker volume
   prune` or delete a named volume automatically. PostgreSQL, Garmin private
   data, and browser login profiles are protected.
5. An image is removable only when no container references it, it is not a
   production/candidate/rollback image, no other project's compose file or
   script references its tag, and the source SHA and lockfiles can rebuild it.
   Record the digest before removal.
6. BuildKit cache is the first cleanup target: use a dated, age-filtered
   `docker builder prune`, only after confirming no build is running and no
   other project is relying on the cache. This is a host-wide action.
7. Never run global `docker system prune`, `docker volume prune`, or an
   unreviewed privileged `rm -rf` on this host.
8. Pin every Compose project name (`name:` or an explicitly recorded
   `COMPOSE_PROJECT_NAME`) before moving its compose directory. Confirm the
   existing named volume IDs remain attached after the pin. `:latest` is never
   the sole rollback reference or cron target; promotion must record an
   immutable tag and digest first.

## 6. Worktrees and reviews

- Codex is the integration owner for Garmin.
- Claude/Fable/Opus/Gemini reviews are read-only by default and share one
  source-only snapshot. They do not create persistent worktrees, install a
  private environment, build images, or start services merely to review.
- A coding worktree requires an explicit owner, task, source SHA, expiry, and
  return patch/commit. At most one active Garmin implementation worktree is
  allowed unless the user approves more.
- Before deleting an old snapshot, classify uncommitted deltas, unique
  fixtures, and evidence; export a patch/archive and keep its manifest.
- A run directory larger than 100 MiB is audited as a unit. Its contents are
  split into source, unique evidence, disposable build output, and caches
  before any deletion. A directory containing Claude worktrees is protected
  until that content-level audit is complete, regardless of its age or name.
- Review transcripts and review worktrees are separate resources. Deleting a
  transcript does not authorize deleting its source snapshot, and deleting a
  snapshot does not authorize deleting the transcript or its evidence.

Here, a `run directory` means either `/home/jason/codex-runs/<run>` or a
project-owned `tmp/runs/<session-id>` tree, including its nested build/evidence
subdirectories but excluding Docker named volumes and the shared `demos` tree.
The first pass for every run over 100 MiB is machine-generated (source SHA,
Git diff/status, file-type buckets, cache/build detection, active references).
Human review is required only for uncommitted deltas or unique
non-rebuildable material.

The retention class of data and the lifecycle of a running service are separate
axes:

| Kind | Lifecycle source | Deleting it does not authorize |
|---|---|---|
| Review transcript | decision/release record | deleting its source snapshot |
| Source worktree/snapshot | TTL plus delta audit | deleting transcript/evidence |
| Evidence archive | release decision | deleting persistent data |
| Public demo | live URL retirement | deleting authoritative copy |
| Persistent data | never automatic | deleting siblings |
| Running service | registry disposition plus mounted data | deleting image/volume/data |

New review services must not mount P0 data read-write. Existing mount mode must
be recorded before a keep/replace/retire decision.

## 7. Capacity gates

Check capacity before and after heavy work:

| Free root disk | Rule |
|---:|---|
| `>= 15 GiB` | normal work |
| `< 15 GiB` | no parallel heavy jobs; cleanup plan required |
| `< 10 GiB` | stop starting builds/browser suites/imports |
| `< 5 GiB` | recovery and cleanup only |

Memory, swap, active builds, and running services must also be checked. If a
command might consume sustained CPU, RAM, disk I/O, or network, run it on the
Homeserver and record it; never move that load to the small editing machine.

## 8. Safe cleanup procedure

1. Inspect and write an allow-list manifest with absolute paths/object IDs.
2. For every P0 path or volume that will move, prove a restorable backup by
   checking its checksum and performing a test restore/read (not merely
   checking that an archive exists).
3. Capture and temporarily quiesce every affected scheduler (user crontab,
   `/etc/cron.d`, `/etc/cron.*`, and systemd timers); confirm no run is in
   flight. Restore the scheduler only after the move is verified.
4. Verify no process, mount, service, or other project references each item.
5. Preserve a checksum/exit-code/log record where applicable.
6. Perform only the listed moves/deletions.
7. Recheck services, mounts, routes, disk, and project boundaries.
8. Record what remains and the next review date.

Compatibility symlinks may remain temporarily when an old cron, compose file,
or service still references a path. A symlink is a deliberate migration
bridge, not an invitation to keep writing files at the old location.

## 9. Host-wide boundaries

The policy covers all projects but does not authorize moving or deleting
`sat-coach-*`, `health`, `notebook-data`, `bs-companion`, `actions-runner`, or
any unfamiliar service. Each project must be audited and migrated separately.
Public `/home/jason/demos` remains a shared delivery directory; new Garmin
evidence should first be stored under the Garmin root and copied there only
when approved, with a TTL and URL manifest. Public delivery directories contain
copies only, never symlinks into a project root, and directory browsing stays
disabled. Inspect the GitHub Actions runner UID before migration and keep
`persistent/` mode `0700` so workflows cannot write P0 data implicitly.

The existing `demos` contents require a one-time retro-classification by live
URL and authoritative project copy; the rule is not limited to newly created
evidence. Check that no public item contains P0 or credential-shaped material
before considering individual removal. Retiring a demo is a URL change and
requires recording the replacement/404 decision separately from deleting its
file.

The same ownership rule applies to root-level files such as `aicaddie-sync*.log`,
`prepare-recent.log`, Caddyfile backups, and one-off review transcripts: new
Garmin files belong under `/home/jason/garmin-ai-caddie/{logs,services,archives,
manifests,tmp}`. Existing files are moved only after reference checks and a
manifest; unrelated project files stay in their own project roots.

## 10. Review gate for this draft

Claude must check this draft for missing data-loss hazards, ambiguous Docker
rules, resource validity and lifecycle, long-running endpoint ownership and
exposure, top-level containment, unusable paths, and conflicts with existing
services. The user reviews the draft and Claude's report. Only after explicit
approval may an agent:

- create `/home/jason/garmin-ai-caddie` and host policy files;
- move Garmin-owned paths using a generated manifest;
- update cron/service references and add compatibility symlinks;
- remove the explicitly approved test Docker objects or caches.
