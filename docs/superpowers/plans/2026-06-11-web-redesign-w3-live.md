# Web Redesign W3 — 实战(web)Implementation Plan

> **2026-07-16 AUTHORITY CORRECTION — HISTORICAL PLAN：**本计划中的手工风输入与风力决策沙盘违反 L18，不能继续作为现行 v1 实施依据；Web 的深编辑边界也以后续 D10 为准。保留文件仅用于追溯已实现来源，当前冲突见[全仓 Owner-gate 审计](../../reviews/2026-07-16-repository-wide-owner-gate-authority-and-drift-audit.md)。

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Checkbox steps for tracking.

> **中文摘要:** 把「实战」从旧工程页(CaddiePage 仪表盘)升级为 spec §5.4 web 范围的产品页:**决策沙盘**(选球场/洞 → 在洞图上拖球摆位 → 设球位状态/风/稳博 → 出一条主建议)+ **最近回放**(最近球局逐洞回看)+ **完整工具**页签(旧 CaddiePage 原样保留,零功能丢失)。纯前端阶段,后端零新增端点。

**CRITICAL recon caveat:** the recon fact-sheet was partly read from a STALE checkout. Implementers MUST verify frontend wiring against the WORKTREE (post-W2: AppShell exists, PrepHoleCard exists, CoursePrepPanel deleted, PrepPage on 'prep'). The API contracts below were verified and are current.

**Verified contracts (current):**
- `GET /api/v2/caddie/context` (api.ts fetchCaddieContext) params: `sourceRef`(required), `shotType`('tee'|'approach'|'recovery'), `distanceToPinM?`, `lie?`(free string; 'fairway'/'rough'/'bunker'/'green'/'fringe' used), `currentLatitude/Longitude?`, `targetLatitude/Longitude?`, `strategyMode?`(''|'protect_score'|'attack'), `startX/startY/targetX/targetY?`, `landingRadiusM?`. → `{context, evidence, missingData}` (context: globalId/localHole/clubProfiles/hazards/historicalHoleIssues/…).
- `POST /api/v2/caddie/decision` body `{shotType, context, includeExplanation?}` → options[](id label club carry_m riskScore confidence), selectedOptionId, sequences, acceptableMiss{direction,rationale}, confidence, explanation{narrative,factBinding}, missingData. Strategy preference flows through context.strategyMode (NOT a top-level request field). 稳/博 mapping: 稳=protect_score, 博=attack, 默认=stock('').
- Wind: `GET /api/v2/weather/snapshot` accepts MANUAL `windSpeedMps`/`windDirectionDeg` (source 'manual'); CaddiePage merges weatherSnapshot into the decision context. The sandbox does the same.
- ⚠ `startX/startY/targetX/targetY` UNITS: the old panel fed "hole render space" route coords — BEFORE building the drag→request mapping, READ `server_v2/caddie.py` + the ai_caddie context builder to determine the expected frame/units (route-space metres vs px). If route-space metres: dragged px → `nearestCum(route,px,py)` (metres along route) and/or px→metres via overlay.ppm. Write this up in the component as a comment with the source line cited.
- Replay data: `fetchHistoryRoundDetail(roundRef)` + existing `HistoryRoundDetailPanel` (standalone-capable: props `state`, `onSelectRef`, `onRetryRound`, `onCreateAnnotationForRound`, report props — check current signature in worktree). Recent rounds list: `overviewState.data.recentRounds` (10, post-W1b).
- Sandbox map: prep response per hole `map{image, overlay{w,h,ppm,ln,route[[px,py,cum]]}}` + `fetchCoursePrep(gid,{holes?},token)`; drag helpers `atCum`/`nearestCum` in `coursePrepPanelLogic.ts`; PrepHoleCard renders but is prep-specific — the sandbox builds its OWN lean map canvas reusing the helpers (extract shared bits only if clean).

