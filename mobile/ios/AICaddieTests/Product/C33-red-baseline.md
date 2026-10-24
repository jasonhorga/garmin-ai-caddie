C33 baseline: origin/main c2ddbd93. These are separate XCTest classes, never
LiveRoundAppModelTests. Native XCTest and swiftc are unavailable on this Linux host.
No native red or green execution is claimed.

The test-first commit specifies the injection/access seams implemented in the
next commit (roundStartTimeoutInterval/roundStartFailure, LiveTopoAvailability,
GarminRasterImageStore clock/loader, GreenDetailImageResolver, quarantine reader).
Before those seams exist native compilation is red. The intended behavioural reds
against the original implementations after exposing the seams are:

* Start priority: oldCancelled expectation times out; old package is not cancelled.
* Start deadline: request timeout is 120 (>30), isPreparingRound remains true and
  roundStartFailure is absent when the injected deadline expires.
* Topo: XCTAssertNotNil(url) fails with ready package/partial prep.
* Retry: attempts is 3 rather than 4; image nil; last state numericPlaceholder;
  nextPlan after repeated failures is nil rather than a 60 s plan.
* Green: selection has no cropped bitmap for null map.image; expected topo and
  Garmin fallbacks are absent.
* Strategy: unknown-route/driver-3w/route:7I pass straight through to club events,
  violating the explicitly hand-written three-value allowlist.
* Queue: the 5-event batch repeatedly receives 422; accepted count 0 instead of 4,
  pending count 5 instead of 0, no durable quarantine record.

Expected constants are taken directly from the C33 card (1 s, 30 s, four successes
plus one quarantined event, three server enum values, retry cap 60 s) and the
requested first retry slots (5 s, 15 s), followed by exponential 30 s, 60 s.
