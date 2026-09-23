# PR332 Deployment Manifest

**Owner:** Codex (`/root`)
**Purpose:** exact-merge-SHA candidate verification and reversible internal API deployment
**Created:** 2026-09-23 08:42 UTC
**Expiry:** 2026-10-01 08:42 UTC unless renewed while physical validation is active

## Planned Resources

| Kind | Exact resource | Lifetime / cleanup |
| --- | --- | --- |
| Source snapshot | `/home/jason/codex-runs/garmin-ai-caddie-pr332-20260923-merge` | Remove after post-deploy evidence is durable and no process uses it |
| API image | `garmin-ai-caddie-api:07df70c500146f930afc076033b2972dc9cc9b3d-candidate-20260923` | Retain as rollback image until physical validation closes |
| Sync image | `aicaddie-sync:07df70c500146f930afc076033b2972dc9cc9b3d` | Retain with API rollback image; remove only under a later exact allow-list |
| API candidate | `aicaddie-release-07df70c5-candidate-20260923`, `127.0.0.1:39086` | Stop/remove when superseded; do not touch protected `39055` or `39083` |
| Private data | `garmin-ai-caddie_ai-caddie-private` | Existing shared project volume; mount only, never delete or prune |
| Database/network | Existing `garmin-ai-caddie-db-1` and `garmin-ai-caddie_default` | Protected shared resources; no schema/data reset |
| Evidence | `/home/jason/garmin-ai-caddie-data/operations/pr332-deploy-20260923/` | Retain timings, health, image labels, deployment and cleanup records |

## Gates

1. Build the API and same-SHA sync image on homeserver.
2. Start the candidate on `39086` with the existing private volume and verify health, readiness, authenticated package/prep/history smoke, and source revision.
3. Only after candidate evidence passes, switch the existing API service through the documented reversible deployment path; preserve the prior `39055` image/container as rollback until post-deploy checks pass.
4. Run post-deploy health and focused timing checks, then update `PROJECT_STATE.md`.
5. Native/TestFlight action remains governed by the existing internal-only release rule and must use the merged source SHA.

## Protected Resources

- `aicaddie-release-5124d638-candidate-20260909` on `39055` and its Caddy/Tailscale route.
- `aicaddie-release-a13724e1-candidate-20260922` on `39083` and the route2 evidence tunnel.
- PR332 validation resources on `39084`/`39085` until their separate manifest is closed.
- PostgreSQL, named volumes, unrelated containers, tmux sessions, and shared Docker cache.