**Branch:** `superpowers/web-redesign-w3-live` off integration/v2 (c71cc95) via EnterWorktree (verify base = origin/integration/v2; reset if stale). Node 24 PATH. Frontend baseline post-W2: vitest 276/30 files, e2e 2/2, backend 778.

**IA decision (locked):** 实战 page = three inner tabs (PrepPage idiom, local state, subnav--inner classes): `决策沙盘`(default) / `最近回放` / `完整工具`. 完整工具 hosts the EXISTING CaddiePage component VERBATIM (all media/audit/context tooling preserved → no functionality deleted, CaddiePage tests survive with wiring-only edits). Topbar h1 stays 实战 (shell). e2e 'Caddie' heading anchor will change → new anchors below.

---

### Task T1: LivePage shell + tabs + App wiring

**Files:** Create `web_v2/src/components/LivePage.tsx` + test; modify `App.tsx` (caddie branch renders LivePage; CaddiePage becomes its child), `App.test.tsx` (caddie-flow tests now click into 完整工具 first), e2e (实战 step asserts the sandbox entry anchor `决策沙盘` tab + heading `选择球场开始模拟`).

LivePage props: everything CaddiePage needs (pass-through) + sandbox/replay needs:
```tsx
interface LivePageProps {
  // sandbox
  courseOptions: MobileCourseOptionsResponse | null
  adminToken?: string
  onSearchCourses: (name: string) => Promise<CourseSearchResponse>
  // replay
  recentRounds: RoundCardType[]
  // 完整工具 (verbatim CaddiePage props bundle)
  caddieProps: ComponentProps<typeof CaddiePage>
}
```
(Implementer: check ComponentProps pattern acceptability vs explicit re-listing; pick the cleaner; LivePage renders `<CaddiePage {...caddieProps}/>` in the third tab.)
Tabs default 决策沙盘 showing a course-pick entry (heading EXACTLY `选择球场开始模拟`, CourseFinder reuse with custom heading/sub copy). Tab switching test; CaddiePage render-in-tab test (assert its 'Caddie' heading appears only after clicking 完整工具).
App.test migration: existing caddie tests prepend `click 完整工具` after `click 实战`. e2e: 实战 step → assert `选择球场开始模拟`; ADD a 完整工具 click asserting the old 'Caddie' heading (coverage preserved).
Commit: `feat(web): LivePage shell — 沙盘/回放/完整工具 tabs (CaddiePage preserved verbatim)`

### Task T2: 最近回放 tab

LivePage replay tab: round list (recentRounds rows — date/course/score chips, click selects) + the selected round's detail via NEW lightweight fetch state inside LivePage (`fetchHistoryRoundDetail`) rendered through the EXISTING `HistoryRoundDetailPanel` (verify its current props in the worktree; wire minimal handlers: onSelectRef may navigate… keep it inert (no-op) or wire to the existing App drilldown handler if cheaply passable — prefer passing App's `onSelectRef`/`onOpenRoundDetail` handlers through LivePage props so drilldown panels behave exactly as on history pages). Default selection: first recent round, auto-loaded on tab open (lazy). Loading/error+重试; seq guard (race idiom). Tests: list renders, click loads detail (mock), stale-response guard test, error retry.
Commit: `feat(web): 最近回放 — recent-round replay via round detail panel`

### Task T3: 决策沙盘 — course/hole pick + map + draggable ball + situation readout

