# AI Caddie Master Plan Tree

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement each detailed plan task-by-task. Steps in detailed plans use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the master product spec into dependency-ordered, testable implementation plans without dropping any required capability.

**Architecture:** The work is split by dependency boundaries. Data fixtures and connector contracts come first, then history statistics, Web product, AI provider/review, geometry, caddie decisions, manual corrections, mobile/watch, vision, and private trial hardening.

**Tech Stack:** Python 3.12, FastAPI, pytest/unittest, React, Vite, TypeScript, Vitest, Garmin CN Web Session connector, Garmin prodgeometry, provider-based AI layer.

---

## Source Spec

`docs/superpowers/specs/2026-05-25-ai-caddie-master-product-spec.md`

## Planning Rules

- Every required capability remains inside the final build.
- The order below is dependency order, not product ambition order.
- Each detailed plan must be executable without routine user input.
- Each detailed plan must include automated verification and clear commit points.
- External secrets must not be required for automated tests.
- Private Garmin data can validate manually, but synthetic/sanitized fixtures must drive tests.
- If Garmin auth is expired, connector tests validate `reauth_required`; unrelated history/UI tests must still pass.

## Dependency Tree

### 1. Foundation And Fixtures

Detailed plan: `docs/superpowers/plans/2026-05-25-foundation-and-fixtures.md`

Purpose:

- Establish fixture data, config, connector status semantics, and test helpers.
- Make backend/frontend useful when private Garmin data is absent.
- Provide the stable base for downstream plans.

Depends on:

- Current repo only.

Unblocks:

- Connector implementation
- History statistics core
- Web screens
- AI fake provider tests

Completion standard:

- Backend tests and frontend tests can run with synthetic data and no Garmin secrets.
- UI/API can render populated history from fixtures instead of only empty states.

### 2. Connector And Snapshot Layer

Detailed plan: `docs/superpowers/plans/2026-05-25-connector-and-snapshot-layer.md`

Purpose:

- Wrap existing Garmin CN fetch/auth into a connector interface.
- Store versioned raw snapshots and normalized import results.
- Represent `ready`, `expired`, `reauth_required`, `no_data`, and `error` states.

Depends on:

- Plan 1 fixture/status types.

Unblocks:

- Real private-data sync
- Geometry profile id discovery
- Data quality coverage

Completion standard:

- Expired cookie returns a typed reauth state.
- Successful sync produces raw snapshot metadata and normalized records.
- No cookie/token is printed or returned through API responses.

### 3. History Statistics Core

Detailed plan: `docs/superpowers/plans/2026-05-25-history-statistics-core.md`

Purpose:

- Build the complete aggregation engine for time, round, course, hole, club,
  issue, and data quality.

Depends on:

- Plan 1 fixtures
- Plan 2 normalized snapshot contracts

Unblocks:

- Web history product
- AI trend review
- Course/hole diagnosis

Completion standard:

- Every aggregate has tests and drill-down references.
- 18-hole/9-hole handling, merged same-day rounds, recent trends, score
  distribution, course/hole/club stats, and coverage metrics are available.

### 4. Web History Product

Detailed plan: `docs/superpowers/plans/2026-05-25-web-history-product.md`

Purpose:

- Build the Garmin Pro review experience: overview, timeline, rounds, courses,
  holes, clubs, issues, and data quality.

Depends on:

- Plan 3 history APIs

Unblocks:

- Daily personal review
- Manual correction surfaces
- AI report surfaces

Completion standard:

- Populated, empty, loading, and degraded states are tested.
- Major charts/cards drill down to source records.
- Visual semantics are unified.

### 5. AI Provider And Fact-Bound Review

Detailed plan: `docs/superpowers/plans/2026-05-25-ai-provider-and-fact-bound-review.md`

Purpose:

- Replace Anthropic-only coupling with provider abstraction.
- Integrate static, Anthropic, NVIDIA NIM, and Gemini-compatible paths.
- Generate fact-bound round and trend reviews.

Depends on:

- Plan 1 config/test fixture base
- Plan 3 structured facts

Unblocks:

- AI reviews
- Vision provider path
- Caddie natural-language explanation

Completion standard:

