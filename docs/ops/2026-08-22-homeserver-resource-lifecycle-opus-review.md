# Homeserver Resource Lifecycle Review (Opus)

Date: 2026-08-22
Status: review result only; no host resource was deleted or stopped.
Scope: large resources, long-running review sessions, public routes, and
`/home/jason` ownership rules.

## Verdict

The drafts are not ready for approval as-is. The migration/data-loss controls
are useful, but the lifecycle model is incomplete. In particular, the drafts
do not define what "still needed" or "proven-disposable" means, do not provide
a host-wide registry for existing long-running resources, and do not resolve
the conflict between a 24-hour preview/tunnel TTL and protection for a service
that mounts P0 data.

## Observed resources

| Resource | Current evidence | Disposition before an owner decision |
|---|---|---|
| `aicaddie-review-f463725-tunnel` + `aicaddie-review-real-f463725-api` | Cloudflare quick tunnel since 2026-08-01; public URL; upstream `127.0.0.1:39022`; API and tunnel return 200; container mounts `garmin-ai-caddie_ai-caddie-private`; recent requests exist | Keep running for now. This is a change-window item, not a normal P2 cleanup. Traffic proves reachability, not continuing need. Public unauthenticated exposure to P0 data must be explicitly assessed. |
| `sat-coach-review-settings-20260822` | Different project; detached Node API; recent requests; uses `/dev/shm` | Out of Garmin scope. Do not stop, move, or delete it. Its owner must apply the same lifecycle rules. |
| `/home/jason/codex-runs` (~6.4 GiB) | Many run directories, including 0.5-1.0 GiB Garmin snapshots; worktree deletion was explicitly deferred | Keep until a two-tier content audit classifies source, unique evidence, build output, and caches. Size alone is not evidence. |
| `/home/jason/demos` (~271 MiB) | Shared public delivery directory | Keep the directory. Retro-classify contents by live URL and authoritative project copy before removing individual items. Check for private/P0 material before any public cleanup. |
| BuildKit cache | Rebuildable, host-wide cache | First cleanup candidate after confirming no active build; use an age-filtered prune. |
| `aicaddie-sync:28a9d18-candidate` | Listed both as a removal candidate and as protected | Resolve the contradiction before any action; retain digest/source metadata and rollback decision. |

## Safe cleanup boundaries

No item above is authorized for deletion by this review. The low-risk order is:

1. Age-filtered BuildKit cache, after an active-build check.
2. Named preflight volumes only after `inspect`, mountpoint read, compose-origin
   check, and an explicit allow-list.
3. Old run directories only after the machine-generated pass and human review
   of directories with uncommitted deltas or unique non-rebuildable files.
4. The f463725 stack only after a named owner chooses `replace`, `retire`, or
   `convert` to an authenticated/Tailnet-private route and records rollback.

The SAT Coach session, host dotfiles, `/home/codex/garmin-ai-caddie`, production
volumes, and unfamiliar top-level projects are explicit non-candidates.

## Required policy additions

### Host-wide resource registry

Add a fixed registry (for example under the approved host policy data root)
with one row per long-running service, tunnel, preview, tmux session, Docker
container, and persistent mount. Each row must include:

```text
owner
project
purpose
resource_kind
location
route_class: public-unauthenticated | public-authenticated | tailnet-private | localhost-only
public_url_or_route
upstream_and_port
resource_paths
mounts_and_mode: ro | rw
created_at_utc
last_use_evidence_source
last_verified_use_utc
expires_at_utc
disposition: keep | replace | retire | convert | awaiting-owner
```

Existing resources must be retro-registered by a stated date. A missing
manifest is never, by itself, grounds to stop a service.

### Protection precedence

The protection class of a running service is the maximum of its own class and
the class of the data it mounts. A review-labelled service mounting P0 data is
therefore P0-protected until its exposure and replacement/retirement are
resolved. The 24-hour preview/tunnel TTL applies only to services that do not
mount protected data.

Active traffic is necessary but not sufficient for retention. It can be a
health check, edge probe, scanner, or stale browser. Conversely, no traffic is
not sufficient grounds to stop a P0-mounted service.

### Route-aware TTL and escalation

Use route-aware defaults rather than one flat TTL:

- 24 hours: `/dev/shm` snapshots and localhost-only previews;
- 72 hours: authenticated or Tailnet-private review endpoints;
- 24 hours plus explicit owner renewal: public unauthenticated review routes.

An item expired for seven days is escalated to the owner/user with a named
due date and disposition. The policy remains report-only until the owner
approves an allow-list.

### Top-level containment

`/home/jason` may contain dotfiles, host configuration, and declared project
roots only. New generated logs, screenshots, review files, scripts, archives,
and run outputs must be created under the owning project root. Every session
must `cd` to its declared location before creating files; no relative writes
from `$HOME` are allowed.

Freeze a dated top-level inventory with each entry marked:

```text
Garmin-owned | known-unrelated | unclassified
```

Add a report-only detector that diffs new top-level entries against this
inventory. Do not bulk-move existing loose files; classify and reference-check
each one first.

### Resource-kind separation

P0-P3 describes data retention, not the whole lifecycle of a running service.
Keep these kinds separate:

| Kind | Lifecycle source | Deleting it does not authorize |
|---|---|---|
| Review transcript | decision/release record | deleting its source snapshot |
| Source worktree/snapshot | TTL plus delta audit | deleting transcript/evidence |
| Evidence archive | release decision | deleting persistent data |
| Public demo | live URL retirement | deleting authoritative copy |
| Persistent data | never automatic | deleting siblings |
| Running service | registry disposition plus mounted data | deleting its image/volume/data |

New review services must not mount P0 data read-write. Existing mount mode must
be recorded before a keep/replace/retire decision. No new public unauthenticated
route may front a service that mounts P0 data.

## Large-directory audit

The `>100 MiB` threshold is a trigger, not a requirement for an unbounded manual
review. For each matching run directory, first generate a cheap machine report:

- source SHA and remote availability;
- Git status/diff against that SHA;
- file-type buckets for source, unique evidence, build output, and caches;
- references from release records, active processes, mounts, and public URLs.

Human review is required only for directories with uncommitted deltas or
unique non-rebuildable material. A directory containing Claude worktrees stays
protected until that content-level audit completes, regardless of age/name.

## User decisions still required

1. For the f463725 review stack: `replace`, `retire`, or `convert` to an
   authenticated/Tailnet-private route, and who owns it.
2. Adopt the protection-precedence and traffic-is-not-sufficient rules.
3. Treat `codex-runs` as a declared Garmin/Codex exception and fund the
   two-tier audit, or explicitly freeze it indefinitely.
4. Adopt route-aware TTLs and seven-day escalation.
5. Retro-classify the existing `/home/jason/demos` contents by URL, or make a
   deliberate grandfather decision.
6. Set the adoption deadline for the host-wide resource registry.

