# AI Caddie Master Product Spec

Date: 2026-05-25

## Purpose

Build AI Caddie as a complete personal golf intelligence product: extreme
history review and statistics first, then course-aware caddie decisions, then
offline-first mobile and watch capture.

This spec replaces the prototype-led direction. Existing code remains useful as
technical proof, but the final product should not be constrained by the old UI,
one-file server, or current partial v2 screens.

## Product Thesis

The product is valuable if it can answer two hard questions better than Garmin
Golf and GolfLive:

1. What exactly has changed in my golf over time, and what problems keep
   costing strokes?
2. Given my current position, course geometry, hazards, weather, and personal
   club model, what is the best plan for the next shot and the rest of the
   hole?

History is the memory layer. Caddie decisioning is the action layer. The first
complete build must make history and diagnosis excellent while keeping the
architecture ready for live caddie, iOS, Apple Watch, photo/video context, and
offline play.

## Final Product Boundary

The target is a complete personal product with a path to friends trial and
public release readiness. It is not a public commercial SaaS launch in this
build.

Required final capabilities inside this product boundary:

- Garmin CN Web Session connector for scorecards, shot data, and geometry
  dependencies.
- Official Garmin OAuth feasibility track as a replaceable connector path.
- Standardized local data snapshot independent of current login state.
- Full historical statistics across time, round, course, hole, club, issue,
  and data quality.
- Round, course, hole, and club review with drill-down to source rounds, holes,
  shots, and geometry evidence.
- Fact-bound AI review and explanation layer.
- Manual annotation and correction for tags, notes, missing/incorrect facts,
  and caddie feedback.
- Web app for deep review, analysis, admin, reports, and data quality.
- iOS app for live use, GPS, offline cache, score/club input, photos/videos,
  and sync.
- Apple Watch companion through iPhone for quick live input and at-a-glance
  decisions.
- Offline-first live round operation once a round starts.
- Cloud test/staging deployment path for remote development and private use.
- Evidence-bound caddie decision engine using course geometry, hazards,
  weather/context, and the personal club model.
- Future photo/video/camera-glasses context path without making vision a
  dependency for the first history build.

Explicitly outside this build:

- Garmin watch app. Garmin remains a data source only.
- Friend/group/team/tournament/PK/social product surfaces.
- Booking, course commerce, competition signup, and social feed.
- Practice range or simulator product. This can be a later product area, but it
  is not required for this build.
- Swing-instruction video coaching as a primary product. Photos/videos are used
  for lie/obstacle/context evidence first.

## Non-Negotiable Product Rules

1. No required capability is optional. Execution increments define build order,
   not whether the final product includes the capability.
2. Data acquisition and normalized fixtures come before UI polish. Historical
   statistics cannot be validated against empty data.
3. Every statistic and recommendation must expose source, coverage, confidence,
   and missing information.
4. Every AI narrative must be generated from structured facts and evidence. AI
   cannot overwrite verified numeric facts without an explicit correction flow.
5. Every important chart or aggregate must drill down to the rounds, holes,
   shots, and source fields that created it.
6. Login/session state must not block already-synced history review.
7. Live round capture must be offline-first. A round already in progress should
   keep working with cached course/player/club data and local GPS, then sync
   after the round.
8. Web, iOS, and Apple Watch share product semantics and visual language, but
   each platform owns its ergonomics.
9. The product should stay useful when geometry, weather, shots, or AI are
   unavailable by clearly degrading confidence instead of hiding the gap.
10. Do not store Garmin username/password in the cloud product path.

## Competitor Lessons

Garmin Golf is strong at clean personal data:

- compact round cards with course/date/score/to-par/hole strip
- scorecard-first round detail
- progressive scorecard expansion into FIR/GIR/putts/penalties
- phase-based stats: tee, approach, short game, putting
- course stats and simple club stats

GolfLive is strong at history breadth:

- history hub with many record modules
- month-grouped play timeline
- score distribution pyramid and histogram
- annual and quarterly summaries
- course distribution map
- round detail with AI review entry

