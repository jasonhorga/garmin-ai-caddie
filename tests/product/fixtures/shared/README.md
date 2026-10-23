# Shared product vectors

Synthetic, hand-calculated inputs and expected results for Python and Swift.
These files do not derive expectations from the old fixture sets or product code.
All documents have `schemaVersion: 1` and a `cases` array. `id` identifies a data
row; `handCalculation` explains its independent arithmetic.

## tee_result.json — 5.8

Coordinates are `[latitude, longitude]` in degrees, invented near the equator.
Each row supplies `par`, nullable `point`, nullable `fairwayOutline`, `route`,
and nullable `expected` (`hit`, `left`, `right`). Outline version 1 contains
`polygons`, each with `outerLatLon` and `holesLatLon` arrays. No position means
no second-shot or first-putt position. Edge tolerance is 0.5 m. A missing route
prevents left/right classification; containment still proves a hit.
The cutout and disconnected-component rows must not be treated as their convex
hull. Direction is the direction from the first route point to the last.

## loop_map.json — 4.3

`courses` is authoritative test input: `globalId`, `holeCount`, `venue`, `name`.
81001 is one 18-hole course; 82001/82002/82003 are the three distinct 9-hole
courses of one 27-hole venue. These IDs are synthetic.
Each case supplies `pathGlobalId`, the HTTP `loops` query, `expectedLoopKey`,
and `expectedHoles`. Each hole is a **four-element array**, whose columns are
listed in `holeColumns`: `[number, sourceGlobalId, sourceLocalHole,
courseHoleNumber]`. Compare the entire table, including order and all holes.
`number` is the round slot; `(sourceGlobalId, sourceLocalHole)` is the physical
identity. `courseHoleNumber` is the displayed number: physical local hole for
one 18-hole course; round slot for distinct nine-hole courses. In particular,
a repeated physical loop restarts `sourceLocalHole` without restarting the
round slot. Single-loop cases have exactly nine holes.

## caddie_golden.json — 5.11 / 4.6

All distances and local coordinates are metres, x east / y north. Two holes,
each with two parallel tee positions, use a straight factual `routeLocal` from
`ballLocal` to `pinLocal`. `par`, `shotType`, `distanceToPin_m`, `clubProfiles`
and `openingClubs` are input facts; the three opening clubs describe supplied
prep candidates, not a selected answer. Profiles contain `median_m`, `p10_m`,
`p90_m`, `sampleSize`. A consumer adapts these input facts to its evaluator.
Each `expected` item is keyed by strategy `id` (`safe`, `stock`, `attack`) and
contains the full ordered `clubNames`, cumulative `routeOffsets_m`, projected
`landingsLocal`, and zero-based `planIndices`. Python checks decision sequences;
Swift checks the same sequence plus route projection. Do not feed `expected`
into the planner. The two positions have equal distances but translated landing
coordinates; an evaluator cannot hard-code an origin of (0,0).
The three strategies differ in first club and at least one route offset. Safe
uses three equal short shots, stock two equal medium shots, attack a long shot
then a short shot. The bag deliberately requires the safe/stock repeat fallback.
