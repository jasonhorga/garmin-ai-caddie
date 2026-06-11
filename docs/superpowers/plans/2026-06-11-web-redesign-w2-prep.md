# Web Redesign W2 — 备战(赛前攻略)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Checkbox steps for tracking.

> **中文摘要:** 把备战页从"工程面板 CoursePrepPanel"升级为 spec §5.3 的三页签产品页:球场头部(名称/Par/码数/你的战绩)+ 概览(关键洞 + 逐洞速览)/ 逐洞攻略(现有洞图 + 你的历史落点散布)/ 针对你(个性化提示)。后端:提示组装引擎(复用 history_stats 已有的 teeDirection/approachMiss/parScoring/playerProfile 倾向)+ 击球点投影到洞图像素坐标。

**Key recon facts (verified, build on these):**
- Tendencies ALREADY computed per course in `history_stats.courses[]`: `teeDirection{hitPct,leftPct,rightPct,dominantMiss,…}`, `approachMiss{girPct,shortPct,…,dominantMiss}`, `parScoring[{key:par3/4/5,averageToPar,…}]`, plus global `playerProfile{strengths,weaknesses,caddieBiases[{direction,appliesTo,…}]}`. The "tips engine" is an ASSEMBLY of these × course features.
- `course_prep.prep_nine(global_id, holes, render)` returns per-hole: par/par_source/blue_yards/route_len_m/route/hazards{water_carry,bunkers}/steps/cautions/candidateRoutes/carryTargets/map{image,overlay{w,h,ppm,route(px)}}. Server route `/api/v2/courses/{gid}/prep` (admin-gated) at server_v2/main.py:399.
- Hole geometry: `data/courseview/prodgeometry/{gid}/Hole{nn}_{ver}/` — `hole.json` has `RefLat/RefLon` (world anchor), TeeLocations, Doglegs; meshes via `hole_render.load_mesh(gid,hole)`; render via `hole_render.render_hole(...)→(jpeg,overlay)`; local frame `_local(p)=(-x,z)`; overlay.ppm = px per metre.
- Shots: `data/shots/{scorecardId}.json` → `holeShots[{holeNumber,pinPosition{lat,lon},shots[{startLoc/endLoc{lat,lon,lie},meters,clubId,shotType,excludeFromStats,…}]}]`. lat/lon are RAW GARMIN SEMICIRCLES (int) → degrees = value × 180 / 2^31 (VERIFY against a real file: compute and sanity-check the degrees fall near the course RefLat/RefLon before trusting).
- globalId↔scorecards: played store / course_reference (`data/courses/{gid}.json`) + scorecard summaries hold front/back nine globalIds; mobile course options maps globalId↔courseKey/roundCount. Frontend already loads stats(all) + courseOptions at boot (W1b).
- Frontend reusables: CoursePrepPanel's HoleCard (map+SVG overlay+draggable ball+club chips+steps+cautions), `coursePrepPanelLogic.ts` helpers (`atCum`, `nearestCum`, readouts). `prepGlobalId` flows from 概览 via `<CoursePrepPanel key=… defaultGlobalId=…/>` (App.tsx).
- Tests: backend mirrors `tests/test_course_prep.py` (`_rect_mesh` helper, `patch.object(cp.hole_render,'load_mesh')`) and `tests/test_course_prep_api.py` (`_PAR_31870`, `_prep_row`). unittest only. Frontend vitest 219 baseline; e2e 2 projects.

**Branch:** `superpowers/web-redesign-w2-prep` off integration/v2 (c60c570) via EnterWorktree (verify base; reset if EnterWorktree picked a stale origin/HEAD). Node 24 via `export PATH="$HOME/node24/bin:$PATH"`. Backend: `uv run python -m unittest …` (729 baseline).

**Locked decisions (spec defaults):**
- 针对你 tips: deterministic, zh text, each with `sourceRefs`, priority-ordered, computed from tendencies × course features. NO canned/LLM text (D9).
- New-course (never played) degradation: 概览 shows HCP/length-based key holes only; 针对你 shows global tendencies (playerProfile) tips only; 逐洞速览 neutral.
- Shot scatter: END positions of TEE + APPROACH shots (skip putts/UNKNOWN), max ~80 dots/hole, excludeFromStats respected; dots colored by shotType (TEE green, APPROACH blue).
- Course header "你的战绩": roundCount/average18 via stats.courses joined client-side by courseKey (courseOptions gives globalId↔courseKey).