AI Caddie should combine those strengths and go beyond both:

- data quality everywhere
- explanation of why scores changed
- course/hole history tied to shot geometry and hazards
- club model based on median, p10/p90, sample size, and confidence
- AI review bound to facts, not generic coaching text
- caddie plans that can be audited after the round

The product should not copy GolfLive social/team/tournament surfaces.

## Information Architecture

### Web

Web is the deep review and control surface:

- Overview
- History
- Rounds
- Courses
- Holes
- Clubs
- Issues
- Caddie
- Sync & Data Quality
- Reports
- Settings

Web should prioritize dense scanning, drill-down, comparison, and correction.
It is not a marketing site and should not open on a landing page.

### iOS

iOS is the live and mobile review surface:

- Today / Round in Progress
- Start Round
- Current Hole
- Caddie Plan
- Quick Score / Club Input
- Photo / Video Context Capture
- Offline Package Status
- Recent Round Review
- Sync Status

iOS can also host the CN Web Session connector because it can own a controlled
login surface and local secure storage. Public release risk must be reviewed
before depending on this as a commercial path.

### Apple Watch

Apple Watch is a fast companion, not a full analytics surface:

- current hole, par, distance, target note
- club suggestion and confidence
- quick selected club input
- score and putt input
- penalty marker
- next-shot prompt
- sync through iPhone

The Watch app must work during a round if the phone/network is unavailable, as
long as required offline packages were prepared.

## Visual Direction

Use a unified Garmin Pro visual language:

- quiet, precise, dense, and golf-native
- dark-on-light or carefully balanced neutral base
- strong score semantics and score strips
- green for par, light blue for birdie, deeper blue for eagle, warm danger
  tones for bogey/double+ and penalties
- maps and geometry as real evidence, not decorative fairway cartoons
- compact charts with clear drill-down affordances
- data quality chips near affected content
- cards only for repeated items, tools, and modals

Avoid:

- mini-program module clutter
- oversized hero/marketing compositions
- decorative gradient/orb backgrounds
- one-note purple/blue, beige, or dark-slate palettes
- nested cards
- abstract course drawings when real geometry or satellite context exists

## Data Sources

### Garmin CN Web Session Connector

Track 2 is the first implemented connector.

It uses the existing validated Garmin CN web session approach:

- scorecard summary endpoint
- scorecard detail endpoint
- shot-by-shot endpoint
- cookie plus `connect-csrf-token`
- local OAuth/DI token material where needed for prodgeometry

Product rules:

- Save session material, not Garmin username/password.
- Store secrets only in protected local/server secret storage.
- Never print cookies, CSRF tokens, OAuth tokens, or local secret paths.
- Session expiration becomes `reauth_required`.
- Already-synced data remains usable after session expiration.
- Sync produces versioned raw snapshots and normalized records.
- UI exposes connection state, last successful sync, next required action, and
  data coverage.

The initial Web implementation may include a manual secure paste flow for
cookie/CSRF to unblock personal use. The productized connector should be
designed so an iOS login surface or other connector implementation can replace
that input method without changing history analysis.

Mac local sync agent is not a recommended path.

### Official Garmin OAuth Feasibility

Track 1 is a backup validation path, not a first dependency.

Garmin Connect Developer Program uses OAuth 2.0 PKCE, but the public developer
surface does not prove that golf scorecard and shot data are available through
that program. Garmin Golf Premium API explicitly covers scorecards and GPS shot
data, but it is a partner/license product and should not be treated as available
for this build.

Feasibility questions:

- Can official OAuth access any golf round record?
- Can it access FIT files containing golf shots or scorecards?
- Can it access course or golf activity metadata enough to help history review?
- If not, can it still support identity or future migration?

The connector interface must allow an OAuth connector to replace the CN Web
Session connector later.

### Garmin Geometry

Use Garmin `prodgeometry` as the primary fine geometry source:

- fairway
- green
- bunker
- water
- rough
- teebox
- playable bounds

