# Garmin Homeserver Layout and Migration Draft

Status: **draft only**. This is the proposed target and allow-list shape; it
has not been applied to `/home/jason`.

## Target layout

```text
/home/jason/garmin-ai-caddie/
├── README.md
├── POLICY.md
├── persistent/
│   ├── data/                 # former garmin-ai-caddie-data
│   ├── backups/              # production backups; P0
│   └── legacy-evidence/      # former aicaddie-data/evidence
├── evidence/
│   ├── approved/
│   └── public-staging/
├── archives/
├── manifests/
│   └── sessions/
├── services/
│   ├── sync/
│   │   ├── aicaddie-sync.sh
│   │   └── build-context/
│   ├── prepare/prepare-recent.sh
│   └── caddy/
│       ├── Caddyfile
│       └── history/
├── logs/
│   ├── sync/
│   ├── prepare/
│   └── archive/
├── incoming/
├── bin/
└── tmp/
    ├── sessions/
    ├── reviews/
    ├── runs/
    ├── builds/
    ├── downloads/
    ├── extraction/
    ├── docker/
    └── tunnels/
```

All directories are owned by `jason:jason`. Use mode `0700` for `persistent/`
and `incoming/`, `0750` for `services/`, `logs/`, `manifests/`, `archives/`
and `evidence/`, and `0700` for each per-session `tmp/<class>/<session-id>`.
If a service runtime UID cannot traverse/read `services/`, grant a dedicated
runtime group `0750` directory access and `0640` file access, or mount a
root-owned read-only copy; never make `persistent/` or secrets world-readable.
The code checkout and compose file remain at the sanctioned
`/home/codex/garmin-ai-caddie` exception; neither moves or duplicates under
this data root in phase one. Any active container whose Compose metadata names
a different legacy working directory is audited before it is recreated.

## Proposed first migration (after approval)

| Current path | Target | Class | Compatibility bridge |
|---|---|---|---|
| `/home/jason/garmin-ai-caddie-data` | `persistent/data` | P0 | symlink at old path until all references are updated |
| `/home/jason/aicaddie-production-backups` | `persistent/backups` | P0 | symlink at old path |
| `/home/jason/aicaddie-data/evidence` | `persistent/legacy-evidence` | P1/P0 by file | symlink only at old `aicaddie-data/evidence`; parent stays a real directory until siblings are audited |
| `/home/jason/aicaddie-sync-build` | `services/sync/build-context` | P2/P3 | symlink at old path while release scripts migrate |
| `/home/jason/aicaddie-sync.sh` | `services/sync/aicaddie-sync.sh` | P0 service entrypoint | update cron to the new absolute path; old path is a wrapper only if `$0`-relative behavior is proven safe |
| `/home/jason/prepare-recent.sh` | `services/prepare/prepare-recent.sh` | P0 service entrypoint | update cron to the new absolute path; old path is a wrapper only if `$0`-relative behavior is proven safe |
| `/home/jason/aicaddie-sync*.log` | `logs/sync` | P2/P1 by evidence | symlink only for active log |
| `/home/jason/prepare-recent.log` | `logs/prepare/current.log` | P2 | symlink |
| `/home/jason/aicaddie-web.Caddyfile` | `services/caddy/Caddyfile` | P0 service config | validate, then update the bind mount in a planned container recreate with a tested rollback and brief expected downtime; do not rely on a home symlink until runtime permissions are proven |
| old Caddyfile backups | `services/caddy/history` | P1/P2 | none needed |

The migration must not move the shared `/home/jason/demos`, unrelated project
roots, Docker named volumes, or the active `/home/codex` checkout. Existing
Garmin `codex-runs` snapshots remain an exception until their unique deltas and
evidence are classified; inactive, proven-disposable run directories may later
move to `tmp/runs/legacy` with symlinks and a manifest.

The two currently observed review sessions are handled by the host policy,
not by directory age alone:

- `aicaddie-review-f463725-tunnel` is a live Cloudflare quick tunnel to the
  `f463725` review API and mounts the production private volume. It is
  protected because of the P0 mount, not because it returns 200. An owner must
  choose `replace`, `retire`, or `convert` to an authenticated/Tailnet-private
  route before the stack is stopped.
- `sat-coach-review-settings-20260822` belongs to another project. Garmin
  cleanup must not stop or move it; its owner must apply the same manifest and
  TTL rules under the SAT Coach project root.

No new Garmin review may use an untracked top-level file or a permanent
detached tmux session. A review endpoint gets a manifest under
`manifests/sessions/`, disposable logs under `tmp/tunnels/<session-id>/`, and
an explicit expiry. The cross-project registry remains at
`/home/jason/.local/share/homeserver/resource-registry.tsv`; it is host policy
metadata, not Garmin persistent data. The public `/home/jason/demos` tree is shared and remains
outside this project root; only approved copies may be placed there.

