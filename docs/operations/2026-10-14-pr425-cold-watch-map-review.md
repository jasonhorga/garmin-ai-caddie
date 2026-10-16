# PR #425 — cold Watch map incident and exact-head review

Production revision `cbc17f4e76f085229c3bdb3c74a5067951b217a6`; all times below are **2026-10-14 UTC**. This is the incident evidence, not a new cold-start benchmark.

The selected nine finished in approximately **76 seconds**, and the requested whole-course template in approximately **125 seconds**. Extending the Watch retry window is not the root-cause fix: both jobs completed before the last Watch package request, and the Watch's required-string decoding of `map.image: null` rejects the ready package (P1 already posted).

| Phase | Retained evidence |
|---|---|
| Garmin CourseView release / Tee metadata | `/tees?ensure_release=true` completed 08:14:26.483. The release file was refreshed at 15:52:37, so its original download-start/end timestamps cannot be recovered from its current mtime. |
| First nine enqueue | Journal `course-e888717818cdc213e416ceb4` created 08:14:38; initial package response completed 08:14:38.864. |
| `render=false` prep | Batches 1–3, 4–6, 7–9 completed 08:14:46.071 / 08:14:47.512 / 08:14:47.524, **before the first release-bound precise geometry completed at 08:14:53.232**. A 200 here is not proof of drawable geometry. |
| Geometry download / decode / authority | First ZIPs written 08:14:42.255 / 08:14:42.666; first decoded meshes 08:14:49.425 / 08:14:49.673; first validated authority 08:14:53.232 (hole 2), 08:14:54.894 (hole 1). All front-nine geometry complete by 08:15:50.212. |
| First raster | Hole 2 PNG 08:15:15.013; hole 1 PNG 08:15:20.277. |
| Selected nine terminal | All nine PNGs complete by 08:15:54.494; journal `ready`, geometry 9/9 and topo 9/9, updatedAt 08:15:54, generation 1, retryCount 0. |
| Whole-course follow-up | Enqueued 08:14:50; all 18 geometry assets complete 08:16:53.697; last PNG 08:16:55.870; journal terminal `ready` at 08:16:55. |
| Watch after readiness | Package 200 at 08:16:41.026 and 08:17:54.421, with no further prep or topo request. |

Per-hole retained file milestones:

| Hole | Garmin ZIP written | Decoded mesh written | Release-bound geometry ready | Topo PNG written | Geometry-ready → PNG (queue + render + cache write) |
|---|---|---|---|---|---|
| 1 | 08:14:42.665 | 08:14:49.672 | 08:14:54.893 | 08:15:20.277 | 25.384 s |
| 2 | 08:14:42.254 | 08:14:49.424 | 08:14:53.231 | 08:15:15.013 | 21.782 s |
| 3 | 08:14:55.952 | 08:14:58.575 | 08:15:11.511 | 08:15:29.583 | 18.072 s |
| 4 | 08:14:57.117 | 08:15:00.210 | 08:15:06.350 | 08:15:24.360 | 18.010 s |
| 5 | 08:15:08.320 | 08:15:10.318 | 08:15:12.659 | 08:15:32.342 | 19.683 s |
| 6 | 08:15:12.290 | 08:15:14.267 | 08:15:22.368 | 08:15:34.975 | 12.607 s |
| 7 | 08:15:13.815 | 08:15:17.668 | 08:15:22.485 | 08:15:37.731 | 15.246 s |
| 8 | 08:15:23.017 | 08:15:25.132 | 08:15:50.211 | 08:15:54.493 | 4.282 s |
| 9 | 08:15:23.724 | 08:15:26.216 | 08:15:28.221 | 08:15:41.048 | 12.827 s |
| 10 | 08:16:00.854 | 08:16:03.052 | 08:16:26.454 | 08:16:32.041 | 5.587 s |
| 11 | 08:15:57.841 | 08:15:59.659 | 08:16:06.695 | 08:16:09.958 | 3.263 s |
| 12 | 08:16:07.983 | 08:16:10.721 | 08:16:13.717 | 08:16:16.970 | 3.253 s |
| 13 | 08:16:15.026 | 08:16:17.367 | 08:16:20.254 | 08:16:23.914 | 3.660 s |
| 14 | 08:16:21.569 | 08:16:24.324 | 08:16:26.516 | 08:16:35.828 | 9.312 s |
| 15 | 08:16:27.888 | 08:16:30.505 | 08:16:35.346 | 08:16:40.727 | 5.381 s |
| 16 | 08:16:28.147 | 08:16:31.130 | 08:16:45.161 | 08:16:47.853 | 2.692 s |
| 17 | 08:16:36.312 | 08:16:40.859 | 08:16:46.426 | 08:16:50.912 | 4.486 s |
| 18 | 08:16:46.426 | 08:16:48.520 | 08:16:53.696 | 08:16:55.870 | 2.174 s |

