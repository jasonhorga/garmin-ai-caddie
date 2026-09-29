# B4b-2 contract proposal: an 18-hole course played as two halves

Status: **proposal for owner decision**. Implementation waits for the decisions in §6.

README §8: a single 18-hole course with two halves follows the same flow as a 27-hole venue.
The player picks the first loop (前九 or 后九), then picks the second loop at the turn. The
second loop can be the same half, can be changed until its first hole is played, and is
locked after that. The plan requires all four orders (前→前, 前→后, 后→前, 后→后) and
lock-before/after tests.

## 1. What exists today (facts)

- **Holes.** Each package hole has `number`, `sourceGlobalId` and `sourceLocalHole` (`_package_holes`).
  - For 9-hole loop compositions, `number` is already the round order (1–18) and
    `sourceGlobalId` / `sourceLocalHole` are the physical loop and hole (`_merge_nines`,
    `composingBackNine`).
  - For a single 18-hole course, `number == sourceLocalHole`. `nine=back` returns holes
    **10–18** (`test_mobile_course_package_can_start_a_chosen_nine`). No request can put
    physical 10–18 at round positions 1–9, or physical 1–9 at 10–18.
- **Events.** `LiveRoundEvent.hole` and the server projection key everything by
  `number`. Neither side maps events to physical holes.
- **Lock.** The second-loop lock is "any event with hole > 9" (`CurrentHoleView`).
- **Local and online paths.**
  - Local composition takes the back package's first 9 holes by position.
  - Revalidation refetches with `nine` / `back_global_id` and matches prep rows by `number`.
- **Turn.** The turn plan only knows 9-hole catalogue loops, so an 18-hole course has no turn.

## 2. Proposed contract

1. **`number` is the round-order hole.** It is the only hole key everywhere: events, the
   projection, seeds, prep rows, recent history, scorecard columns and "继续第 N 洞". First
   loop = 1–9, second loop = 10–18, in the order played.
2. **Every hole carries its physical identity explicitly**: `sourceGlobalId` +
   `sourceLocalHole`. For a single 18-hole course, `sourceLocalHole` is the physical 1–18.
   Geometry, topo, install refs and stats loop keys (plan: `gid:10-18`) use only this.
3. **New package field `roundLoops`.** It is
   `[{ "globalId": Int, "half": "all"|"front"|"back", "firstHole": 1|10 }]`: the round's
   loops in play order. This is the single mapping that local composition, revalidation
   and the lock read.
4. **Request.** `GET /api/v2/mobile/courses/{globalId}/package?loops=G:H[,G2:H2]`, where
   `H` is `all` for a 9-hole loop and `front` / `back` for a half of an 18-hole course. The
   first entry's `G` is the path id. The server builds each distinct course once (`nine=all`),
   selects each loop's physical holes by `sourceLocalHole` (front 1–9, back 10–18, or the
   loop's 9), renumbers them in round order, and shifts seeds / prep / history / weather /
   priority holes with the existing `_merge_nines` machinery.
   - 前→后 = `G:front,G:back`
   - 前→前 = `G:front,G:front`
   - 后→前 = `G:back,G:front`
   - 后→后 = `G:back,G:back`
   - A first-loop-only start is one entry.
5. **Local composition** (offline turn): the second loop comes from the installed whole-course
   template (`nine=all`, 18 physical holes). Select the half by `sourceLocalHole`, renumber it
   10–18, and append to `roundLoops`. Revalidation refetches with the package's own
   `roundLoops`, so online and offline produce the same `(number → sourceGlobalId,
   sourceLocalHole)` table.
6. **Lock**: unchanged rule, now correct for every order. The second loop is locked once any
   event has `hole >= roundLoops[1].firstHole`.
7. **Turn**: an 18-hole course offers its halves as loops named 前九 / 后九 (ids `G:front` /
   `G:back`). The other half is preselected, the same half is allowed, and "只打 9 洞" is
   allowed. This is the same `NineLoopPlan` state machine. The start screen shows 前九 / 后九
   tiles and "从 后九 开始 · 蓝 T".

## 3. Displayed hole number

**Recommendation: show the physical hole for a half of an 18-hole course, and the round
order for 9-hole loop combinations.**
- A 后→前 round shows 第 10…18 洞, then 第 1…9 洞, which matches the course's own hole signage.
- A+B at a 27-hole venue keeps today's 1–18.

Each hole would carry `displayHole`, set by the server and by local composition, used only
for text. Navigation, keys and the lock stay on `number`. The scorecard's two cards become
"第一环 / 第二环", labelled by loop name (前九 / 后九 / A 场), with OUT/IN = first / second
loop.

## 4. Existing parameters

`nine` and `back_global_id` would be removed from the iOS client in this PR, with every start,
turn and revalidation going through `loops`.
- On the server they become an internal translation to `loops` (`nine=back` → `G:back`),
  because other callers still send them: the Watch course download (`WatchCourseDownload`,
  until B6) and the web install-status call (`web_v2/src/api.ts` `fetchCourseInstallStatus`).
  The translated `nine=back` would then return round holes **1–9** (physical 10–18), not
  10–18.

## 5. Acceptance tests

- **Server:** the four orders plus first-loop-only front/back. Check `number` 1–18,
  `sourceLocalHole`, `displayHole`, `roundLoops`, and seeds / prep / history / weather on the
  round numbers. Also check the `nine` / `back_global_id` translation, and that the install
  refs use physical holes.
- **Client:**
  - Local composition of the four orders from the whole-course template equals the
    server table.
  - Revalidation keeps the mapping.
  - The lock holds before and after the first second-loop event.
  - The turn plan offers 前九 / 后九 with the same half allowed.
  - Start-screen tiles.
- **Real journey:** the RealFlow 18-hole round starts 前九, takes the turn after hole 9, and
  continues 后九 on hole 10. A second fixture journey starts 后九 and continues 前九. The CI
  fixture server gets the same `loops` resolver.

## 6. Decisions requested

1. The contract in §2: round-order `number` as the only key, physical identity on each hole,
   `roundLoops`, and the `loops=` request.
2. The displayed hole number in §3: physical for 18-hole halves (recommended), or round
   order everywhere.
3. §4: whether `nine=back` may change to round holes 1–9 for the remaining callers, or must
   keep 10–18 until those callers move.
