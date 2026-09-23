# PR332 Deployment Manifest

**Owner:** Codex (`/root`)
**Purpose:** exact-merge-SHA candidate verification and reversible internal API deployment
**Created:** 2026-09-23 08:42 UTC
**Expiry:** 2026-10-01 08:42 UTC unless renewed while physical validation is active

## Planned Resources

| Kind | Exact resource | Lifetime / cleanup |
| --- | --- | --- |
| Source snapshot | `/home/jason/codex-runs/garmin-ai-caddie-pr332-20260923-canonical` | **Removed 2026-09-23** under allow-list `20260923T1134Z-pr332-source-snapshot`; canonical Git source and durable evidence remain |
| API image | `garmin-ai-caddie-api:3c5ec81af1b0f67576c0e93e1ede0c305194d099-candidate-20260923` | Retain as rollback image until physical validation closes |
| Sync image | `aicaddie-sync:3c5ec81af1b0f67576c0e93e1ede0c305194d099` | Retain with API rollback image; remove only under a later exact allow-list |
| API candidate | `aicaddie-release-3c5ec81a-candidate-20260923`, `127.0.0.1:39086` | **Removed 2026-09-23** under allow-list `20260923T1058Z-pr332-final-candidates`; do not recreate |
| API production | `aicaddie-release-3c5ec81a-production-20260923`, `127.0.0.1:39055` | Active deployment; retain old rollback container until physical validation closes |
| API rollback | `aicaddie-release-5124d638-rollback-20260923` (stopped) | Retain until physical validation closes; start only for rollback |
| Private data | `garmin-ai-caddie-pr332-deploy-private-20260923` (copy of `garmin-ai-caddie_ai-caddie-private`) | **Removed 2026-09-23** under the same allow-list; protected source volume was not touched |
| Database/network | Existing `garmin-ai-caddie-db-1` and `garmin-ai-caddie_default` | Protected shared resources; no schema/data reset |
| Evidence | `/home/jason/garmin-ai-caddie-data/operations/pr332-deploy-20260923/` | Retain timings, health, image labels, deployment, snapshot, cleanup and TestFlight records |

## Gates

1. **Complete:** Build the API and same-SHA sync image on homeserver; both labels report `3c5ec81af1b0f67576c0e93e1ede0c305194d099`.
2. **Complete:** Start and smoke-test the candidate on `39086`; health, authenticated readiness, package, prep and history checks passed.
3. **Complete:** Switch `39055` through the reversible path; the old container is stopped under the exact rollback name.
4. **Complete:** Post-deploy local/Caddy/Funnel health and focused timing checks passed; evidence is under the evidence directory.
5. **Complete:** Same-SHA Native Mobile CI `35847317420`, internal TestFlight CD `35853831558` (Build 74), and read-only ASC check `35854907245` passed. No external distribution, tester mutation or additional production promotion occurred.

## Protected Resources

- `aicaddie-release-3c5ec81a-production-20260923` on `39055` and its Caddy/Tailscale route.
- `aicaddie-release-5124d638-rollback-20260923` (stopped rollback container) and the prior `5124d638` image.
- `aicaddie-release-a13724e1-candidate-20260922` on `39083` and the route2 evidence tunnel.
- `garmin-ai-caddie_ai-caddie-private`, PostgreSQL, named volumes, unrelated containers, tmux sessions, and shared Docker cache.

## Closeout evidence

- TestFlight Build `0.1.0 (74)` provenance: workflow `35853831558`, IPA SHA-256 `98e568501f243086d6eb2a253a6a31d0c42530bb1c2faadd576a89753777c64b`.
- Apple read-only result: workflow `35854907245`; Build 74 `VALID`, unexpired, `IN_BETA_TESTING`, arm64, Watch bundle present, existing internal all-builds group visible, `internalReady=false`.
- Production post-deploy health and timing evidence remains under `/home/jason/garmin-ai-caddie-data/operations/pr332-deploy-20260923/`.
- The disposable canonical source snapshot cleanup is recorded under `/home/jason/garmin-ai-caddie-data/cleanup-manifests/20260923T1134Z-pr332-source-snapshot/`; production and route2 containers remained healthy after removal.