Existing prototype validation showed `prodgeometry` meshes align with Garmin
shot/raster references closely enough for surface classification and route
evidence.

CourseView IMG remains useful for coarse context and reverse-engineering, but it
is not the primary fine geometry source.

### Satellite / Map Context

Use WGS84 map sources. The prototype used Esri World Imagery without an API key
for validation. Do not mix GCJ-02 providers such as AutoNavi, Tencent, or Baidu
with Garmin shot/geometry coordinates because the offset breaks alignment.

For public release, evaluate a formal map provider and terms, such as ArcGIS
Location Platform or Mapbox. This is not required to validate history and
statistics.

### Weather

Weather is a context input, not a blocker for history.

Initial product path:

- Use no-key weather sources such as Open-Meteo where possible.
- Store weather by round/hole/time/location snapshot.
- Mark weather as missing when unavailable.
- Never infer weather in AI review unless recorded.

Later product path:

- Consider paid weather provider only if reliability, rate limits, or public
  release requirements demand it.

### AI Providers

The current repo has an Anthropic-specific `ai_caddie/llm.py`. The notebook repo
has a useful provider abstraction and an NVIDIA NIM OpenAI-compatible provider.

Required provider design:

- `static` provider for tests
- `anthropic` provider for current compatibility
- `nvidia_nim` provider using OpenAI-compatible `/chat/completions`
- `gemini_api_key` provider if needed
- `gemini_cli_oauth` only as a development/internal option, not production

Use provider interfaces for text and vision:

- text review
- structured explanation
- photo/video context analysis
- future real-time caddie narrative

AI provider errors must not leak keys, tokens, cookies, or raw private paths.

## Data Model

The system needs stable records independent of raw Garmin shape:

- `Connection`
- `SyncRun`
- `RawSnapshot`
- `Round`
- `HoleScore`
- `Shot`
- `Course`
- `Hole`
- `GeometryAsset`
- `WeatherSnapshot`
- `Club`
- `ClubProfile`
- `Issue`
- `Annotation`
- `Correction`
- `ReviewReport`
- `CaddieDecision`
- `DecisionAudit`
- `DataQualityFinding`

Raw Garmin files are preserved behind adapters. Frontend and AI never parse raw
Garmin JSON directly.

Each normalized fact should carry:

- source connector
- source file or snapshot id
- original field reference where practical
- confidence
- missing/derived/manual status
- last updated time

## Historical Statistics

History must cover these dimensions:

- Time
- Round
- Course
- Hole
- Club
- Issue
- Data Quality

Required history capabilities:

- all-round overview
- 18-hole and 9-hole separation
- same-day 9-hole merge logic where appropriate
- recent 5/10/20 trends
- year, quarter, month summaries
- score average, best, worst, median
- birdie/eagle/par/bogey/double+ counts
- score distribution bands and histogram
- play frequency
- course count and course distribution map
- course-specific average, best, worst, recent form
- hole-specific score distribution and repeated issue ranking
- club usage, valid samples, median, p10/p90, max, confidence
- shot count and shot coverage
- geometry coverage
- report coverage
- annotation and correction coverage

Every aggregate must drill down to the rounds, holes, and shots behind it.

## Issue Taxonomy

Use a two-layer taxonomy.

Layer 1: golf phase / product category:

- Tee
- Approach
- Short Game
- Putting
- Penalty
- Course Management
- Club Confidence
- Data Quality

Layer 2: scoring loss source or reason:

- OB
- water
- bunker
- other hazard
- tee position bad
- fairway missed left
- fairway missed right
- approach short
- approach long
- approach left
- approach right
- wrong club
- poor lie
- wind
- slope
- blocked view
- recovery failed
- three-putt
- too aggressive
- too conservative
- low-confidence club
- missing shot data
- missing putt data
- missing geometry
- weak sample size

Issues can be deterministic, AI-suggested, or manually tagged. The UI must show
the source and confidence.

## Manual Annotation And Correction

