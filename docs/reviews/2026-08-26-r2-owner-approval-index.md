# R2 HMB Owner Approval Index

**Scope:** visual approval only; no credentials or private source data are stored here.
Technical evidence is complete for the deterministic Half Moon Bay round; owner
approval remains open.

## Evidence Sources

| Surface | Run / artifact | Technical facts already verified | Owner decision still required |
|---|---|---|---|
| iOS simulator | GitHub Actions run `32919313329`; head `e484ac37`; `real-screenshots` artifact `9589881940`; `real-video` artifact `9589884098` | iOS XCTest 257/257; selected UI tests 9/9; resolver round `17603881`, Ocean hole 1, `globalId/localHole=6022/1`, shotCount 3, Driver/5I; secret scans passed; no correction/sync writes | Approve each image's first-frame, map, data and navigation state; confirm no visual mismatch with Web |
| iOS build/design | Native build artifact `9589887946`; design artifact `9589420299` | iOS build passed; 30 design snapshot files scanned successfully | Approve design context only where used for comparison |
| Web HMB owner run | GitHub Actions run `32944143003`; head `8419840b`; job `98101156667`; artifact `9597641080` | `1/1` passed in 39.8s; six artifact files, 821,477 bytes; overview/detail/shotmap/topo 200; shotmap `found=true`, `globalId=6022`, `localHole=1`; topo holes 1/2 `image/png`; secret scan passed; zip SHA-256 `d321b5816904214abcc37c1f231e02fb844ed7dc2a47e667d83d0b04f454f375` | Approve each image's map/topo, HMB round selection and first-frame state |
| Web baseline reference | GitHub run `32847990023`, artifact `9563119622` | Stable Funnel CI-player journey and six non-empty PNGs; not HMB-specific | Use only as transport/layout context, not as HMB proof |

## iOS Screenshots

All files below are in artifact `9589881940`; each was non-empty and included in
the successful secret-byte scan. The owner should approve the stated visual
purpose and compare the HMB-specific rows against the Web rows below.

| File | Review purpose | Verified fact | Owner judgment |
|---|---|---|---|
| `01-home.png` | Home first frame | App home rendered in real iOS simulator | Approve first-frame hierarchy |
| `02-results.png` | Results landing | Results surface rendered | Approve navigation/data framing |
| `02-start-round.png` | Start-round entry | Start-round surface rendered | Approve entry state |
| `02b-start-round-selected.png` | Selected course state | Course selection rendered | Approve selected-course clarity |
| `02b-trends.png` | Trends surface | Trends rendered | Approve chart framing |
| `02c-analysis.png` | Analysis surface | Analysis rendered | Approve analysis hierarchy |
| `03-history-list.png` | History list | Archive list rendered | Approve round list scanability |
| `03-tee-menu.png` | Tee menu | Tee selection rendered | Approve tee options |
| `03b-history-real-round.png` | HMB history entry | Resolver-selected HMB round is present | Approve round identity |
| `04-round-review.png` | HMB review first frame | Round `17603881`, Ocean, hole 1 context | Approve review first frame |
| `04-white-tee-selected.png` | Tee selection within review flow | White tee state rendered | Approve state distinction |
| `04b-shot-map.png` | HMB shot map | `globalId/localHole=6022/1`, shotCount 3 | Approve map geometry and shot order |
| `04c-edit-mode.png` | Edit mode | Review edit controls rendered | Approve edit affordances |
| `04d-edit-cancelled.png` | Cancel recovery | Cancel state rendered; no correction write | Approve unchanged post-cancel state |
| `05-last-round-review.png` | Last-round shortcut | Last-round review rendered | Approve shortcut consistency |
| `denied-01-start-round.png` | Denied fallback | Denied/limited state rendered | Approve safe fallback |
| `edit-00-home.png` | Edit flow home | Edit suite home rendered | Approve entry context |
| `edit-01-history-list.png` | Edit flow archive | Archive list rendered | Approve target selection |
| `edit-02-round-review.png` | Edit flow review | HMB review rendered | Approve review context |
| `edit-03-shot-map.png` | Edit flow map | HMB map rendered | Approve map baseline |
| `edit-04-edit-handles.png` | Edit handles | Handles rendered | Approve handle discoverability |
| `edit-05-add-draft.png` | Add draft | Draft shot rendered | Approve draft distinction |
| `edit-06-edit-sheet.png` | Edit sheet | Edit sheet rendered | Approve sheet content |
| `edit-07-drag-move.png` | Drag move | Dragged draft rendered | Approve movement result |
| `edit-08-delete-draft.png` | Delete draft | Delete state rendered | Approve delete affordance |
| `edit-09-reorder-draft.png` | Reorder draft | Reorder state rendered | Approve order feedback |
| `edit-10-edit-done.png` | Edit completion | Completion state rendered | Approve completion presentation |
| `empty-nearby-01-start-round.png` | Empty nearby fallback | Empty-nearby state rendered | Approve fallback wording |
| `no-fix-01-start-round.png` | No-fix fallback | No-fix state rendered | Approve fallback wording |
| `offline-cache-01-online-ready.png` | Offline cache recovery | Online-ready state rendered | Approve recovery clarity |
| `offline-start-01-new-first-hole.png` | Offline start | Offline first-hole state rendered | Approve offline state |
| `real-core-location-01-nearby.png` | Real location path | Nearby result rendered from simulator location | Approve location result framing |

## Web Screenshots

The GitHub Web-only run produced these six files. They are listed for
comparison; PNGs are intentionally not copied into this repository or public
`/demos`. The earlier homeserver owner-only run remains supplementary history:
it verified the same HMB request path and visuals, but is not the primary Web
row above.

| File | Review purpose | Verified fact | Owner judgment |
|---|---|---|---|
| `results-overview.png` | Results first frame | Overview request 200 | Approve first-frame hierarchy |
| `time-trends.png` | Trends | Trends data rendered without load error | Approve trends hierarchy |
| `performance-analysis.png` | Performance | Performance data rendered without load error | Approve analysis hierarchy |
| `rounds-list.png` | Deterministic round selection | HMB round ref `17603881` selected | Approve identity/date/score |
| `review-workbench.png` | HMB map workbench | Shotmap found, `globalId=6022`; topo 200 | Approve map/topo alignment |
| `round-review.png` | HMB round review | Detail 200 and review content ready | Approve review first frame |

## Timing Boundary

The first two GitHub attempts, runs `32942764978` and `32943661246`, stopped at
the overview 60-second transport wait. Service diagnosis found no 5xx; these
were transport/evidence collection failures, not product errors. The third
attempt, run `32944143003`, completed successfully as recorded above.

iOS event-latency files report only `round-home.appear pending=-1 course=31796`
at approximately 1.38--1.65 seconds. This is not a complete review-topo
first-frame measurement. Owner approval must therefore be based on the actual
images and visible state, not that proxy timing.