Sandbox state machine inside LivePage (or `LiveSandbox.tsx` subcomponent — preferred file split): course picked (CourseFinder; name passthrough like W2) → `fetchCoursePrep(gid, …includeShots false… holes default)` (race-guarded) → hole picker (chips 1..N from response) → map canvas for the chosen hole: image + overlay route polyline + tee/green markers + DRAGGABLE ball (reuse atCum/nearestCum; initial ball at tee, i.e. cum=0) + readout `距T {x}m · 到果岭 {y}m`(= ln−cum). Holes without map degrade: distance-only mode (numeric 到果岭 input replaces the map; sandbox still works).
FIRST verify startX/Y units (read server_v2/caddie.py + builder; cite line in code comment). Derive from ball: `distanceToPinM = ln − cum`(round 1dp) and shotType auto: cum==0→'tee' else 'approach' (user-overridable select incl. 'recovery').
Tests: hole switch resets ball; drag updates readout (pointer events like PrepHoleCard tests); degraded no-map path.
Commit: `feat(web): 决策沙盘 — course/hole pick, draggable ball, situation readout`

### Task T4: 沙盘建议 — inputs + decision flow + advice card

Inputs row (zh): 球位状态 select(球道/长草/沙坑/果岭边/果岭 → lie strings fairway/rough/bunker/fringe/green), 风 speed m/s + direction deg numeric inputs (optional; when set → include manual weatherSnapshot via fetchWeatherSnapshot manual params OR construct the snapshot object client-side if the API requires a fetch — check how CaddiePage builds weatherSnapshot into context and mirror), 策略 segmented 稳/默认/博 (protect_score/''/attack).
`要建议` button: context fetch (sourceRef: needs one — check what context builder REQUIRES; the old panel used roundRef:hole refs like '900001:7'. For a pure course/hole sandbox WITHOUT a round, determine if sourceRef can be a course-form ref — read build_caddie_context_response: if sourceRef must resolve to a played hole, derive one from stats/drilldown (latest round on this course+hole) and DEGRADE to the latest ANY round ref when none (engine context still binds clubs/history); document the chosen rule) → decision POST (includeExplanation true) → advice card: 主建议 = selectedOption (club big + label + carry + riskScore dot + confidence pill) + `为什么`(explanation.narrative) + acceptableMiss line + 其它选项 chips (click→show that option's numbers; purely informational) + missingData chips. 稳/博 switch RE-REQUESTS (context+decision) with the new strategyMode (race-guarded; loading state on the card only).
Tests: lie/strategy flow into params (mock asserts query/body), advice renders selected option + narrative, 稳→博 refetch asserted, error+重试, degraded distance-only flow works end-to-end.
Commit: `feat(web): 沙盘建议 — 球位/风/稳博 inputs, decision advice card`

### Task T5: e2e walk + gates

e2e: 实战 → 选择球场开始模拟 → pick frequent course (mock prep) → hole chip → drag skip (pointer drags are flaky in e2e; instead assert readout initial) → set 球位状态 → 要建议 (mock context+decision payloads — reuse App.test fixtures) → advice card visible (club + 为什么) → 稳/博 toggle → second decision call recorded → 最近回放 tab → round list + detail (mock round detail) → 完整工具 → 'Caddie' heading. Overflow checks per state; failedResponses/browserErrors stay empty (mock every endpoint the flow hits).
FULL gates: backend discover (untouched, but run), vitest, tsc, lint, build, e2e 2/2.
Commit: `test(e2e): 实战 full walk — sandbox advice, replay, full-tools`

### Task T6: ship
Push → PR → adversarial review workflow (dimensions: sandbox correctness incl. units/sourceRef rule; CaddiePage preservation regression; test mutations; UX/a11y/zh) → fix confirmed findings → CI green → merge (pre-authorized). Exit+remove worktree; update memory (W1-W3 complete = /goal condition); final summary to user.

## Self-review
- §5.4 web scope ✓ (sandbox: course/hole, ball on render, wind/lie, 稳/博 via strategyMode recompute; replay; no fake GPS). D7 honored: ONE main recommendation + toggle; no score-strategy.
- Nothing deleted: CaddiePage verbatim in 完整工具 ✓.
- Risks: sourceRef requirement for context (T4 instructs reading the builder and defining the degradation rule); startX/Y units (T3 verify-first); e2e drag flakiness avoided by design.