- Provider selection and secret redaction are tested.
- AI review uses structured facts and stores evidence/confidence/missing data.

### 6. Geometry And Course Evidence

Detailed plan: `docs/superpowers/plans/2026-05-25-geometry-and-course-evidence.md`

Purpose:

- Productionize prodgeometry coverage, shot-to-surface classification, hazard
  evidence, and map DTOs.

Depends on:

- Plan 2 connector/snapshot metadata
- Plan 3 course/hole stats

Unblocks:

- Hole review route evidence
- Caddie decisions

Completion standard:

- Geometry coverage is tracked.
- Missing geometry degrades confidence.
- Course/hole pages can show hazard/route evidence.

### 7. Caddie Decision Layer

Detailed plan: `docs/superpowers/plans/2026-05-25-caddie-decision-layer-complete.md`

Purpose:

- Expand deterministic decisions for tee, approach, and recovery.
- Add audit loop against actual outcomes.

Depends on:

- Plan 3 club/history stats
- Plan 6 geometry evidence
- Weather context from fixture/degraded layer

Unblocks:

- Live iOS caddie
- Watch decision glance

Completion standard:

- Safe/stock/attack options, selected plan, confidence, evidence, avoid zones,
  and audit criteria exist and are tested.

### 8. Manual Correction And Annotation

Detailed plan: `docs/superpowers/plans/2026-05-25-manual-correction-and-annotation.md`

Purpose:

- Add notes, corrections, issue tags, and caddie feedback with audit history.

Depends on:

- Plan 3 normalized facts
- Plan 4 Web drill-down surfaces

Unblocks:

- Better issue taxonomy
- Club/round correction
- Live input reconciliation

Completion standard:

- Raw facts remain immutable.
- Corrections are auditable and affect derived stats through explicit rules.

### 9. iOS Live App

Detailed plan: `docs/superpowers/plans/2026-05-25-ios-live-app.md`

Purpose:

- Build live round capture, offline package preparation, GPS, score/club input,
  photo/video capture, and sync status.

Depends on:

- Plan 2 connector contracts
- Plan 7 caddie decision contracts
- Plan 8 correction/event model

Unblocks:

- On-course use
- Apple Watch companion

Completion standard:

- A round can start with cached data, continue through network loss, and sync
  an event log afterward.

### 10. Apple Watch Companion

Detailed plan: `docs/superpowers/plans/2026-05-25-apple-watch-companion.md`

Purpose:

- Build current-hole glance, club suggestion, score/putt/penalty/club input, and
  iPhone sync.

Depends on:

- Plan 9 iOS live model

Unblocks:

- Garmin-watch-like live input replacement path

Completion standard:

- Watch input syncs through iPhone and handles offline/live constraints.

### 11. Photo And Video Context

Detailed plan: `docs/superpowers/plans/2026-05-25-photo-video-context.md`

Purpose:

- Add evidence-bound vision analysis for lie, obstacle, blocked view, and
  uncertainty.

Depends on:

- Plan 5 AI provider abstraction
- Plan 9 iOS capture

Unblocks:

- Future glasses/camera path
- Richer live caddie context

Completion standard:

- Vision findings attach to shot/hole context with confidence and are never
  treated as automatic truth.

### 12. Private Trial Hardening

Detailed plan: `docs/superpowers/plans/2026-05-25-private-trial-hardening.md`

Purpose:

- Prepare personal daily use and limited friends trial.

Depends on:

- Plans 1-11 as implemented product slices

Unblocks:

- Private release
- Public release readiness evaluation

Completion standard:

- Cloud staging, backups, import/export, secret handling, observability,
  onboarding, and reauth flows are sufficient for unattended use.

## Current Execution Status

- Plan 1 Foundation And Fixtures is implemented through commit `1588a7d`.
- Plan 2 Connector And Snapshot Layer is implemented through commit `493f1da`.
- Plan 3 History Statistics Core is implemented through commit `edba619`.
- Plan 4 Web History Product is the next execution target.

Plan 4 is next because fixture-backed data, connector status, and the backend
statistics contract now exist. The UI can be tested against non-empty fixture
data while real Garmin sync remains independent of the history review surface.
