# PR #389 live course-selection evidence

Reviewed source: `56022d326edf7b4cc789f9ecea818ceb6da50805`.
Live run: [37519627055](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/37519627055).

The four request-lifetime findings are resolved. This live run failed before
starting a round, so it provides no final enrollment/relaunch acceptance.
The original journey assertion remains intact; approval is pending.

## Direct observations

- XCTest's back-nine journey starts at 19:53:10 UTC and fails at 19:54:58,
  `RealFlowUITests.swift:70`, missing `start-round-course-half-31793-back`.
- Verified simulator video shows a data-empty home around 19:53:24–32,
  an empty start-course list and nearby spinner at 19:53:56–19:54:07,
  then an empty list with the retry icon at 19:54:17–52.
- The helper searches for `start-round-venue-31793` through 24 swipes,
  then a front-half tile through eight; it returns without verifying
  selection. The back-half assertion therefore reports a failed prerequisite.
- PID 50615's retained latency trace has `round-home.appear` and a local
  31795 activation about 60 seconds later, without course-start/queue release.
  No evidence establishes that activation as the cause of the missing row.
- API response logs have a gap from the 19:49:12 catalogue preflight until
  19:55:01 health. cloudflared records incoming-request cancellations during
  the failing test. These facts establish response failure, not its layer.
  A lack of release-file writes cannot rule out an unfinished upstream fetch.

## Screenshot and source verification

All five build/screenshot ZIP digests and the video ZIP digest are verified.
The full-live comparison index has zero missing, added or changed files:
89 iOS and 47 Watch design PNGs equal the individually reviewed #387 baseline.
All 86 iOS and 13 Watch runtime PNGs were visually inspected against the design
README, approved layouts and nine-loop plan. The unrelated dark iOS system
status-bar text remains a recorded nonblocking issue.

The Watch capture resets and checks its own rendered marker before each
screenshot; unknown/unrendered routes fail the step. This is page-route proof.
`watch-round-seeded.png` contains a map waiting page, so it is not evidence
that precise course geometry finished loading. These Native captures remain
simulator evidence, not paired physical-device testing.

## Next verification and retained evidence

One further full-live run on the unchanged exact head is justified by the
observed selection prerequisite failure. It must keep the original assertions
and record simultaneous origin/tunnel health latency and bounded logs. A
repeated failure requires diagnosis from that trace, not another blind run.

Evidence root on homeserver:
`/home/jason/garmin-ai-caddie-data/operations/pr389-56022d32-20261006/full-live-37519627055`.
Video ZIP artifact 11443055917 SHA-256:
`f4ef44ec8a2b8591c9a185f794fa19974dda40ac82ea3f5d108f65d4eb5dcbbc`.
Eleven bounded frames, two sheets and approximate wall-time index are retained
in `video-evidence/failed-selection`; original video remains unchanged.
The temporary renderer container was automatically removed. Local review
copies expire October 7 21:15 UTC; persistent originals remain on homeserver.

## Observed-run enrollment success and remaining tap evidence

[37534118109](https://github.com/jasonhorga/garmin-ai-caddie/actions/runs/37534118109)
ran the unchanged head and original assertions. The back-nine→front-nine /
relaunch / complete prep-course journey passed in 253.888 s; the main full
flow passed in 1,065.894 s. All five evidence ZIP digests passed verification.
The observer's 105 origin health samples all returned 200; tunnel health
returned 200 in 103/105, with two connection timeouts away from the tee tap.
The observer, sampler and waiter closed at 22:24:57 UTC with a closure receipt.

Native's sole failure was `TeeSelectionUITests.swift:142`, White not selected.
`03-tee-row.png` visibly has half the tee dots behind the fixed Start band.
Its tree gives White y=730.7–787.0 and Start y=759.7–810.0, yet the test's
viewport excludes only the home-indicator lane. After the 22:06:33 White tap,
the API responds to a new Blue/前九 round package at 22:06:38. The selection
assertion then cannot find White. The tunnel health at 22:06:32 was 200/0.388 s.
This is a different failure from the first empty catalogue.

P2 verification correction: exclude the entire fixed action band/padding
from the scroll viewport, recheck before tap, retain White/action-label
assertions and verify the start page remains until an explicit Start tap.
Inspect the same RealFlow helper and save screenshot/tree on prerequisites
failing. Final merge remains pending this concrete failure's correction.

## Completed observed-run visual review

All 91 iOS and 13 Watch runtime PNGs in run 37534118109 have now been
visually inspected, including the final iOS nearby-GPS capture and both Watch
contact sheets. All 89 iOS / 47 Watch design PNGs remain byte-identical to the
approved baseline. The remaining tee-tap P2 is not cleared by that equality.

A separate nonblocking layout follow-up appears in
`09d-new-course-lightweight-map.png`, `b4b2-02-back-nine-first-hole.png` and
`b4b2-04-front-nine-round-hole-10.png`: the facts-only hole hugs the left edge
while most of the canvas is empty, and its upper club label overlaps the
fixed `洞位图` control. Fit the available map bounds with margins and place
labels outside fixed-control bounds. These runtime frames are not visually
clear merely because the fixture design frames have not changed.

The final GPS capture shows populated nearby Chinese course names and
distances; it is simulator location evidence. Watch route and waiting-state
limitations above still apply, as does the existing status-bar contrast
follow-up. Original enrollment acceptance stays passed; approval still waits
for the usable-viewport correction and targeted live White selection.

The source snapshot and all temporary test/render containers are closed;
the observer, sampler, artifact downloaders and CI waiter have completed.
Persistent originals are retained on homeserver. Local review copies remain
available for comparison until their recorded October 7 21:15 UTC expiry.

Author comment 6026596438 proposed either an unchanged targeted rerun or a
separate test fix. Codex chose the separate fix: stable coordinates alone
do not prove that a chip is outside the fixed footer. Use the actual usable
viewport, recheck before tapping and preserve White/start-page assertions.
PR #390 diagnostics are merged, so the author can base that fix on main.