## Preflight gates

Before any move or deletion, record:

- exact path, owner, mode, size, mtime and SHA-256 for files;
- directory file count and checksum manifest for persistent data;
- process cwd/open-file references;
- systemd, cron, Docker Compose, Caddy and tmux references;
- Docker image/container/volume IDs and mounts;
- current disk, memory, network routes and service health;
- the Compose project name and a post-pin check that the existing volume IDs
  are still attached;
- every scheduler (user crontab, `/etc/cron.d`, `/etc/cron.daily`,
  `/etc/cron.hourly`, and systemd timers), then quiesce the relevant jobs and
  confirm no sync run is in flight;
- the Caddy runtime user, unit/container mount, `ProtectHome` setting if a
  host unit is involved, and a `caddy validate` result.

For every P0 move, the migration is blocked until a backup is checksum-verified
and a small test restore/read succeeds. A backup file that has never been
restored is evidence of existence, not evidence of recoverability.

If a reference cannot be explained, leave the item in place and report it.
Moves happen one class at a time, followed by service checks and a rollback
path. A failed move is not repaired with a broad delete.

## Safe migration order

1. After user approval, install the approved host policy at
   `/home/jason/HOMESERVER_AI_OPERATIONS.md`. Until then, this draft is the
   controlling rule and no migration or deletion is allowed.
2. Capture the full preflight manifest, including scheduler definitions,
   Compose config/project name, volume IDs, Caddy runtime/permissions, disk and
   `/dev/shm` pressure, and checksums of every service entrypoint.
3. Read both shell entrypoints for `$0`/`dirname`-relative behavior. The compose
   file stays under `/home/codex/garmin-ai-caddie`; pin its project name as a
   precaution and confirm the same volumes remain attached. Nothing moves
   before this check.
4. Create the empty target tree with the modes above, then install its
   `README.md` and `POLICY.md` before any project resource moves into it.
5. Quiesce the relevant cron/timer jobs, capture the old crontab, and confirm
   no sync run is in flight.
6. Verify and test-restore P0 backups, then move persistent data and add only
   child-level compatibility bridges.
7. Move service entrypoints, update schedulers to absolute target paths, run
   one full cycle, and only then remove temporary wrappers.
8. Move/update Caddy last: validate, perform a planned container recreate to
   change the bind source, verify the new mount and live URL, and use the
   recorded old container/config command for rollback if health fails.
9. Quiesce schedulers again and confirm no run is in flight before moving
   active logs; install log bridges, re-enable, and observe another cycle.
10. Move legacy evidence; handle Docker candidates in a separate, quiet
    change window after the release/review decision.

Loose Garmin files currently sitting directly under `/home/jason` are not
bulk-moved. Each file is first classified as an active service input, a
protected log/evidence item, or disposable scratch. Active inputs move during
the scheduler/service change window; logs and evidence move only after a
checksum/reference check; disposable scratch is removed only from an explicit
allow-list.

## Current Docker decision candidates

These are **candidates for Claude/user review**, not an execution list:

- `aicaddie-sync:28a9d18-candidate`: **awaiting-owner**. It has no running
  container reference, but it is neither an approved rollback nor an approved
  deletion candidate until its digest/source metadata and rollback decision are
  recorded. Do not remove it while the decision is pending.
- two zero-byte, unreferenced preflight named volumes:
  `garmin-topov4-preflight-d92272a-20260731_ai-caddie-pgdata` and
  `garmin-topov4-preflight-d92272a-20260731_ai-caddie-private`; inspect labels,
  mounts and compose history before removal. Named-volume deletion is never
  implicit.
- `alpine:latest`: 13 MB, no container reference; keep for now because it is a
  common base/healthcheck helper and the space is negligible.
- BuildKit cache: approximately 2.5 GB; age-filtered prune is preferred after
  confirming no build is active.

The following stay protected until a release decision changes their role:

`garmin-ai-caddie-api:5130f65` (production),
`garmin-ai-caddie-api:6a6080c-candidate` (current candidate),
`garmin-ai-caddie-api:f463725` (active review),
`garmin-ai-caddie-api:latest`/`rollback-a6d5ec5` (rollback alias),
`aicaddie-sync:latest`/`6a6080c-candidate` (cron target), PostgreSQL,
`garmin-ai-caddie_ai-caddie-private`, and `aicaddie-pw-profile`.

The `latest` tags are current compatibility exceptions because cron still uses
them. Before changing that job, promote an immutable sync/API tag and record
its digest; do not treat `latest` as a rollback guarantee.

## Rollback

Every migration step writes a manifest with `before`, `after`, and a tested
rollback command. If a service loses health or a path is still referenced,
restore the compatibility symlink/file from the manifest and stop the
migration. Do not improvise a second directory tree.
