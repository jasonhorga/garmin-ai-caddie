# Scoped Homeserver Cleanup: Superseded Course-Name Candidate

Created: 2026-09-18T14:34:26Z
Owner: Codex / `/root`
Project: `garmin-ai-caddie`
Purpose: stop only the superseded course-name validation API and its dedicated
Quick Tunnel after Build 65 (`7ef3fcc833790bc49b02c94e7685f11f5d624d2b`) became
the active physical-validation candidate.

## Protected resources

- `aicaddie-release-7ef3fcc8-candidate-20260917`, loopback `127.0.0.1:39068`:
  current Build 65 backend; keep running.
- `aicaddie-release-5124d638-candidate-20260909`, loopback
  `127.0.0.1:39055`: Caddy's current upstream and rollback/stable entry; keep
  running.
- `aicaddie-web`, `garmin-ai-caddie-db-1`, all named/private volumes, images,
  Caddy/Tailscale routes, and all other candidate services: outside this
  allow-list; do not change.

## Exact cleanup allow-list

The operation is stop-only and reversible. No image, volume, source checkout,
log, or persistent round data is deleted.

| Resource | Exact target | Evidence/reason | Expiry |
|---|---|---|---|
| API container | `aicaddie-release-1e350be5-candidate-20260917` (`127.0.0.1:39067`) | source `1e350be5ce3dbc9e5199733401b4fdc07d4ef51a`, superseded by current `7ef3fcc8`; Docker stats ~389 MiB | originally stop-only; container metadata was later removed under the exact follow-up allow-list in `cleanup-20260918-expired-quicktunnel.md`; image/volume retained |
| Quick Tunnel | tmux session `codex-course-name-20260917-tunnel`, exact upstream `http://127.0.0.1:39067`, cloudflared PID observed as `3357856` | dedicated only to the superseded API; no shared Caddy/Funnel route | stop with API |

## Pre-cleanup facts

- API containers observed: `39055`, `39067`, `39068` only.
- Caddy `/api/*` upstream: `127.0.0.1:39055`.
- Current Build 65 Quick Tunnel: `https://creature-dramatic-acne-power.trycloudflare.com`
  -> `39068`.
- The allow-listed candidate had no shared route and was not the TestFlight
  Build 65 origin.
- Before action, capture Docker/container, socket, route, memory, and health
  output under `/home/jason/garmin-ai-caddie-data/cleanup-manifests/`.

## Post-cleanup checks

Re-check that `39068`, `39055`, Caddy, PostgreSQL, and the Build 65 Quick
Tunnel remain healthy; verify `39067` is no longer listening and the dedicated
tunnel session/process is gone. Record before/after capacity and the exact
stop result below.

## Recorded result

- `docker stop` returned the exact container name and the container is now
  `Exited (143)`; its restart policy is `no`.
- `127.0.0.1:39067` is no longer listening and no `cloudflared` process or
  `codex-course-name-20260917-tunnel` session remains.
- `127.0.0.1:39055/api/v2/health` returned HTTP 200; Caddy's
  `https://caddie.taile36706.ts.net/api/v2/health` returned HTTP 200.
- `127.0.0.1:39068/api/v2/health` and the Build 65 Quick Tunnel health check
  both returned HTTP 200.
- PostgreSQL remained healthy. No Caddy/Tailscale route changed.
- Capacity after stop: `Mem available 4.6 GiB`, `swap used 1.5/8.0 GiB`;
  Docker showed the current `39068` candidate at ~824 MiB and the protected
  `39055` candidate at ~21 MiB. The stopped candidate's observed footprint was
  ~389 MiB before stop.
- Machine-level before/after inventories are preserved in
  `/home/jason/garmin-ai-caddie-data/cleanup-manifests/20260918T143500Z-stale-candidate-disk-audit/`
  and
  `/home/jason/garmin-ai-caddie-data/cleanup-manifests/20260918T143600Z-stale-candidate-after-disk-audit/`.

Post-cleanup result: complete for the original stop-only operation. The later
follow-up cleanup removed the stopped container metadata and the superseded
39055 Quick Tunnel; see
`docs/operations/cleanup-20260918-expired-quicktunnel.md` for the authoritative
final resource state.
