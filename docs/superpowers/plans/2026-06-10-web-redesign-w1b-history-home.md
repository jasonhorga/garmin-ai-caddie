# Web Redesign W1b — 历史·趋势总览 + 概览落地页 + 范围参数 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **中文摘要:** W1a 给了外壳;W1b 给内容。后端:`/api/v2/history/stats` 增加 `window=all|12m|last10` 窗口参数(缓存按窗口分键)+ 差点估算/月度差点字段。前端:全新「历史·趋势总览」(范围切换驱动整页、4 KPI、走势图、成绩构成、最近球局)、全新「概览」落地页(想备哪场?搜索+常打球场 / 上一场 / 近期状态 / 本周该练)、强弱分析三页合一、比分 token 换 mockup 色值。旧 StatsOverview/HistoryOverview 退役。

**Goal:** Implement spec §5.1 (概览) and §5.2·趋势总览/强弱分析 plus backend capability §8.1, on top of the W1a shell.

**Architecture:** Backend windows the round set BEFORE `build_history_stats` (new pure helper), cache key gains the window. Frontend keeps the existing app-wide `statsState` (window=all) for 球场/报告/数据质量 consumers, and adds an independent `trendsState` keyed by the selected window for the 趋势总览 page. 概览 composes data already loaded at boot (overview) + all-stats + mobile course options (for globalIds) + course search.

**Tech stack:** unchanged (FastAPI + unittest; React 19 + vitest + Playwright; inline SVG charts).