---

## Part A — Backend

### Task A1: prep tips assembly engine (TDD)

**Files:** Create `ai_caddie/prep_tips.py` + `tests/test_prep_tips.py`; modify `server_v2/main.py` (new route) + a server test.

Pure function:
```python
def build_prep_tips(*, course_row: dict | None, player_profile: dict | None, prep_holes: list[dict]) -> dict:
    """ai-caddie-prep-tips-v1: {schema, tips: [{priority, severity, text, basis, sourceRefs}], courseKey|None}"""
```
Rules (deterministic, ordered by severity desc; each tip cites sourceRefs from its inputs):
1. teeDirection.dominantMiss ('left'/'right') with leftPct/rightPct ≥ 40 → tip: `开球偏{左|右}({pct}%)…` + name the holes where it bites: prep holes with par≥4 AND (hazards.water_carry non-empty OR len(hazards.bunkers)>0) listed as `第N洞`; severity high if pct≥55 else medium.
2. approachMiss.dominantMiss == 'short' with shortPct ≥ 35 → `攻果岭常偏短({pct}%),本场多带半杆` severity medium (long/left/right analogues).
3. parScoring rows: best `averageToPar` ≤ +0.4 → strength tip `三杆洞稳(平均+X),按部就班`; worst ≥ +1.0 → caution `Par{N} 平均+X,保守开局` (par3/4/5 zh labels).
4. playerProfile.caddieBiases (appliesTo includes 'tee'/'approach'): one tip each, text from label+direction, severity from severity_score (≥0.6 high).
5. No course_row (new course): only rules 3-applicable-from-profile + 4, plus `新球场:按 HCP 与长度提示` informational tip listing the 3 longest par-4/5 holes from prep_holes.
Cap 6 tips. Empty inputs → `tips: []`.

Tests: hand-built course_row/profile/prep_holes fixtures asserting exact tip texts/order/severity/sourceRefs; new-course path; cap; empty.

Route: `GET /api/v2/courses/{global_id}/prep-tips` (admin-gated like prep): loads stats via `load_history_stats_response()` parts — implementation: call `cached_build_history_stats` path indirectly through a small loader in server_v2 that finds courses[] row whose courseKey matches the globalId (mapping via mobile course options helper or course_reference played store — find the existing globalId→courseKey source in `ai_caddie/mobile_live.py` `_course_prep_package`/options builder and reuse) + playerProfile + `prep_nine(global_id, render=False)` features. Response = build_prep_tips output. Server test: fixture mode, assert schema + deterministic tips for the fixture course (31795/'black_knight' fixture data has teeDirection etc. — inspect fixture stats first; if fixture tendencies are empty, patch the loader inputs in the test).

Commit: `feat(api): prep-tips assembly from existing per-course tendencies`

### Task A2: shot scatter projection into prep holes (TDD)

**Files:** Modify `ai_caddie/course_prep.py` (+ projection helper in `ai_caddie/hole_render.py` or new `ai_caddie/shot_projection.py`); tests `tests/test_shot_projection.py` + extend `tests/test_course_prep_api.py`.