Manual input is required because Garmin data is incomplete and because player
intent is often invisible.

Required manual surfaces:

- round note
- hole note
- shot note
- issue tag add/remove
- club correction
- lie correction
- penalty correction
- putt correction
- weather/context note
- intended target or strategy note
- caddie feedback after the shot

Manual corrections must preserve audit history. They should not overwrite raw
source records.

## AI Review Rules

AI is explanation and synthesis, not the source of truth.

Allowed AI work:

- summarize a round from structured facts
- explain likely scoring loss from known evidence
- compare current trends to prior periods
- propose practice or course-management focus
- analyze photo/video context when explicitly provided
- generate natural-language caddie explanation from deterministic decision data

Disallowed AI behavior:

- invent weather, lie, intent, club, or penalties
- change verified numeric facts
- hide low confidence
- produce generic advice with no cited evidence
- use raw Garmin tokens, cookies, or private source files

Every AI output should expose:

- facts used
- inferences made
- confidence
- missing data
- links/drill-down to source records

## Caddie Decision Engine

The caddie engine combines deterministic models and AI explanation.

Inputs:

- current location
- hole geometry
- pin/green/target data where available
- hazards and playable bounds
- weather and wind when available
- lie and stance context when available
- personal club model
- current score/strategy mode
- historical hole/course patterns
- player confidence and manual notes
- provided photo/video context when available

Outputs:

- recommended plan
- safe/stock/attack alternatives
- club sequence possibilities
- target line or landing window
- carry/clear distances
- avoid zones
- expected scoring impact
- confidence
- missing info
- post-shot audit criteria

Garmin-style sequences such as `1D-3W-58` or `3W-5i-54` should be supported,
but AI Caddie should go deeper by accounting for dispersion, hazards, lie,
weather, confidence, historical outcome, and recoverability.

## Offline-First Live Round Model

Before a round:

- sync selected course package
- sync geometry package
- sync club profile
- sync recent course/hole history
- cache weather forecast when available
- cache caddie rules and UI assets

During a round:

- GPS and local state continue without network
- score, putts, penalties, club choice, and notes are local-first
- iOS and Apple Watch can continue even if the phone/network relationship
  changes, within platform limits
- AI/vision features degrade if no network/model is available

After a round:

- sync local event log
- reconcile with Garmin data when available
- show differences and allow corrections
- update club profiles, issue trends, and decision audit

## Testing And Autonomous Execution Rules

The implementation plan must be executable without routine user input.

Required test layers:

- connector contract tests with fixtures
- Garmin raw adapter tests
- normalized data snapshot tests
- history aggregate tests
- statistics drill-down tests
- issue taxonomy tests
- geometry classification tests
- weather missing/degraded tests
- AI provider selection and secret-redaction tests
- AI review deterministic fake-provider tests
- API contract tests
- frontend component tests
- visual smoke tests for major screens
- offline event-log tests
- sync/reconciliation tests

Execution rules:

- Each implementation increment defines done criteria and automated verification.
- Missing external keys must use fake providers or fixtures unless the increment
  explicitly tests a live provider.
- Empty remote data is not an acceptable final test state for history UI.
- The system must include synthetic and sanitized sample data for tests.
- Private Garmin data can be used locally for manual validation but is not
  required for automated CI.
- If a connector is expired, tests should validate `reauth_required`, not fail
  unrelated history or UI behavior.

## Execution Increment Tree

Increment names describe build order only. They do not remove final scope.

### 1. Foundation And Fixtures

Build stable project boundaries, config, test fixtures, and sample data so all
later work can be tested without live Garmin credentials.

Done when:

- normalized fixture dataset exists
- connector status can report no data, ready, expired, and error states
- tests can run without private secrets
- backend/frontend can render useful sample history

### 2. Connector And Snapshot Layer

Implement CN Web Session connector around the existing validated Garmin fetch
logic, with reauth status and versioned snapshots.

Done when:

- scorecard summary/detail/shots sync through a connector interface
- expired cookie returns `reauth_required`
- raw snapshots are versioned
- normalized records are independent of login state
- Web shows sync status without exposing secrets

