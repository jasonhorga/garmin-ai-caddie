# Web History Product Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the Web v2 UI into a complete Garmin Pro history product over the existing overview, rounds, sync, and stats APIs.

**Architecture:** Keep `web_v2` as React/Vite/TypeScript. Add page-level components that consume existing API contracts first; do not invent frontend-only statistics. Use `HistoryStatsResponse` as the source for new course, hole, club, issue, and data quality screens.

**Tech Stack:** React, TypeScript, Vite, Vitest, Testing Library, CSS tokens.

---

## Files

Create:

- `web_v2/src/components/StatsOverview.tsx`
- `web_v2/src/components/StatsOverview.test.tsx`
- `web_v2/src/components/CourseStats.tsx`
- `web_v2/src/components/CourseStats.test.tsx`
- `web_v2/src/components/HoleStats.tsx`
- `web_v2/src/components/HoleStats.test.tsx`
- `web_v2/src/components/ClubStats.tsx`
- `web_v2/src/components/ClubStats.test.tsx`
- `web_v2/src/components/IssueStats.tsx`
- `web_v2/src/components/IssueStats.test.tsx`
- `web_v2/src/components/DataQualityPage.tsx`
- `web_v2/src/components/DataQualityPage.test.tsx`

Modify:

- `web_v2/src/types.ts`
- `web_v2/src/api.ts`
- `web_v2/src/api.test.ts`
- `web_v2/src/components/ProductNav.tsx`
- `web_v2/src/App.tsx`
- `web_v2/src/App.test.tsx`
- `web_v2/src/styles.css`

## Task 1: Add History Stats Frontend API

- [ ] Add `HistoryStatsResponse` and nested dictionary-friendly types to `web_v2/src/types.ts`.

Use this minimum type:

```typescript
export interface HistoryStatsResponse {
  schema: 'ai-caddie-history-stats-v1'
  dataMode: 'local' | 'fixture'
  summary: Record<string, unknown>
  time: Record<string, unknown>
  scoring: Record<string, unknown>
  courses: Array<Record<string, unknown>>
  holes: Array<Record<string, unknown>>
  clubs: Array<Record<string, unknown>>
  issues: Array<Record<string, unknown>>
  dataQuality: Array<Record<string, unknown>>
  drillDown: Record<string, unknown>
}
```

- [ ] Add failing test in `web_v2/src/api.test.ts` asserting `fetchHistoryStats()` calls `/api/v2/history/stats`.
- [ ] Implement `fetchHistoryStats()` in `web_v2/src/api.ts`.
- [ ] Run:

```bash
npx -y -p node@24 -c 'cd web_v2 && npm test -- --run src/api.test.ts'
```

- [ ] Commit:

```bash
git add web_v2/src/types.ts web_v2/src/api.ts web_v2/src/api.test.ts
git commit -m "feat: add history stats frontend API"
```

## Task 2: Add Stats Overview

- [ ] Create `StatsOverview.test.tsx` with a fixture payload containing `summary.totalRounds`, `summary.average18`, `summary.bestScore`, `time.byMonth`, and `scoring.scoreBands`.
- [ ] Create `StatsOverview.tsx` that renders:
  - total rounds
  - 18-hole average
  - best score
  - data mode
  - score bands
  - latest months
- [ ] Ensure no text overflows on narrow width by using compact labels and CSS grid.
- [ ] Run:

```bash
npx -y -p node@24 -c 'cd web_v2 && npm test -- --run src/components/StatsOverview.test.tsx'
```

- [ ] Commit:

```bash
git add web_v2/src/components/StatsOverview.tsx web_v2/src/components/StatsOverview.test.tsx web_v2/src/styles.css
git commit -m "feat: add stats overview panel"
```

## Task 3: Add Course, Hole, Club, Issue, Data Quality Pages

- [ ] Create one test per component listed in the Files section.
- [ ] Each component receives `HistoryStatsResponse` and renders only its own slice:
  - `CourseStats`: course name, rounds, average, best/worst, round refs.
  - `HoleStats`: course key, hole number, samples, average-to-par, worst-to-par, refs.
  - `ClubStats`: club, samples, median, p10, p90, max, confidence.
  - `IssueStats`: issue name, count, refs.
  - `DataQualityPage`: label, state, ready/total, refs.
- [ ] Use compact table/list hybrids, not nested cards.
- [ ] Run all component tests:

```bash
npx -y -p node@24 -c 'cd web_v2 && npm test -- --run src/components/CourseStats.test.tsx src/components/HoleStats.test.tsx src/components/ClubStats.test.tsx src/components/IssueStats.test.tsx src/components/DataQualityPage.test.tsx'
```

- [ ] Commit:

```bash
git add web_v2/src/components/CourseStats.tsx web_v2/src/components/CourseStats.test.tsx web_v2/src/components/HoleStats.tsx web_v2/src/components/HoleStats.test.tsx web_v2/src/components/ClubStats.tsx web_v2/src/components/ClubStats.test.tsx web_v2/src/components/IssueStats.tsx web_v2/src/components/IssueStats.test.tsx web_v2/src/components/DataQualityPage.tsx web_v2/src/components/DataQualityPage.test.tsx web_v2/src/styles.css
git commit -m "feat: add history statistics pages"
```

## Task 4: Wire Navigation And App State

- [ ] Extend `ProductPage` in `ProductNav.tsx` to include:
  - `stats`
  - `courses`
  - `holes`
  - `clubs`
  - `issues`
  - `quality`
- [ ] Update nav labels to match the master spec.
- [ ] In `App.tsx`, add a deferred `HistoryStatsResponse` load state.
- [ ] Fetch stats when any stats-backed page is first opened.
- [ ] Render loading/error states for stats-backed pages.
- [ ] Update `App.test.tsx` to navigate to at least `Clubs` and `Issues` and assert fixture rows render.
- [ ] Run:

```bash
npx -y -p node@24 -c 'cd web_v2 && npm test -- --run src/App.test.tsx'
```

- [ ] Commit:

```bash
git add web_v2/src/App.tsx web_v2/src/App.test.tsx web_v2/src/components/ProductNav.tsx web_v2/src/styles.css
git commit -m "feat: wire history stats navigation"
```

## Task 5: Verification

- [ ] Run all frontend tests:

```bash
npx -y -p node@24 -c 'cd web_v2 && npm test -- --run'
```

- [ ] Run lint and build:

```bash
npx -y -p node@24 -c 'cd web_v2 && npm run lint && npm run build'
```

- [ ] With API on 9000 and Vite on 5173, manually open:

```text
http://127.0.0.1:5173
```

- [ ] Confirm the app can navigate to overview, timeline, stats, courses, holes, clubs, issues, and data quality using fixture data.
