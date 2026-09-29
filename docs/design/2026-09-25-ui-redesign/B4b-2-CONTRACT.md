# B4b-2 contract: an 18-hole course played as two halves

Status: **approved direction, corrected contract** (owner review on PR #362). This document is
the contract the implementation follows.

README §8: a single 18-hole course follows the same flow as a 27-hole venue. The player picks
the first nine (前九 or 后九) and picks the second at the turn. The second can be the same
half, can be changed until its first hole is played, and is locked after that. Acceptance
covers 前→前, 前→后, 后→前, 后→后 and lock before/after.

## 1. What exists today (facts)

- **Package holes.** They carry `number` and optional `sourceGlobalId` / `sourceLocalHole` (the
  iOS model falls back when these are missing).
  - For 9-hole loop compositions, `number` is already round order.
  - For a single 18-hole course, `number == sourceLocalHole`, and `nine=back` returns holes
    10–18.
- **Events and lock.** Events and the server projection key on `number`. The second-loop lock
  is "any event with hole > 9".
- **Identity stores keyed on `nine` / `back_global_id`.** None of these can tell the four
  orders of one 18-hole course apart:
  - the server package single-flight key (`server_v2/mobile.py`);
  - the install journal id (`server_v2/course_install.py`);
  - the Watch template `cacheKey` / `matches` (`WatchCourseDownload.swift`);
  - the iOS revalidation request;
  - the web install-status call.
- **Schema.** The package schema is `ai-caddie-live-round-package-v1`.

## 2. Coordinates

There are two axes, and no field serves both.

| Axis | Values | Used for |
| --- | --- | --- |
| Round hole: `number` | 1–9 = first loop, 10–18 = second loop, in play order | events, projection, navigation state, score aggregation, the lock, source refs (`{roundId}:{number}`), seeds / prep / history / weather keys |
| Physical hole: `sourceGlobalId` + `sourceLocalHole` | the loop's Garmin id; its hole 1–9 (9-hole loop) or 1–18 (18-hole course) | geometry, topo, install refs, stats loop keys, tee yards |
| Presentation: `courseHoleNumber` | half of an 18-hole course → `sourceLocalHole`; 9-hole loop (`all`) → `number` | text only: live header, "继续第 N 洞", scorecard, summary, review, Watch |

`displayHole` keeps its existing meaning (the round-order key in caddie seed context) and is
not reused.

## 3. `roundLoops` and the canonical loop key

Every package carries `roundLoops`, the round's loops in play order:

```json
[
  { "globalId": 41825, "half": "back",  "roundStartHole": 1,  "sourceStartHole": 10, "holeCount": 9 },
  { "globalId": 41825, "half": "front", "roundStartHole": 10, "sourceStartHole": 1,  "holeCount": 9 }
]
```

- `half`: `all` for a 9-hole loop; `front` / `back` for a half of an 18-hole course.
- `roundStartHole`: 1 for the first entry, 10 for the second.
- `sourceStartHole`: 1 for `all` / `front`, 10 for `back`.
- `holeCount`: always 9.
- Hole `number` `roundStartHole + i` maps to `sourceLocalHole` `sourceStartHole + i` on
  `globalId`.

**Canonical loop key** `loopKey` = the entries in order as `"{globalId}:{half}"`, joined with
`+`, e.g. `41825:back+41825:front`. It preserves order and duplicates, so 前→前
`41825:front+41825:front` and 后→后 `41825:back+41825:back` are distinct. The package carries
it as `loopKey`.

**Lock:** the second loop is locked once any event has `hole >= roundLoops[1].roundStartHole`
(i.e. 10). Nothing reads `sourceStartHole` for the lock.

## 4. API

`GET /api/v2/mobile/courses/{globalId}/package?loops=G:H[,G2:H2]&tee_box=…` and
`GET /api/v2/courses/{globalId}/install/status?loops=…&tee_box=…`.

The parser rejects ambiguous input with a 422:
- exactly one or two ordered entries; duplicates allowed;
- the path id must equal the first entry's `G`;
- `front` / `back` only when `G`'s authoritative course is 18 holes; `all` only when it is an
  authoritative 9-hole loop;
- every entry must resolve to exactly nine holes;
- all entries must belong to the same physical venue.

The server builds each distinct course once, selects each loop's physical holes by
`sourceLocalHole`, and assigns `number` in round order. It shifts seeds / prep / history /
weather / priority holes onto round numbers.

An 18-hole course is always requested as halves. The whole course in the usual order is
`G:front,G:back`.

**`nine` and `back_global_id` are removed** from the package endpoint, the install-status
endpoint, the install journal, the server models and every first-party caller: iPhone, Watch
and web. No translator ships. Any intermediate commit that still carries an old route keeps its
old semantics.

## 5. Identity stores (all keyed by `loopKey`)

- **Server:** the package single-flight key (replacing `nine` / `back_global_id`), the install
  job id and status lookup, and the install journal's recorded selection.
- **iOS:**
  - the package request, including every start, turn and revalidation;
  - the offline package and round restore;
  - the course-install back-loop inference, which is replaced by `roundLoops`;
  - local composition at the turn;
  - the remembered pairing.
- **Watch:** the selection, the template `cacheKey` / `matches`, the seeds, and WCSession round
  state.
- **Web:** the install-status call.

## 6. Strict, versioned contract

- The package schema becomes `ai-caddie-live-round-package-v2`.
- `roundLoops`, `loopKey` and, on every playable hole, `sourceGlobalId`, `sourceLocalHole` and
  `courseHoleNumber` are required. iOS and Watch decoding reject a v2 package missing any of them.
- Stored v1 templates and packages are invalidated and re-downloaded. Source identity is never
  fabricated from `number`.

## 7. Client behaviour

- **Start screen.** An 18-hole course shows 前九 / 后九 tiles, and the action reads
  "从 后九 开始 · 蓝 T". Its request is one entry: `G:back`.
- **Turn.** The halves are loops named 前九 / 后九 (loop ids `G:front` / `G:back`) in the same
  `NineLoopPlan` state machine. The other half is preselected, the same half is allowed, and
  "只打 9 洞" is allowed.
  - **Online:** the turn requests `loops=<first>,<second>`.
  - **Offline:** the turn composes from the installed whole-course template: it selects the
    half by `sourceLocalHole`, assigns `number` 10–18 and appends to `roundLoops`.
  - Both paths produce the same `number → (sourceGlobalId, sourceLocalHole)` table.
- **Scorecard / summary.** Two cards, one per loop, in play order. Each is labelled
  "第一环 · 后九" / "第二环 · 前九" (A/B/C: "第一环 · A 场"), and hole columns show
  `courseHoleNumber`. OUT/IN labels are dropped; a physical half is never relabelled.

## 8. Acceptance

- **Server:**
  - The parser rejects each invalid shape.
  - The four orders plus first-loop-only front / back produce `number` 1–18 (or 1–9),
    `sourceLocalHole`, `courseHoleNumber`, `roundLoops` and `loopKey`, with seeds / prep /
    history / weather on round numbers.
  - The four orders' `loopKey`, single-flight keys and install job ids are pairwise distinct.
  - Install refs use physical holes.
- **iOS:**
  - Local composition of each order equals the server table.
  - Offline round restore and revalidation keep `loopKey` and the table.
  - The lock holds before and after the first round-10 event, including 后→前.
  - The turn offers 前九 / 后九 with the same half allowed.
  - Start tiles and title.
  - Header / scorecard use `courseHoleNumber`.
  - A v1 package is rejected and re-downloaded.
- **Watch:** the four orders' template keys do not collide and survive restore; the round state
  carries `loopKey`.
- **Web:** install status by `loops`.
- **Real journeys.** The CI fixture server gets the same `loops` resolver.
  - The RealFlow 18-hole round starts 前九, takes the turn after hole 9 and continues 后九 on
    round hole 10 (shown 第 10 洞).
  - A second journey starts 后九 (shown 第 10 洞) and continues 前九.