### 3. History Statistics Core

Build complete history aggregation by time, round, course, hole, club, issue,
and data quality.

Done when:

- all required historical aggregates have tests
- every aggregate exposes drill-down references
- data quality is attached to affected stats
- sample and private data both work

### 4. Web History Product

Build the Garmin Pro Web review experience over the stable history API.

Done when:

- overview, timeline, rounds, courses, holes, clubs, issues, and data quality
  screens exist
- charts and cards use unified visual semantics
- empty, loading, degraded, and populated states are tested
- major charts drill down to records

### 5. AI Provider And Fact-Bound Review

Introduce provider abstraction and generate deterministic/fact-bound reviews.

Done when:

- static test provider exists
- Anthropic/NIM/Gemini provider paths are selectable by config
- AI outputs cite facts and missing data
- provider errors redact secrets
- round and trend reviews are stored and drill-down capable

### 6. Geometry And Course Evidence

Productionize prodgeometry sync and geometry-derived analysis.

Done when:

- geometry coverage is tracked by course/hole
- shot-to-surface and shot-to-hazard classification is tested
- course/hole review can show route and hazard evidence
- missing geometry degrades confidence cleanly

### 7. Caddie Decision Layer

Expand deterministic caddie decisions beyond the prototype.

Done when:

- tee, approach, and recovery decision contracts exist
- safe/stock/attack alternatives are generated
- club model, geometry, hazards, and weather/context feed decisions
- decisions can be audited after actual shot outcomes

### 8. Manual Correction And Annotation

Add the audit-safe user correction loop.

Done when:

- notes, tags, and corrections exist for round/hole/shot
- corrections preserve raw source
- issue and club models can use manual corrections
- UI exposes correction history clearly

### 9. iOS Live App

Build iOS as the live capture and mobile caddie surface.

Done when:

- round package can be prepared offline
- GPS, score, club, putt, penalty, note, photo/video capture exist
- sync status is clear
- live state survives network loss
- CN connector product path can be hosted on iOS if selected

### 10. Apple Watch Companion

Build Watch as fast live input and decision glance.

Done when:

- current hole and distance context display
- quick club/score/putt/penalty input works
- data syncs through iPhone
- offline/live constraints are explicit and tested

### 11. Photo And Video Context

Add vision-assisted context analysis.

Done when:

- photos/videos attach to shot/hole context
- AI can label visible obstacles, lie clues, blocked view, and uncertainties
- vision findings are evidence with confidence, not automatic truth
- privacy and storage controls exist

### 12. Private Trial Hardening

Prepare the product for personal daily use and limited friends trial.

Done when:

- cloud staging deployment is documented
- secret handling and private data boundaries are tested
- import/export and backup exist
- onboarding and reauth flows are understandable
- observability and error states are sufficient for unattended operation

## Open Decisions Already Resolved

- Backend Python is acceptable and preferred for the engine because existing
  normalization, geometry, and statistics work is in Python.
- Frontend Web remains React/Vite/TypeScript unless a future plan proves a
  better alternative.
- Node version should be chosen for the toolchain and deployment target, not
  arbitrarily for Vite alone.
- Garmin CN Web Session Connector is the first real connector.
- Official OAuth is a feasibility track, not the first dependency.
- Mac local sync agent is not the preferred path.
- Garmin watch app is excluded.
- Friends/group/social stats are excluded.
- Practice range/simulator is excluded from this build.
- AI uses deterministic facts plus provider-based explanation.

## Spec Acceptance Criteria

This spec is accepted when:

- it captures the complete product target, not only a first slice
- no required capability is mislabeled as optional
- connector design avoids hard-coding cookie logic into history/UI
- history/statistics are treated as first-class and comprehensive
- caddie decisioning remains architecturally supported
- offline iOS/Watch direction is included
- testing and autonomous execution requirements are explicit
- future OAuth, map, weather, and AI provider swaps have clear boundaries
