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
