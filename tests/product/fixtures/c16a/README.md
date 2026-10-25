# C16a inputs and independent answers

These are invented records for one Paper Links layout (900001), not a Garmin
export. No input or assertion is copied from the old test suite.

- Round 101: eighteen par-four holes, each 4 strokes / 2 putts / 0 penalties:
  72 strokes, par 72, 36 putts. Round 102 on the next day has eighteen fives:
  90 strokes; the two-round average is (72 + 90) / 2 = 81. Round 103 is still
  in progress and contributes nothing. Each finished round has three recorded
  full shots in hole 1: Driver 200m, 7I 100m, PW 20m. The synced roster has one
  Driver with advice distance 200m. Partial shot and geometry availability do
  not change the scorecard arithmetic.
- For half-round rows, the first nine fours total 36 and the second nine fives
  total 45. The merged result is 81 strokes / par 72 / 36 putts. Its display
  holes are 1..18; the first card's shots belong to display hole 1 even when
  Garmin numbers that card 10..18, and the second card's shots belong to 10.
  Manual-first and Garmin-first rows each leave exactly the Garmin round 101
  visible, while the manual source remains on disk.
- The mesh is a straight 300m route, a 40m-wide fairway rectangle and a 20m
  green square. The fake installer replaces the external binary acquisition
  and decoder, writes these committed inputs and can fail. Actual dependency
  discovery, snapshot creation and shot-map projection are exercised. Geometry
  decoding accuracy belongs to J4, outside this card.
- J3 establishes a client-authored pixel snapshot: Driver (80,960)->(160,680),
  7I ->(240,380), PW ->(320,160). The geometry revision read from the server is
  used only as an input frame token, never as an expected value. A single move
  of the second landing to (280,440) changes that landing and reconnects the
  next start; it produces exactly one move entry. Moving it again to (300,460)
  must describe (280,440) as the before value. A changed frame produces no
  position entry. `audit-golden.json` spells out all expected operations,
  indices, before/after values and hole numbers; expected logs are never
  generated from a server read or a product diff function.
- Reassigning the sole 100m 7I shot to 6I leaves Driver 200m and PW 20m. Adding
  one shot makes four, deleting one leaves two. Changing hole 1 from two putts
  to one makes 35 round putts; changing four strokes to six makes 74 strokes;
  changing zero penalties to one makes one round penalty. These are the
  independent answers used for the projection KNOWN-RED tests. A penalty
  correction only marks strokes as penalties and never changes the total, so
  4 strokes / 2 putts allow at most 4 - 2 - 1 = 1 penalty (spec 5.7); the
  `penalty` row in `audit-golden.json` is therefore before 0 / after 1.
- Correcting shot 2's start lie to Bunker also identifies shot 1's landing
  (the same connected point) as bunker: the Driver has one bunker landing.
  Reordering the three IDs as 3/1/2 gives PW/Driver/7I, numbered 1/2/3.
  The additional move row places the 7I landing at its snapshot start
  (160,680), so its review distance is exactly 0m; no projection or scale
  helper is needed to calculate this answer. These three statistics/review
  checks are separate KNOWN-RED tests, rather than masking passing map rows.

The HTTP routes, append-only JSONL stores, locks, cached file readers, audit
and repair code are real. `Sandbox` binds them to a temporary tree populated
only from these inputs. The outer process remains in fixture mode. The Garmin
HTTP adapter rejects every unlisted host/resource. Authentication runs the real
cache/refresh chain through a fake `mint_web_auth`; it never starts Playwright.
Statistics are primed before writes to exercise cache freshness. Independent
course-warming workers are disabled because they are unrelated to these
promises. No real account, browser or network is used.
