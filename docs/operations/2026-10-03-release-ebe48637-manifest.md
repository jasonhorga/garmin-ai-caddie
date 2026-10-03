# Internal release manifest: `ebe48637` (2026-10-03)

**Purpose:** owner-requested internal validation of the merged B2–B7.1 product
tip from PR #370. This is a candidate-only release; it must not switch
production or perform external distribution.

| Resource | Planned value | Lifecycle |
|---|---|---|
| Source | `ebe486372ea3956ae784f3af9a58e7843c481208` | exact immutable release source |
| Remote source snapshot | `/home/jason/codex-runs/garmin-ai-caddie-release-ebe48637-20261003` | remove after evidence is retained |
| API image | `garmin-ai-caddie-api:ebe486372ea3956ae784f3af9a58e7843c481208-candidate-20261003` | retain until release evidence is closed, then allow-list cleanup |
| Candidate container | `aicaddie-release-ebe48637-candidate-20261003` | loopback only; never production |
| Candidate port | `127.0.0.1:39087` | release-scoped, verify free before start |
| Candidate tunnel | `codex-release-ebe48637-tunnel-20261003` | unique Quick Tunnel; expiry/cleanup recorded when created |
| Persistent data | existing protected private data volume, mounted only for candidate checks | production remains untouched; no volume deletion |

## Gates

1. Build and label the candidate image from the exact source; start it on the
   candidate port and verify health, authenticated readiness, B5 stats,
   B4b-2 loops, swing-candidates, and image/container/source revision binding.
2. Expose only the candidate through the unique Quick Tunnel and dispatch
   exact-SHA live Native Mobile CI (`capture_scope=full`, `fixture_mode=false`).
3. Download and inspect the Native Mobile CI evidence artifacts on the
   homeserver.
4. Dispatch the internal-only TestFlight upload with the candidate HTTPS
   origin and expected backend revision.
5. Run the existing read-only Apple status/group check and record build
   validity, expiry, internal beta state, Watch bundle, and group visibility.

No production container, shared Funnel route, persistent volume, or external
tester/group state may be changed by this release.
