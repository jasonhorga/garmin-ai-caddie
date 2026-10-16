# Nearby and cold map startup

Coordination: https://github.com/jasonhorga/garmin-ai-caddie/issues/426.
Codex owns backend; Claude owns Watch nearby download and vector drawing.

The owner target is a nearby map in seconds and a genuinely unseen usable map
under 30 s. These measurements are backend calls, not wrist/public-network claims.

Implementation queues every provider course within 30 km on GPS discovery;
uses one shared public-assets journal per physical course; checks actual hole
counts from the release; bounds regional work to one hole and selected work
to two holes per coordinator pass; and prioritizes a playing-hole download.
Factual vectors persist by physical-hole/release/Tee fingerprint independently
of the player's history and topo raster. Personalized planning stays scoped
to the requesting player and can enrich the partial factual prep later.

`coursePrep.holes[*].map.image` remains null for vector-only rows. The overlay
adds `surfaces` with actual mesh rings (`kind`, `polygons`, `outerPx`, `holesPx`)
in the shared raster frame. Route, green/fairway outlines, hazard edges and
F/M/B/GPS projection are included. Do not gate drawing on `topoReady` or the
install's all-assets `ready` phase. #425's null-image/progress fixes are required.

## Measured first draw

2026-10-14, existing production dependency image with candidate source, real
Garmin data/session paths. Before 28263 (Drachenwand): no cached release, no
ZIPs, no decoded holes. No data was removed to manufacture a cold measurement.

| Phase | Seconds |
|---|---:|
| Release metadata | 0.299 |
| ZIP download | 0.733 |
| Key retrieval + extraction | 2.086 |
| Draco decode | 0.967 |
| Distance export | 0.980 |
| Hazard export | 1.549 |
| File install | 0.001 |
| Geometry ensure (includes authority/other overhead) | 6.393 |
| Factual vectors | 0.152 |
| First drawable physical hole | 6.844 |
| History load | 2.388 |
| Facts/stats/caddie package | 4.857 |
| Route/vector seeds | 0.024 |
| First package with drawable map | 14.125 |
| Immediate repeat while remaining install pending | 0.615 |

The map contains real fairway/fringe/tee/green/bunker rings and green F/M/B
317/331/344 yd. Nine-hole geometry+topo completed 17:30:00Z, about 63 s after
enqueue (17:28:57Z), about 77 s after the cold request began. First-map
availability and full install completion are different measured milestones.

An earlier 30180 probe omitted the production session symlink and failed
decryption. Its captures remain failed-verification evidence, excluded from
successful timing claims. The corrected probe reads the existing protected
session path; no credential is copied to evidence or logs.

## Regional contention and first-map response

All 17 provider courses around 47.8688854, 13.1455506 were enqueued, with a
foreground cold selection. No release, ZIP or mesh existed for the named
selection before each measurement. Direct backend results:

| Selection/request | First package | Vector preparation | History | Facts/player package |
|---|---:|---:|---:|---:|
| 30189, ordinary cold package | 24.061 s | 8.176 s | 7.189 s | 8.661 s |
| 30189, warm package | 4.718 s | 0.023 s | 2.559 s | 2.094 s |
| 30189, warm after selected nine ready | 8.315 s | 0.026 s | 2.381 s | 4.362 s |
| 28241, cold factual map package | 7.643 s | 7.445 s | 0.000 s | 0.166 s |
| 28241, immediate warm factual map | 0.450 s | 0.186 s | 0.000 s | 0.217 s |
| 28241, warm after selected nine ready | 0.618 s | 0.032 s | 0.000 s | 0.343 s |
| 28245, final code cold factual map | 11.613 s | 10.676 s | 0.000 s | 0.836 s |
| 28245, immediate warm factual map | 0.321 s | 0.053 s | 0.000 s | 0.213 s |

Different courses are separate samples, not a paired latency benchmark. The
ordinary path still waits for player projection after its map is drawable.
The explicit `map_only=true&background_geometry=true` package request removes
that dependency: the same v2 schema carries the complete ordered hole list,
factual vectors and deferred player enrichment. It returns empty clubProfiles
and no synthetic recommendations; fetch the ordinary package separately for
personal clubs/history/caddie. Keep the first map and any existing personal
club model while that enrichment arrives. This is the visible tradeoff: map
first, recommendations later. Raster completion is never a drawing gate.

The 28241 nine-hole install succeeded (geometry 9/9 + topo 9/9), but hole 9
alone spent 36.266 s exporting distances and 54.052 s exporting hazards.
This remains a full-install optimization opportunity, independent of usable
first-map delivery. Optional CourseView route authority is now observed before
the foreground export so A/B greens bind to the selected layout; missing
catalogues are shared per release and retried hourly instead of per hole.

Targeted final code tests: 231 passed, two missing-data skips. These include
the map-only history/stats/planning/raster isolation and ordered back→front
identity, plus optional catalogue release invalidation/backoff. The final
cold 28245 sample includes optional route authority (metadata 0.765 s),
geometry 8.609 s and factual vectors 1.286 s, with all 17 regional courses
queued. The first response had a real map with topo still pending; its
verification-owned remaining install was cancelled/drained after first-map
measurements. Public transport acceptance is pending. Production remains
cbc17f4e and TestFlight remains 0.1.0 (87) at this checkpoint.

