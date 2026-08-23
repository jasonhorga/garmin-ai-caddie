# Homeserver Large Resource Audit

Date: 2026-08-22
Scope: Homeserver resources larger than roughly 100 MiB, plus long-running
review sessions. This is a read-only audit; no resource was deleted or stopped.

## Current size and ownership

| Resource | Approx. size | Ownership/status | Immediate action |
|---|---:|---|---|
| `/home/jason/codex-runs` | 6.4 GiB | Mixed Garmin/Codex/SAT Coach runs; includes 79 Claude worktree snapshots that the user said not to delete | Keep. Run the existing machine-generated per-run audit, then review only unique deltas/evidence. |
| `/home/jason/actions-runner` | 2.5 GiB | GitHub Actions runner, active process, cross-project | Out of Garmin scope. Do not clean from this session; its owner needs a separate cache policy. |
| `/home/jason/aicaddie-production-backups` | 1.1 GiB | Garmin P0 backups | Keep. Checksum and test-restore before any move or retention change. |
| `aicaddie-review-real-f463725-api` image/container | image about 1.7 GiB; container layer about 8 MB | Active Garmin review API; public quick tunnel; mounts `garmin-ai-caddie_ai-caddie-private` | Keep for now. This is a replace/retire/convert change-window decision, not a cache prune. |
| `/home/jason/sat-1550-coach` + `sat-1550-coach-data` | about 573 MiB | Other project; active server | Out of scope. |
| `/home/jason/garmin-ai-caddie-data` | 218 MiB | Garmin persistent data and cleanup manifests | Keep; this is the current durable evidence location until the target root migration is approved. |
| `/home/jason/demos` | 271 MiB | Shared public delivery tree | Keep the directory. Audit each item by live URL and authoritative copy; check for private/P0 content. |
| `/home/jason/.cache` | 315 MiB | Mixed tool caches | Defer until ownership is classified; use cache-specific cleanup only. |
| `/home/jason/.claude` | 19 MiB | Claude transcripts/config/cache | Small; defer while larger resources are being audited. |

The current machine-generated run inventory is retained at:

`/home/jason/garmin-ai-caddie-data/cleanup-manifests/2026-08-22T2032Z-codex-runs-audit/`

It records 102 run directories. The largest Garmin entries include:

- `aicaddie-watch-sync-fix-20260822` (~995 MiB): Git, `.venv`, build output,
  evidence, and 43 references; treat as current/active until references close.
- `garmin-ai-caddie-p0-watch-20260822` (~906 MiB): Claude worktrees,
  `.venv`, build/evidence/data; protected by the user's no-delete instruction.
- `aicaddie-25244f9-final-review-20260814` (~910 MiB): mostly native review
  artifacts; candidate for archive/deletion only after every published or
  approved image is copied and URL references are retired.
- `aicaddie-75bf5ce-git-20260821`, `aicaddie-a700dca-git-20260821`, and the
  `system-adjust`/`opus-close` snapshots (~0.5-0.56 GiB each): source/build/
  evidence mixtures; require the two-tier delta audit, not name-based removal.

## Long-running sessions

### Garmin review tunnel

`aicaddie-review-f463725-tunnel` has run since 2026-08-01 and proxies the quick
Cloudflare URL `lobby-slight-thee-station.trycloudflare.com` to
`127.0.0.1:39022`. The upstream is container
`aicaddie-review-real-f463725-api`, and recent API requests exist. The container
mounts the production private volume. A 200 response proves reachability, not
that the review is still wanted. The owner must choose:

1. `replace` it with an authenticated or Tailnet-private route;
2. `retire` it and capture rollback/evidence; or
3. `keep` it with a named owner, purpose, expiry, and an explicit P0 exposure
   decision.

Until then, do not stop the tunnel, container, image, or shared volume.

### SAT Coach review

`sat-coach-review-settings-20260822` is a different project's detached session.
Its API had requests within the current audit window and uses `/dev/shm`. It is
not a Garmin cleanup candidate. The SAT Coach owner must register and expire it
under the same host policy. The related `sat-coach-gate-debug-*` session and
active release-gate processes are likewise out of scope.

## Loose `/home/jason` files

The Garmin cron currently references these top-level paths directly:

- `/home/jason/aicaddie-sync.sh`
- `/home/jason/prepare-recent.sh`
- their logs
- `/home/jason/aicaddie-web.Caddyfile`

They cannot be moved until cron, Docker bind mounts, and rollback bridges are
captured. New files must go under the approved Garmin root (`services/`,
`logs/`, `archives/`, `manifests/`, or `tmp/`). Existing root-level files are
classified one by one; unrelated files and dotfiles remain where they are.

## Cleanup order after policy approval

1. Register all existing long-running sessions and routes, including both
   observed tmux sessions.
2. Resolve the f463725 public exposure decision.
3. Perform the two-tier audit of Garmin run directories over 100 MiB; preserve
   the user's Claude worktrees until content-level review is complete.
4. Retro-classify `/home/jason/demos` by URL and authoritative copy.
5. Only then consider archive/deletion allow-lists for old review artifacts,
   build output, and rebuildable caches.
6. Handle the P0 directory migration and cron/Caddy changes in a separate,
   quiesced change window with checksum and test-restore evidence.