**Branch / worktree:** `superpowers/web-redesign-w1b` off `integration/v2` (= d052d0f, post-PR#17), via EnterWorktree (NOTE: EnterWorktree bases on origin/HEAD — verify base == origin/integration/v2 tip, else `git reset --hard origin/integration/v2`). Node 24: `export PATH="$HOME/node24/bin:$PATH"` before every npm/npx. Backend tests: `uv run python -m unittest <targets>` from the worktree root (CI uses `unittest discover -s tests`; no data/ symlink in worktrees — that matches CI).

**Locked design decisions (from the user's /goal + spec):**
- Score tokens take the mockup values: `--bogey: #d9a441`, `--double: #c2553f` (+ `-text` variants where contrast requires, mirroring the `--green-text` pattern).
- 趋势总览 default window = `last10`(mockup 状态);switch options exactly 全部/近12个月/近10场 (D3).
- KPI row exactly: 均杆(18洞) · 差点(估算) · 得分区间 · 帕或更好率 (D2), with vs-全部 deltas when window ≠ all.
- All new page content Chinese-first.

---

## Part A — Backend

### Task A1: window filtering helper + windowed cache

**Files:**
- Modify: `ai_caddie/history_stats.py` (add `windowed_history_data`; extend `_summary` + `_time_stats` per A2 — keep A1 scoped to the helper)
- Modify: `ai_caddie/stats_cache.py` (`cached_build_history_stats` gains `window: str = "all"`; key gains window)
- Modify: `server_v2/history_stats.py` (`load_history_stats_response(window: str = "all")` passes through)
- Modify: `server_v2/main.py` route: `def history_stats(window: str = Query("all", pattern="^(all|12m|last10)$"))`
- Tests: `tests/test_history_stats_window.py` (new), extend `tests/test_stats_cache.py`, extend `tests/test_server_v2_history_stats.py`

**Behavior contract (TDD these exactly):**
1. `windowed_history_data(data, window)` is pure; returns HistoryData with:
   - `all` → same object (identity, zero cost).
   - `last10` → the 10 most recent rounds by `date` (string ISO sort desc; merged rounds count as one); `shots` filtered to surviving round ids (match shot `roundId`/`scorecardId` against round `id`); `raw_rounds` filtered the same way.
   - `12m` → rounds with `date >= anchor - 365 days`, where anchor = max round date in the data (NOT wall clock — determinism). Same shots/raw filtering.
   - Invalid window → `ValueError`.
2. `cached_build_history_stats(..., window="all")`: key = `(data_mode, roots..., window)`; fingerprint still computed on the FULL data; value = `build_history_stats(windowed_history_data(data, window), ...)`. Two windows cached simultaneously; switching windows does NOT evict each other (assert both hit on second call).
3. Route: `GET /api/v2/history/stats?window=last10` → 200 with stats computed over ≤10 rounds (fixture has 3 → same as all); `window=bogus` → 422.
4. All existing callers (`ai_review.py`, `caddie_context.py`, `mobile_live.py`, `server_v2/history_stats.py`) keep working unchanged (default `all`).

**Test names:** `WindowedHistoryDataTests.test_all_returns_identity / test_last10_keeps_newest_rounds_and_their_shots / test_12m_anchors_on_newest_round / test_invalid_window_raises`; `StatsCacheTests.test_window_variants_cached_independently`; `ServerV2HistoryStatsTests.test_history_stats_window_param_validates_and_filters`.

- [ ] Write failing tests → run `uv run python -m unittest tests.test_history_stats_window -v` → implement → green
- [ ] `uv run python -m unittest tests.test_stats_cache tests.test_server_v2_history_stats -v` green
- [ ] Commit: `feat(api): history-stats window param (all|12m|last10) with per-window caching`

### Task A2: handicap estimate + monthly differential

**Files:**
- Modify: `ai_caddie/history_stats.py` — `_summary` gains `handicapEstimate` + `handicapTrend`; `_time_stats` byMonth rows gain `averageDifferential`
- Test: extend `tests/test_history_stats_window.py` (or `tests/test_history_stats_core.py` following its style)

**Formulas (deterministic; UI labels them 估算):**
- Differential per scored 18-hole-equivalent round: reuse the module's existing differential computation (summary already exposes `averageDifferential` — locate its per-round source and reuse; if rating/slope present it already adjusts).
- `handicapEstimate`: take the most recent `min(20, N)` rounds; if `N < 5` → `null`; else take the lowest `ceil(0.4 × min(20,N))` differentials, average, × 0.96, round to 1 decimal.
- `handicapTrend`: `handicapEstimate(now) − handicapEstimate(rounds with date ≤ anchor − 90 days)`; `null` if the older set has `< 5` rounds. Negative = improving.
- `byMonth[].averageDifferential`: mean differential of that month's rounds, 1 decimal, `null` if none have differentials.

**Test names:** `HandicapEstimateTests.test_estimate_uses_best_40pct_of_last_20 / test_estimate_null_under_5_rounds / test_trend_compares_90_day_anchor`; `TimeStatsTests.test_by_month_includes_average_differential`.

- [ ] TDD as above; full backend suite: `uv run python -m unittest discover -s tests 2>&1 | tail -3` → OK
- [ ] Commit: `feat(api): handicap estimate (估算) + monthly differential in history stats`

---

## Part B — Frontend data layer

### Task B1: api + types

**Files:**
- Modify: `web_v2/src/api.ts` — `fetchHistoryStats(adminToken?: string, window: StatsWindow = 'all')` appends `?window=` when ≠ all (mirror fetchHistoryRounds param style); NEW `fetchCourseSearch(name: string, adminToken?: string): Promise<CourseSearchResponse>` → `GET /api/v2/courses/search?name=<encoded>`
- Modify: `web_v2/src/types.ts` — `export type StatsWindow = 'all' | '12m' | 'last10'`; `CourseSearchResponse { schema: 'ai-caddie-course-search-v1'; query: string; matches: Array<{ globalId: number; name: string; holes: number | null; city: string | null; province: string | null; ratio: number }> }`
- Tests: extend `web_v2/src/api.test.ts` (follow its existing fetch-mock style): window param appended/omitted; course search URL-encodes CJK.

- [ ] TDD → `npx vitest run src/api.test.ts` green → Commit: `feat(web): stats window + course-search API clients`

---

## Part C — Frontend pages

### Task C1: 趋势总览 (TrendsOverview) replaces StatsOverview on the `history` page

**Files:**
- Create: `web_v2/src/components/TrendsOverview.tsx` + `TrendsOverview.test.tsx`
- Modify: `web_v2/src/App.tsx` — new state `trendsWindow: StatsWindow` (init `'last10'`), `trendsState: DeferredLoadState<HistoryStatsResponse>`; `navigate('history')` lazy-loads trends (and statsState stays lazy-loaded for the other pages, used for deltas); `renderStatsContent` history branch renders TrendsOverview
- Delete: `web_v2/src/components/StatsOverview.tsx` + `StatsOverview.test.tsx` (grep first: if other components import pieces, report BLOCKED instead of deleting)
- Modify: `web_v2/src/App.test.tsx`, `web_v2/e2e/history-visual.smoke.spec.ts` — anchors change (below)

**Component contract (props):**
```tsx
interface TrendsOverviewProps {
  stats: HistoryStatsResponse            // windowed
  allStats: HistoryStatsResponse | null  // for vs-全部 deltas; null → hide deltas
  window: StatsWindow
  onWindowChange: (w: StatsWindow) => void
  recentRounds: RoundCardType[]          // from overviewState (already loaded at boot)
  onOpenRoundDetail?: (roundRef: string) => void
}
```
**Renders (mockup `history-overview-v2.html`):**
1. Range row: 范围 + segmented 全部/近12个月/近10场 (`aria-pressed` or `aria-current` on active; clicking calls onWindowChange).
2. KPI row (4 cards, tabular numerals): 均杆(18洞)=summary.average18; 差点(估算)=summary.handicapEstimate + trend arrow from handicapTrend (▼ improving green / ▲ red); 得分区间=`${bestScore}–${worstScore}`; 帕或更好率 = outcomes.parOrBetter / (eagleOrBetter+birdie+par+bogey+doubleOrWorse) as %. When window≠all and allStats present, each card shows `vs 全部 ±Δ`.
3. 成绩走势 panel: inline SVG line; window==='last10' → one point per round from `recentRounds.slice(0,10)` reversed (oldest→newest); else monthly from `stats.time.byMonth` (key + average18). Toggle 杆数/差点: 杆数 uses score/average18 series; 差点 uses round.toPar (last10) or byMonth.averageDifferential. Toggle is two buttons with aria-pressed.
4. 成绩构成 panel: five bars 老鹰/小鸟/帕/柏忌/双+ as % of total outcome holes, colored par-family/green/--bogey/--double; below a one-line callout `最吃杆:<top issue zh label>` from `stats.issues[0]` via the label map (new `web_v2/src/issueLabels.ts`: `{ approach_short: '攻果岭偏短', tee_right: '开球偏右', tee_left: '开球偏左', three_putt: '三推', short_game: '短杆', penalty: '罚杆' }` + fallback = raw token; export `issueLabel(token: string): string`).
5. 最近球局 panel: up to 10 rows (date MM-DD, courseName, score, ±toPar chip with par/over/bigover classes) clicking row → onOpenRoundDetail(round.id).

**Test cases (component):** window buttons call onWindowChange; KPI values render from a synthetic stats object incl. handicapEstimate null → shows '—'; deltas hidden when allStats null; outcomes percentage math; issue callout uses zh label + falls back to token; row click fires onOpenRoundDetail.

**App.test.tsx anchor migration:** 'Statistics Overview' (3 hits ~1117/1335/1574) → after clicking 历史 expect `findByText('成绩走势')` (and keep the stats fetch assertion — note it now fires with `?window=last10`, update `toHaveBeenCalledWith('/api/v2/history/stats?window=last10')`; the OTHER stats consumers still call plain `/api/v2/history/stats`). e2e: `['趋势总览', 'Statistics Overview']` row → assert `page.getByText('成绩走势')` instead of the heading.

- [ ] TDD component → wire App → migrate tests → `npx vitest run` green → Commit: `feat(web): 趋势总览 — windowed KPIs, trend chart, 成绩构成, 最近球局`

### Task C2: 强弱分析 merged page

**Files:**
- Modify: `web_v2/src/components/HoleStats.tsx`, `ClubStats.tsx`, `IssueStats.tsx` — h1 → h2 (keep heading TEXT unchanged: 'Hole Stats' etc.; `getByRole('heading', {name})` is level-agnostic so their own tests keep passing)
- Modify: `web_v2/src/App.tsx` — renderStatsContent: holes|clubs|issues → render all three stacked (`<><HoleStats …/><ClubStats …/><IssueStats …/></>`), REMOVE the inner `<SubNav items={ANALYSIS_TABS} …/>`
- Modify: `web_v2/src/navigation.ts` — delete `ANALYSIS_TABS` export (grep zero refs after App change); keep 'clubs'/'issues' in ProductPage (other code may navigate; they now render the same merged page)
- Modify: `web_v2/src/App.test.tsx` — pills gone: tests that clicked 按杆/问题 now assert all three headings visible after clicking 强弱分析; e2e: drop the two pill clicks, after 强弱分析 assert 'Hole Stats' AND 'Club Stats' AND 'Issue Stats' all visible
- Modify: `web_v2/src/navigation.test.ts` — drop the ANALYSIS_TABS assertions

- [ ] Implement → migrate tests → vitest + lint green → Commit: `feat(web): 强弱分析 merges holes/clubs/issues into one stacked page`

### Task C3: 概览 (HomeOverview) replaces HistoryOverview

**Files:**
- Create: `web_v2/src/components/HomeOverview.tsx` + `HomeOverview.test.tsx`
- Modify: `web_v2/src/App.tsx` — overview branch renders HomeOverview; new state `prepGlobalId: number | null`; handler `handlePrepCourse(globalId)` = set state + `navigate('prep')`; prep branch becomes `<CoursePrepPanel key={prepGlobalId ?? 'default'} defaultGlobalId={prepGlobalId ?? undefined} />`; `navigate('overview')` lazy-loads statsState (for 近期状态/本周该练) and mobileCourseOptionsState (for frequent-course globalIds) if idle
- Delete: `web_v2/src/components/HistoryOverview.tsx` + test. Grep `DistributionPanel`/`DataQualityChips` usages — if HistoryOverview was their only consumer, delete them + tests too (RoundCard/ScoreStrip stay: HistoryTimeline uses them — verify by grep, report if not)
- Modify: `web_v2/src/App.test.tsx` (~20 'History Overview' hits) + e2e line ~439

**Component contract:**
```tsx
interface HomeOverviewProps {
  overview: HistoryOverviewResponse
  stats: HistoryStatsResponse | null            // all-window; null → 近期状态 shows loading dashes
  courseOptions: MobileCourseOptionsResponse | null
  onSearchCourses: (name: string) => Promise<CourseSearchResponse>  // App wraps fetchCourseSearch with currentAdminToken
  onPrepCourse: (globalId: number) => void
  onOpenRoundDetail?: (roundRef: string) => void
  onNavigateAnalysis: () => void                // → navigate('holes')
}
```
**Renders (mockup `home-page-v2.html`):**
1. Greeting `你好 👋` + sub 你的近况一眼看完.
2. 备战入口卡 (primary): heading 想备哪场?; search `<input aria-label="搜索球场">` — submit (Enter or 搜索 button) → onSearchCourses → result list (name · city · holes, click → onPrepCourse(globalId)); empty result → 没有找到球场; 3 frequent-course cards from `courseOptions.courses` sorted roundCount desc top 3 (name, `打过 N 次`, 去备战 → onPrepCourse(globalId)).
3. 上一场卡: overview.recentRounds[0] — score big, toPar chip, courseName, date (YYYY-MM-DD→MM-DD), `看复盘 →` → onOpenRoundDetail(id); none → 还没有球局.
4. 近期状态卡: 差点(估算) stats.summary.handicapEstimate + handicapTrend arrow; 均杆 summary.recent10Average; sparkline from overview.recentRounds.slice(0,10) scores reversed; `看历史 →` … link via onNavigateAnalysis? NO — 看历史 navigates to history: add `onNavigateHistory: () => void` prop (→ navigate('history')).
5. 本周该练 banner: `🎯 本周该练:` + top issue zh label from stats.issues[0] (issueLabel) + 看强弱分析 → onNavigateAnalysis. Hidden when stats null/empty issues.

**Test cases:** frequent courses sorted+capped at 3 and click fires onPrepCourse with globalId; search submit calls onSearchCourses and renders matches; selecting match fires onPrepCourse; 上一场 renders first recentRound + detail click; banner uses zh label; stats=null renders without crash.

**App.test.tsx migration:** 'History Overview' text anchors → `findByText('想备哪场?')`; the master IA test's initial assertion likewise; mocks: overview tests now ALSO hit `/api/v2/history/stats` + `/api/v2/mobile/courses/options` on landing — extend the per-path mocks (statsPayload/mobileCourseOptionsPayload helpers already exist in the file). e2e: heading anchor → `page.getByText('想备哪场?')`; mockApi already stubs mobile course options + stats ✓; add `/api/v2/courses/search` stub returning one match and (optional) skip exercising search in e2e.

- [ ] TDD → wire → migrate tests → vitest/lint/e2e green → Commit: `feat(web): 概览落地页 — 备战入口(搜索+常打)、上一场、近期状态、本周该练`

### Task C4: score-token colors → mockup values

**Files:**
- Modify: `web_v2/src/styles.css` — `:root`: `--bogey: #d9a441`, `--double: #c2553f`; add `--bogey-text: #9a6a16`, `--double-text: #a23f2c`
- Then audit EVERY `color: var(--bogey)`/`color: var(--double)` usage (recon found ~16: lines ~649, 654, 812, 903, 1295, 1450, 1558, 1965, 1970, 2892, 2982, 3030, 3238, 3737): for each, if it is normal-size text on a light/tinted background (e.g. `#f7e2dd`, white), switch to the `-text` variant; backgrounds/fills/borders keep the new brighter values (`.score-bogey`/`.score-double` cells keep background usage — their inner text color is unchanged from today).
- Verify contrast arithmetic in the commit message for at least the `#f7e2dd` pairing (`#a23f2c` on `#f7e2dd` ≥ 4.5).

- [ ] Implement → `npm run build` + full vitest → Commit: `feat(web): score tokens take mockup values; -text variants keep WCAG AA`

---

## Part D — Verification & ship

### Task D1: full gates + PR

- [ ] Backend: `uv run python -m unittest discover -s tests 2>&1 | tail -3` → OK (no data/ symlink = CI-equivalent)
- [ ] Frontend: `npm test -- --run` (expect ≥195+new), `npm run lint`, `npm run build`, `npm run test:e2e` (2 projects)
- [ ] Scope: `git diff --stat origin/integration/v2...HEAD -- ':!web_v2' ':!docs' ':!ai_caddie' ':!server_v2' ':!tests'` → empty
- [ ] Push `superpowers/web-redesign-w1b`; PR → `integration/v2` (GH API, GH_TOKEN); title `feat(web+api): W1b — 趋势总览 + 概览落地页 + stats window param`
- [ ] Multi-agent adversarial review (same harness as W1a: 4 dimensions + refutation verifiers) BEFORE merge; fix confirmed findings; merge on CI green (user pre-authorized)

---

## Self-review notes
- Spec coverage: D2 (KPI) → C1; D3 (range) → A1+C1; §5.1 概览 → C3 (search uses §8.4 existing endpoint; 频道 via mobile course options for globalIds); §5.2 趋势总览 → C1; 强弱分析 merge → C2 (shot-derived metrics like GIR remain W2 per spec §8.2); colors → C4 per /goal. 球场/报告 pages keep current content (restyle not in W1b scope).
- Type consistency: StatsWindow shared by api.ts/App/TrendsOverview; trendsState separate from statsState so 球场/报告/数据质量 stay full-window; handicap fields read defensively (`typeof x === 'number'`).
- Known risk: App.test churn again (~20 anchors) — same migration discipline as W1a Task 8 (ledger: relocate, never drop).