**Does cold prep block on rasters? No.** The production `/prep?render=false` path checks mesh/hazard release authority and computes route/projection/facts; it does not check the topo cache or wait for the install's `topoReady`. The package's per-hole geometry readiness likewise comes from geometry authority, independently of raster readiness. The install's overall `phase=ready` does require both, but it is a different gate. Hole 1's vector could be built after 08:14:54.894; its raster finished 25.383 seconds later. The Watch decoder prevents that vector package from being consumed, and #425's status-only phase additionally needs the geometry-progress change requested in P2.

**When did the package first report non-pending?** Access logs retain HTTP status and completion time, not the old JSON body. The first authority-eligible hole was hole 2 at 08:14:53.232; the first subsequent recorded package completed 08:14:54.917 for the whole-course template, then 08:14:59.758 for the active front nine. I cannot assert their exact hole states from HTTP 200 alone. The current authenticated replay confirms 9/9 package rows ready and nine route-only seeds with null images.

There are no retained per-stage request starts or per-hole render-start/CPU timers for this incident. The final column is explicitly an elapsed **queue + rendering + write** interval, not pure render CPU time. The current file/journal facts do not establish which other course work delayed a render. Current release-file replacement also prevents reconstructing the original CourseView network duration. Adding correlated phase start/end telemetry is needed to answer those subdurations exactly next time.

Present-time authenticated loopback measurements: first package **110.098 s**, then three-hole `render=false` prep **4.223 s**, status **0.032 s**. A subsequent package replay was **3.255 s** (Server-Timing total 3.116 s: history 27.9 ms, release lookup 2.4 ms, facts package 1419.7 ms, caddie/route seed 1633.2 ms, serialization 27.9 ms). These demonstrate a substantial cold-process/cache penalty; they do not identify which uncaptured stage caused the initial 110 s, and are not historical Watch-side timings. The earlier P1 source reference is `WatchCourseDownload.swift:912`.

Private persistent evidence: `/home/jason/garmin-ai-caddie-data/operations/pr425-c4fdddc9-20261014/{server-assets.json,request-timeline-28242.log,server-responses.jsonl}`. No credentials are included in these captures.


## Review result at c4fdddc9

Hold merge for P1 route-only-map decoding and P2 geometry/generation progress polling. Comments: [P1](https://github.com/jasonhorga/garmin-ai-caddie/pull/425#issuecomment-6172993813), [P2](https://github.com/jasonhorga/garmin-ai-caddie/pull/425#issuecomment-6173026392), [timeline](https://github.com/jasonhorga/garmin-ai-caddie/pull/425#issuecomment-6173093641). Claude owns the product fixes; Codex continues exact-head re-review.

Ordinary CI `38594117892` and Native `38594117897` passed at exact PR head `c4fdddc9abb601aaefd599f6b31019a92a6680ec`. Native build evidence references GitHub's synthetic merge commit `9f330b2e9abb10a52f4aeba6a9bf7dc33139f1b3`; the Actions source head is c4fdddc9. All 47 Watch and 97 iPhone/design PNGs were downloaded and compared individually: every SHA-256 matches the previously inspected #424 design baseline. No changed screenshot or UI-layout regression is present; these fixtures do not exercise the failing cold response.

Remote exact-head checks: `tests/test_mobile_contracts.py` 126 passed; `tests/test_native_visual_parity.py` 12 passed. Existing API image's /app/.venv was reused in one temporary network-disabled container, with read-only source and tmpfs data. No dependencies were installed and no production configuration, service, backend revision, player data, public route or token changed.

The direct null/string mismatch is established by the current production wire payload and exact Watch source. Native's passing fixture suite does not constitute execution of that real failing response. A behavioral regression test remains required for the author's fix.

The original morning request bodies and phase-start timers are unavailable. Preserve this limitation: file times are completion milestones, not measured pure network/CPU durations. The present 110.098-second cold-cache observation also lacks its stage header; the 3.255-second repeat has the recorded header and cannot be substituted for the cold observation.

