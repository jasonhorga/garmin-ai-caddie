# Scoped Homeserver Cleanup: Expired Build 52 Quick Tunnel

Created: 2026-09-18T15:00:00Z
Owner: Codex / `/root`
Project: `garmin-ai-caddie`
Purpose: close the superseded Build 52/old-candidate public tunnel and its
already-stopped API container after Build 65 became the active physical-test
entry point.

## Exact allow-list

| Resource | Exact target | Evidence and action |
| --- | --- | --- |
| Quick Tunnel tmux session | `codex-aicaddie-quicktunnel-http2-20260907` | Process command points only to `127.0.0.1:39055`; public origin is `suggests-kilometers-normal-insertion.trycloudflare.com`, used by the superseded Build 52/UX2 validation. Stop the named session. |
| Stopped API container | `aicaddie-release-1e350be5-candidate-20260917` | Exact source `1e350be5ce3dbc9e5199733401b4fdc07d4ef51a`; status already `Exited (143)`, restart policy `no`, no listener. Remove container metadata only after confirming it remains stopped; retain its image and shared volume. |

## Protected resources

- `aicaddie-release-7ef3fcc8-candidate-20260917`, `127.0.0.1:39068`, and
  `codex-course-name-7ef3-20260917`: current Build 65 API and tunnel.
- `aicaddie-release-5124d638-candidate-20260909`, `127.0.0.1:39055`: Caddy
  upstream and rollback entry; do not stop.
- PostgreSQL, Caddy, Tailscale/Funnel routes, named volumes, all images,
  source data, credentials, and the `rc` tmux session (other projects).

## Pre-action observations

- Available memory: `5.0 GiB`; swap used `1.4/8.0 GiB`; root free `106 GiB`.
- API container stats: `39068` `823.7 MiB`, `39055` `20.67 MiB`.
- The old public origin returned HTTP 200 revision `5124d638`; the current
  Build 65 origin returned HTTP 200 revision `7ef3fcc8`.
- No active container is bound to `39067`; the old candidate was already
  stopped.

## Result

Executed at `2026-09-18T15:02Z`:

- Stopped tmux session `codex-aicaddie-quicktunnel-http2-20260907`; its
  `cloudflared` process and `127.0.0.1:20242` listener are gone.
- Removed container metadata for
  `aicaddie-release-1e350be5-candidate-20260917` after confirming
  `Exited (143)` and restart policy `no`. Its image and shared volume remain.
- `127.0.0.1:39055` (revision `5124d638`) and `127.0.0.1:39068` (revision
  `7ef3fcc8`) returned HTTP 200; Caddy and the Build 65 Quick Tunnel also
  returned HTTP 200; PostgreSQL remained healthy.
- Docker now reports four containers, all four active, and no reclaimable
  container bytes. Available memory is about `5.1 GiB`; swap is
  `1.4/8.0 GiB`. The current Build 65 API remains the dominant API process at
  about `823.7 MiB`.
- No image, volume, source data, credential, database, Caddy route, or other
  project's tmux session was changed.

The old candidate images and BuildKit cache were intentionally retained. They
are disk cleanup candidates, not running containers; removing them requires a
separate exact rollback-retention decision.