Persistent evidence, controls and resource manifest:
`/home/jason/garmin-ai-caddie-data/operations/map-startup-20261014`.
The baseline profile is instrumentation-affected; it identifies history/stat
and deferred-planner CPU but is not substituted for unprofiled timing.

## Production deployment and public verification

#427 merged as `128798fd8fd638227c8668a05de02c15eb3787a7`; its branch is
deleted. Exact-head CI `38612115537` passed at `b9cf540a`. The production
image passed 258 targeted tests (2 data-dependent skips) plus the deployment
controller's original gates; 39 supplemental map/auth checks had also passed.

Production now runs `aicaddie-release-128798fd-production-20261014` on
loopback port 39055 (container 9000), with matching sync image
`aicaddie-sync:128798fd8fd638227c8668a05de02c15eb3787a7`. The previous
cbc17f4e container is stopped and retained for rollback. Existing Funnel
routes, protected private volume, credentials and cron were preserved.
Health/history/sync/precise prep/topo gates passed. Manual incremental sync
ran 18:36:47–18:37:27 UTC, verified this revision and ended `sync ok`, `done`.

Authenticated readiness returned HTTP200 and `authenticated:true`. Its
runtime/service status remains `degraded`, matching the documented Build87
internal baseline: private snapshot acceptance evidence is absent; historical
package weather is absent while source/18-hole geometry/11 clubs/18 seeds are
ready; the legacy mobile event schema is absent. The controller verified these
existing gaps and rejected new runtime failures. This is not full external
release readiness. Baseline: `2026-10-14-internal-testflight87.md`.

Production probes at 18:56–18:57 UTC used the real protected Garmin session
and authenticated endpoints. Requests originated on homeserver and traversed
the public Funnel; these are not Tokyo, Austrian phone, or wrist measurements.

| Production sample | Seconds | Evidence |
|---|---:|---|
| 28214 Olympia Golf Igls, cold release/Tee lookup | 0.6740 | No release, ZIP or mesh before lookup |
| 28214, first public factual map after metadata | 5.7789 | Route, surfaces, F/M/B; geometry 1/9, topo 0/9 |
| 28214, metadata plus first public package | 6.4529 | Split measurement; metadata command includes interpreter overhead |
| 28214, immediate public warm package | 0.2237 | Same real factual map |
| 28214, loopback warm package | 0.1149 | Same real factual map |
| 26557 Anthal Waginger See, first public existing map | 1.4252 | Regional worker had already prepared 7 holes |
| 26557, public warm package | 0.8883 | Same selected Gelb Tee and `:all` identity |
| 28242 Salzburg-Eugendorf, public nearby map | 3.2413 / 2.6722 | Two samples while regional work was pending |

The cold 28214 request's Server-Timing total was 5.6540 s, including priority
vectors 5.6014 s, release lookup 0.0014 s, factual package 0.0252 s and seeds
0.0202 s. Warm total was 0.0826 s. Its first compressed response was 15,540
bytes (77,553 JSON bytes) with Fairway/Fringe/Teebox/Green/Bunker/Lake rings,
GPS projection and F/M/B 237/252/266 yd. It was drawable with every topo
still queued. These samples support the backend first-map target; they do not
establish on-device rendering time or a percentile guarantee.

Both GPS discovery triggers returned without waiting for preparation. The
first options/nearby samples were 0.8146/1.1234 s, later 0.1980/0.2160 s.
All 17 provider IDs within 30 km of 47.8688854, 13.1455506 were present in
actual production `:nearby-assets` journals. At the cold sample each regional
course had 7–8 geometry/topo holes ready. Journals continue intentional
persistent work; they were not cancelled as probe resources.

The original public probe incorrectly requested `26557:front`: the provider
catalogue reported 18 holes, but release267 contains nine, requiring `:all`.
Its HTTP422 report remains `deployment/live-map-timings.json` and is excluded
from success timings. By the corrected request the course was already warm;
28214 was independently verified cold without deleting any assets. The later
fresh nearby response and Tee response both correctly reported nine. A stale
Watch option test is needed because `withTees` preserves its old hole count;
this source risk is not a reproduced fresh-search Watch failure. Read-only
evidence: `deployment/catalogue-26557-identity.json`.

Detailed successful reports: `deployment/live-map-26557-20261014T185658Z.json`
and `deployment/live-map-28214-20261014T185721Z.json`. Candidate container,
disposable private volume and `/dev/shm/codex-map-startup-deploy-20261014`
were removed via their labelled allow-list after archive/provenance/open-file
checks. `deployment/cleanup-result.json` confirms all three removals and
production health. Disk remained about 44 GiB free; protected production data,
new course assets, production images and stopped rollback were preserved.

TestFlight remains iOS/watchOS 0.1.0 (87). No upload was requested by this
backend-only slice. #425 still needs its Watch null-image/progress fixes and
first-vector renderer before these backend numbers become user-visible.