1. `semicircles_to_degrees(v)` + `project_world_to_pixel(lat_deg, lon_deg, *, ref_lat, ref_lon, overlay)` — world→local metres (equirectangular: dx = (lon−ref_lon)·111320·cos(ref_lat), dy=(lat−ref_lat)·110540 — VERIFY axis orientation against the mesh frame by projecting the course's own TeeLocations/pin and checking they land within overlay bounds; the mesh local frame and `_local(p)=(-x,z)` flip must be derived from hole.json + render code, not guessed. Write an integration-style test against the committed fixture geometry (gid 31870 hole 3 fixtures exist; `AI_CADDIE_RUN_GEOMETRY_BACKED_TESTS=1` pattern) plus pure unit tests with a synthetic overlay).
2. `shots_for_hole(global_id, local_hole) -> list[dict]`: find scorecards whose front/back nine globalId == global_id (reuse the existing source that course_reference/build_played_store uses for the gid↔scorecard mapping — locate it; if absent, derive from scorecard detail JSONs' nine globalIds), load shot files, take holeShots rows matching the LOCAL hole number on that nine (front nine: holeNumber 1-9 ↔ local 1-9; back nine: holeNumber 10-18 ↔ local 1-9 — verify how existing code maps local holes for back nines, e.g. in history/geometry code), filter shots: shotType in (TEE, APPROACH), excludeFromStats false.
3. `prep_hole(..., include_shots=False)`: when True and render and shots exist → hole dict gains `yourShots: [{x, y, club, shotType, roundId}]` (pixel ints, clipped to overlay bounds; club via `club_name_from_details`). Cap 80, newest rounds first. Missing geometry/render → omit key.
4. Server: prep endpoint gains `include_shots: bool = Query(False)`; mobile package path unaffected (defaults False everywhere else).

Tests: pure projection math (synthetic ref + overlay, hand-computed px); semicircle conversion sanity vs a real-file value (commit a TINY anonymized fixture: one holeShots row with 2 shots, lat/lon shifted — synthesize values rather than copying real coords); shots_for_hole mapping incl. back-nine local-hole mapping; API test asserts `yourShots` present only with include_shots=true and shots fixture wired (patch the loader).

Commit: `feat(api): project user shot scatter into prep hole renders (include_shots)`

### Task A3: backend full sweep gate

`uv run python -m unittest discover -s tests` → OK. Commit only if fixes needed.

---

## Part B — Frontend

### Task B1: api + types

`fetchPrepTips(globalId, adminToken?)` → `PrepTipsResponse {schema:'ai-caddie-prep-tips-v1', courseKey: string|null, tips: [{priority:number, severity:'high'|'medium'|'info', text:string, basis:string, sourceRefs:string[]}]}`; `fetchCoursePrep` gains `includeShots?: boolean` (appends `include_shots=true`); `CoursePrepHole` gains `yourShots?: Array<{x:number,y:number,club:string|null,shotType:string,roundId:string}>`. api.test.ts additions (URL building both params). Commit: `feat(web): prep-tips + include_shots API clients`

### Task B2: PrepPage shell (course header + subnav + wiring)

Create `web_v2/src/components/PrepPage.tsx` (+test). Props:
```tsx
interface PrepPageProps {
  globalId: number | null                       // null → entry state
  courseOptions: MobileCourseOptionsResponse | null
  allStats: HistoryStatsResponse | null
  adminToken?: string
  onSearchCourses: (name: string) => Promise<CourseSearchResponse>
  onSelectCourse: (globalId: number) => void
}
```
- globalId null → entry: search box + frequent courses (same building blocks as 概览's prep card — extract the shared search+frequent UI into `web_v2/src/components/CourseFinder.tsx` reused by BOTH HomeOverview and PrepPage entry; refactor HomeOverview to consume it, keeping its tests green with minimal edits).
- globalId set → header: course name (from courseOptions match or search result cache; fallback `球场 {gid}`), Par/码数 (sum from prep response once loaded), 你的战绩 `打过 N 次 · 均杆 X`(stats.courses via courseKey from courseOptions match; hide when unplayed) + 换球场 button (→ entry state via onSelectCourse? use internal mode or App state setPrepGlobalId(null) — wire App: `onSelectCourse=handlePrepCourse`, 换球场 → `setPrepGlobalId(null)` stays on prep page entry).
- Internal subnav (reuse SubNav component, variant inner): 概览 / 逐洞攻略 / 针对你 (local useState, not ProductPage).
- PrepPage owns its data fetching: `fetchCoursePrep(gid,{render:true},token,includeShots:true)` + `fetchPrepTips(gid,token)` on mount/gid change (loading/error states with 重试; race-guard with seq ref — the W1b idiom).
- App.tsx: prep branch renders `<PrepPage globalId={prepGlobalId} …/>` (replacing bare CoursePrepPanel). CoursePrepPanel STAYS in the repo for now (its HoleCard internals are consumed in B3) — only the page-level usage changes.
Tests: entry↔course states, header join logic (courseKey→record), subnav switching, 换球场.
Commit: `feat(web): PrepPage shell — course header, entry finder, 三页签`

### Task B3: 逐洞攻略 subpage (hole cards + shot scatter)

Extract HoleCard from CoursePrepPanel into `web_v2/src/components/PrepHoleCard.tsx` (move, not copy; CoursePrepPanel imports it to stay functional for its remaining tests, or — preferred — DELETE CoursePrepPanel entirely and move its still-valuable tests onto PrepPage/PrepHoleCard; choose deletion if no other consumer: grep). Add scatter rendering: `yourShots` dots in the SVG overlay (circle r=3, TEE `var(--green)`, APPROACH `var(--birdie)`, opacity .7, `<title>` with club+round). Legend line `你的落点:开球 ● 攻果岭 ●` when dots exist. Keep draggable ball + club chips + steps + cautions intact.
逐洞攻略 tab renders all holes' PrepHoleCards (existing behavior) with scatter.
Tests: scatter dots rendered from yourShots fixture; absent gracefully.
Commit: `feat(web): 逐洞攻略 — hole cards with your shot scatter overlay`

### Task B4: 概览 + 针对你 subpages

概览 tab: 关键洞 cards — played: stats.holes rows for this courseKey sorted averageToPar desc top 3 (`第{hole}洞 · Par{par} · 平均+{x}` + worst score line); unplayed: 3 longest par4/5 from prep holes (`第{hole}洞 · Par{par} · {yards}码 · 长洞注意`). 逐洞速览 strip: per prep hole chip colored by your averageToPar (reuse the trends chip classes; neutral when no history), click → jump to 逐洞攻略 scrolled to that hole (anchor via element id `prep-hole-{n}`).
针对你 tab: tips list — severity dot (high `--double-text`, medium `--bogey-text`, info `--muted`), text, basis sub-line; empty → `暂无足够数据生成提示`.
Tests: played/unplayed key-holes logic; strip coloring; tips render order/severity colors; empty state.
Commit: `feat(web): 备战概览(关键洞+逐洞速览) + 针对你(个性化提示)`

### Task B5: test/e2e migration + zh sweep of the prep page

- App.test prep-related tests: the W1b handoff test asserts CoursePrepPanel's input value '31795' — update to PrepPage reality (assert header shows the chosen course, e.g. 'Black Knight B/C', and prep fetch called with 31795). e2e: 备战 step asserts heading 赛前球场攻略 — PrepPage keeps an h2 赛前球场攻略? Decide: header h2 = course name; keep a stable e2e anchor: the entry state shows `想备哪场?`-style heading? e2e currently clicks 备战 with prepGlobalId null → entry state. New anchor: `getByText('选择球场开始备战')` (entry heading — implement exactly this string in B2) and extend e2e: from 概览 click a frequent course's 去备战 → assert course header + 逐洞攻略 tab content visible (mockApi must stub `/api/v2/courses/{gid}/prep` + `/prep-tips` — add fixtures to the e2e spec).
- Full gates: backend discover OK; vitest all; lint; build; e2e 2/2.
Commit: `test(web): prep-page e2e walk + migrated handoff assertions`

---

## Part C — Ship

### Task C1: gates, PR, adversarial review, merge
1. Full local gates (both stacks). 2. Push `superpowers/web-redesign-w2-prep`; PR → integration/v2. 3. Same adversarial workflow as W1a/W1b (4 dimensions: backend correctness incl. projection math vs real fixture geometry; frontend state/races; test mutation probes; UX/a11y/zh + contrast on new classes). 4. Fix confirmed findings. 5. CI green → merge (pre-authorized). 6. Exit+remove worktree; update memory; proceed to W3.

## Self-review
- Spec §5.3 coverage: entry(搜索+常打 via shared CourseFinder)✓ header(no date pin)✓ 概览(key holes+速览)✓ 逐洞攻略(real geometry render+scatter D8)✓ 针对你(computed tips D9, sourceRefs)✓ degradation for unplayed/missing-geometry ✓.
- §8.2 note: GIR/fairway%/proximity aggregates already exist as approachMiss/teeDirection (course-sliced) — W2 consumes them; a standalone "shot-analytics module" is NOT rebuilt (avoid duplication). 强弱分析 page enrichment with these = W3-adjacent polish, out of W2 scope.
- Risks: semicircle→degrees + mesh-frame orientation (A2 has fixture-anchored tests + sanity gates); CoursePrepPanel deletion ripples (grep-gated); e2e new stubs.
