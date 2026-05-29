# AI Caddie Competitor Research

Date: 2026-05-24

Research scope:

- Garmin Golf iOS app, inspected through iPhone Mirroring on the user's account.
- GolfLive WeChat mini program, inspected through iPhone Mirroring and Mac WeChat.
- Sensitive account details, friend names, phone numbers, chat content, and identifiers are intentionally omitted or generalized.
- Screenshots are not committed in this first pass because the inspected pages contain private account, friend, and score history. Page evidence is recorded as structured notes below.

## Executive Summary

### 10-20 Most Important Findings

1. Garmin Golf's strongest history surface is the activity list: each round card shows course, date, tee/course segment, total score, to-par, and a compact per-hole color strip.
2. Garmin's round detail is compact and useful: first viewport shows course, tee/course segment, date, scorecard, total score, to-par, and a score distribution chart.
3. Garmin's complete scorecard expands from hole scores into fairway direction, GIR, putts, and penalties. This is a strong model for progressive disclosure.
4. Garmin's performance stats are organized by game phase: tee shot, approach, short game, putting. It includes differential, best/average scores, recent-10-round context, and comparison bars.
5. Garmin's course stats page is action-oriented for repeated courses: total rounds, last played date, average score range, tee shot fairway direction split, and recent tee shot distance with a hole image.
6. Garmin's club stats page is simple but valuable: valid shots by club, normal distance, and max distance.
7. Garmin does not visibly explain why a round was good or bad in tactical terms. It provides stats but little causal review.
8. Garmin's shot map is useful when available, but it is separated from longer-term course/hole history and route decisions.
9. GolfLive's history landing page is much broader than Garmin's: it exposes scorecards, play records, spectating records, trajectories, recent results, score distribution, frequency, played courses, course map, annual summary, and secondary social/competition archives in one list.
10. GolfLive's scorecard list is richer than Garmin's: one card can include multiple players and displays per-hole relative-to-par boxes plus front/back totals. For our product, the useful part is the compact per-hole history display, not the social layer.
11. GolfLive's round detail is review-oriented: it shows player columns, score mode, per-hole relative scores, export image, photo wall, manual scoring, PK scoring, PK rules, and AI review entry. For our product, the useful part is the scorecard-to-review flow.
12. GolfLive's AI review is paid/token-gated. The entry clearly shows point cost and a "generate report" CTA.
13. GolfLive's annual summary is practical and compact: grouped by quarter, with count, average, best, worst, birdies, eagles, and doubles.
14. GolfLive's score distribution page uses a pyramid plus histogram; it shows distribution counts and percentages in a way that is easier to understand than raw tables.
15. GolfLive's play record timeline has filters for all competitions and year/month, and lists rounds grouped by month with participant rows and ended status.
16. GolfLive's course distribution map emphasizes "where I played" better than Garmin's visible history pages.
17. GolfLive's historical record keeps social/group context available, but this research treats it only as context around a round, not as a product direction to copy.
18. Neither product appears to connect history to next-shot or next-round caddie decisions in a transparent way.
19. Neither product clearly exposes data quality: missing shots, missing putts, weak samples, geometry confidence, or whether a statistic is based on enough data.
20. Our AI Caddie should not copy either app's surface exactly. The opportunity is to combine Garmin's shot/club data with GolfLive's history breadth, then add explainable route and practice recommendations.

### 5 Things Garmin Golf Does Well

1. Round history cards are information-dense without being cluttered: course, date, score, to-par, and hole color strip fit in one card.
2. Scorecard detail progressively expands into fairway, GIR, putts, and penalties instead of showing everything by default.
3. Performance stats are phase-based and compare the user against a reference average.
4. Course stats include actionable tee-shot direction split and distance examples.
5. Club stats use a simple table that is immediately understandable.

### 5 Things GolfLive Does Well

1. The history section is comprehensive and discoverable from one screen.
2. Annual/quarterly summaries are easy to scan and include outcome counts, not only average score.
3. The score distribution pyramid communicates scoring level faster than a normal table.
4. Round detail puts scorecard review, export, and AI review entry in one place.
5. AI review is positioned directly on the round detail page, where the user's intent to review is highest.

### 5 Things Both Products Do Poorly

1. Neither makes data confidence explicit.
2. Neither gives clear hole-specific strategy recommendations from historical outcomes.
3. Neither explains "why this round was worse/better" with shot-level evidence.
4. Neither appears to combine course geometry, hazards, and personal club dispersion into recommendations.
5. Neither separates "fact", "inference", and "recommendation" clearly.

### 5 Things Our AI Caddie Should Do First

1. Build a History Review v2 landing page with Garmin-style recent round cards plus GolfLive-style history modules.
2. Add an annual/quarterly/monthly summary with score average, best/worst, birdie/par/bogey/double counts, rounds, courses, and data quality.
3. Add a round review page that explains score loss by hole and shot, not only displays the scorecard.
4. Add course and hole review pages showing repeated performance, shot patterns, hazard relationships, and recommended route options.
5. Add a club model page with median, p10/p90, sample size, miss pattern, and "can trust this club distance?" status.

## Page-Level Notes

### Garmin Activity List

- Product: Garmin Golf
- Entry path: Open Garmin Golf app -> bottom `活动`.
- Main purpose: Let the user find recent rounds and quickly see score outcome.
- Core metrics:
  - Course name
  - Date
  - Tee/course segment
  - Total score
  - To-par
  - Per-hole color strip
- Main interactions:
  - Scroll recent rounds
  - Tap a round for detail
  - Top-right filter/menu
- Information hierarchy:
  - First viewport: list of round cards, newest first.
  - Each card: course metadata on left, score on right, hole outcome strip at bottom.
- Strengths:
  - Very fast round selection.
  - Hole color strip gives immediate round shape.
- Weaknesses:
  - No visible grouping by month/year.
  - No explicit reasons for score changes.
- What we should borrow:
  - Compact card structure and per-hole strip.
- What we can do better:
  - Add delta against personal/course average and data coverage badges.
- Evidence assets:
  - Live inspected through iPhone Mirroring; screenshots omitted for privacy.

### Garmin Round Detail

- Product: Garmin Golf
- Entry path: Activity list -> tap a round.
- Main purpose: Review one completed round.
- Core metrics:
  - Course, course segment, tee
  - Date
  - Total score and to-par
  - Hole-by-hole scorecard
  - Score distribution
- Main interactions:
  - View full scorecard
  - View shot map
  - Share/export
  - Edit scorecard
- Information hierarchy:
  - First viewport: course/date header, scorecard card, statistics card.
  - Scroll: score distribution and more round stats.
- Strengths:
  - Clear summary of one round.
  - Scorecard and shot map entries are close to each other.
- Weaknesses:
  - The round is still mostly descriptive, not diagnostic.
  - No visible "lost strokes came from X" narrative.
- What we should borrow:
  - Scorecard-first round review layout.
- What we can do better:
  - Add structured round diagnosis: high-cost holes, hazard mistakes, club misses, putting count, and route alternatives.
- Evidence assets:
  - Live inspected through iPhone Mirroring; screenshots omitted for privacy.

### Garmin Complete Scorecard

- Product: Garmin Golf
- Entry path: Round detail -> `查看完整记分卡`.
- Main purpose: Inspect hole-level scoring details.
- Core metrics:
  - Hole number
  - Par
  - Score
  - Fairway direction
  - GIR
  - Putts
  - Penalties
- Main interactions:
  - Tap/expand user row to show detail rows.
  - Edit.
- Information hierarchy:
  - First viewport: score table.
  - Expanded row: fairway, GIR, putts, penalties.
- Strengths:
  - Progressive disclosure is effective.
  - The core hole metrics are exactly what a post-round review needs.
- Weaknesses:
  - No hole map or hazard context in the table itself.
- What we should borrow:
  - Expandable scorecard rows.
- What we can do better:
  - Add per-hole issue tags: tee miss, approach miss, penalty, three-putt, bunker, water, recovery.
- Evidence assets:
  - Live inspected through iPhone Mirroring; screenshots omitted for privacy.

### Garmin Performance Stats

- Product: Garmin Golf
- Entry path: Garmin Golf -> bottom `统计` -> `表现统计`.
- Main purpose: Evaluate overall performance by game phase.
- Core metrics:
  - Differential
  - Number of 9-hole and 18-hole rounds
  - Best and average scores
  - Recent 10-round context
  - Tee shot, approach, short game, putting comparison bars
- Main interactions:
  - Scroll chart sections
  - Help entry
- Information hierarchy:
  - First viewport: differential and round-count summary, then phase overview chart.
- Strengths:
  - Game-phase framing is useful and actionable.
  - Recent-form comparison exists.
- Weaknesses:
  - It does not show the underlying shot examples on the first screen.
- What we should borrow:
  - Phase-based summary.
- What we can do better:
  - Link each weak phase to concrete rounds, holes, shots, and practice/strategy suggestions.
- Evidence assets:
  - Live inspected through iPhone Mirroring; screenshots omitted for privacy.

### Garmin Course Stats

- Product: Garmin Golf
- Entry path: Garmin Golf -> `统计` -> `球场统计` -> select course.
- Main purpose: Review repeated performance at a specific course.
- Core metrics:
  - Course name and location
  - Holes/par
  - Total rounds
  - Last played
  - Average score range
  - Tee shot fairway direction split
  - Recent tee shot distance with hole image
- Main interactions:
  - Course selection list
  - Scroll course stat cards
- Information hierarchy:
  - First viewport: course summary, score range, tee direction chart, recent tee distance.
- Strengths:
  - Tee miss pattern is immediately visible.
  - Recent shot card makes statistics more concrete.
- Weaknesses:
  - Course-level history is not clearly connected to hole-level strategy.
- What we should borrow:
  - Course selector and tee direction split.
- What we can do better:
  - Add hole ranking, repeated hazard misses, and suggested tee/approach route for each hole.
- Evidence assets:
  - Live inspected through iPhone Mirroring; screenshots omitted for privacy.

### Garmin Club Stats

- Product: Garmin Golf
- Entry path: Garmin Golf -> `统计` -> `挥杆统计`.
- Main purpose: Understand distance by club.
- Core metrics:
  - Club name
  - Valid shot indicator/count grouping
  - Normal distance
  - Max distance
- Main interactions:
  - Scroll club list
- Information hierarchy:
  - Table ordered from unknown/driver/fairway woods/hybrids/irons downward.
- Strengths:
  - Simple and immediately useful.
- Weaknesses:
  - Max distance can be misleading.
  - No p10/p90, dispersion, carry/total, lie filtering, or sample confidence visible.
- What we should borrow:
  - Club table as baseline.
- What we can do better:
  - Add sample size, median, p10/p90, left/right/short/long misses, and confidence.
- Evidence assets:
  - Live inspected through iPhone Mirroring; screenshots omitted for privacy.

### GolfLive Home / Non-History Scope Boundary

- Product: GolfLive WeChat mini program
- Entry path: WeChat -> search `GolfLive` mini program.
- Main purpose: Confirm navigation path into the history module.
- Core metrics:
  - History is a first-class bottom tab.
- Main interactions:
  - Bottom `历史` tab opens the historical record area.
  - Other homepage entries observed but intentionally excluded from this report: `AI工具`, `球场`, `高球圈`, `我的球队`, `更多`, `赛事广场`, `比赛/报名`, `视频`, `球友`, `我的`.
- Information hierarchy:
  - First viewport is mostly visual background and non-history navigation modules.
- Strengths:
  - The history entry is always visible in the bottom navigation.
- Weaknesses:
  - The homepage itself is not relevant to history review.
- What we should borrow:
  - Nothing beyond keeping history easy to reach.
- What we can do better:
  - Our first screen should go straight to history metrics, not event/social/booking.
- Evidence assets:
  - Live inspected through iPhone Mirroring; screenshots omitted for privacy.

### GolfLive History Hub

- Product: GolfLive WeChat mini program
- Entry path: Bottom `历史`.
- Main purpose: Central archive for score, play, course, and yearly history.
- Core metrics/modules:
  - `成绩卡` count
  - `打球记录` count
  - `围观记录` count
  - `打球轨迹`
  - `最近成绩`
  - `成绩分布图`
  - `打球频率`
  - `打过的球场` count
  - `球场分布图`
  - `年度汇总`
  - `联盟杯`
  - `球友统计` count
- Main interactions:
  - Tap each module to drill down.
- Information hierarchy:
  - First viewport: complete list of history modules grouped in cards.
- Strengths:
  - Very broad history surface.
  - Counts communicate data volume.
- Weaknesses:
  - Many modules are flat entries with little explanation.
- What we should borrow:
  - A history hub with explicit modules and counts.
- What we can do better:
  - Add status badges: supported, missing data, needs sync, low confidence.
- Evidence assets:
  - Live inspected through iPhone Mirroring; screenshots omitted for privacy.

### GolfLive Scorecard List

- Product: GolfLive WeChat mini program
- Entry path: `历史` -> `成绩卡`.
- Main purpose: Browse scorecard archive.
- Core metrics:
  - Date
  - Participants
  - Course
  - Front/back hole score boxes
  - Front/back totals
  - Total score
- Main interactions:
  - Scroll list
  - Tap scorecard
- Information hierarchy:
  - Cards show one round each; score is emphasized at bottom-right.
- Strengths:
  - Multi-player context is visible.
  - Per-hole relative boxes show round shape quickly.
- Weaknesses:
  - Dense cards can be harder to read than Garmin's recent-round list.
- What we should borrow:
  - Per-hole score boxes and social/multi-player optional context.
- What we can do better:
  - Keep personal review cleaner; use social only when relevant.
- Evidence assets:
  - Live inspected through iPhone Mirroring; screenshots omitted for privacy.

### GolfLive Round Detail

- Product: GolfLive WeChat mini program
- Entry path: `历史` -> `成绩卡` -> tap a card.
- Main purpose: Review a group/competition scorecard.
- Core metrics:
  - Course and date/time
  - Player columns
  - Hole relative scores
  - Score mode
  - Player totals
- Main interactions:
  - Toggle `记分组` / `照片墙`
  - Export image
  - Bottom actions: `AI点评`, `人工算分`, `PK得分`, `PK规则`
- Information hierarchy:
  - First viewport: round header, score table, bottom action bar.
- Strengths:
  - Directly supports group play and tournament workflows.
  - AI review entry is located at the point of review.
- Weaknesses:
  - Shot-level explanation is not visible.
  - AI review appears token-gated.
- What we should borrow:
  - Round review actions attached to scorecard detail.
- What we can do better:
  - Generate fact-based review automatically from Garmin data and geometry.
- Evidence assets:
  - Live inspected through iPhone Mirroring; screenshots omitted for privacy.

### GolfLive AI Review

- Product: GolfLive WeChat mini program
- Entry path: Round detail -> `AI点评`.
- Main purpose: Generate AI review for a round.
- Core metrics:
  - Point balance
  - Point cost
  - Review type dropdown, observed as `AI播客-成绩点评`
- Main interactions:
  - Select review type
  - Generate report CTA
  - Recharge link
- Information hierarchy:
  - Bottom sheet overlay with cost and generation control.
- Strengths:
  - Clear monetization and action point.
- Weaknesses:
  - Not transparent about inputs or confidence.
- What we should borrow:
  - Place AI review where users already inspect the round.
- What we can do better:
  - Show structured facts, missing data, and confidence before the narrative.
- Evidence assets:
  - Live inspected through iPhone Mirroring; screenshots omitted for privacy.

### GolfLive Score Distribution

- Product: GolfLive WeChat mini program
- Entry path: `历史` -> `成绩分布图`.
- Main purpose: Show long-term score distribution.
- Core metrics:
  - Score bands such as par/birdie-like and bogey ranges
  - Counts and percentages
  - Histogram by score range
  - Latest differential-like value
  - Historical best
- Main interactions:
  - Mostly read-only.
- Information hierarchy:
  - First viewport: pyramid distribution, histogram, summary values.
- Strengths:
  - The pyramid is easy to interpret.
  - Histogram gives distribution shape.
- Weaknesses:
  - No direct drill-down from a band to rounds was visible.
- What we should borrow:
  - Pyramid plus histogram for scoring distribution.
- What we can do better:
  - Let users click a score band and see exact rounds/holes causing that band.
- Evidence assets:
  - Live inspected through iPhone Mirroring; screenshots omitted for privacy.

### GolfLive Annual Summary

- Product: GolfLive WeChat mini program
- Entry path: `历史` -> `年度汇总`.
- Main purpose: Summarize performance by quarter.
- Core metrics:
  - Quarter
  - Round count
  - Average score
  - Best score
  - Worst score
  - Birdies
  - Eagles
  - Doubles
- Main interactions:
  - Scroll quarterly cards.
- Information hierarchy:
  - Cards ordered from newest quarter backward.
- Strengths:
  - Very compact and useful.
  - Includes scoring-event counts, not only averages.
- Weaknesses:
  - No trend chart or reasons for changes visible.
- What we should borrow:
  - Quarter cards with average/best/worst and scoring event counts.
- What we can do better:
  - Add trend explanation and data quality.
- Evidence assets:
  - Live inspected through iPhone Mirroring; screenshots omitted for privacy.

### GolfLive Play Record Timeline

- Product: GolfLive WeChat mini program
- Entry path: `历史` -> `打球记录`.
- Main purpose: Browse play records chronologically.
- Core metrics:
  - Month grouping
  - Date/time
  - Participants
  - Player scores
  - Course
  - Ended status
- Main interactions:
  - Filter by `所有比赛`
  - Filter by year/month
  - Tap record menu
- Information hierarchy:
  - Timeline grouped by month, cards per event.
- Strengths:
  - Timeline structure is clearer than a plain list.
  - Filters are directly visible.
- Weaknesses:
  - Not clearly separated between personal practice rounds and group competitions.
- What we should borrow:
  - Month-grouped timeline and time filters.
- What we can do better:
  - Support personal, Garmin imported, manual, tournament, and practice labels.
- Evidence assets:
  - Live inspected through iPhone Mirroring; screenshots omitted for privacy.

### GolfLive Course Distribution Map

- Product: GolfLive WeChat mini program
- Entry path: `历史` -> `球场分布图`.
- Main purpose: Show geographic distribution of played courses.
- Core metrics:
  - Map pins
  - Cluster/count labels
- Main interactions:
  - Pan/zoom map
  - Tap markers, not fully inspected
- Information hierarchy:
  - Full-screen map.
- Strengths:
  - Strong "where have I played" memory surface.
- Weaknesses:
  - Map alone does not explain performance.
- What we should borrow:
  - Course map in history.
- What we can do better:
  - Marker color/size by rounds, best score, average score, and data quality.
- Evidence assets:
  - Live inspected through iPhone Mirroring; screenshots omitted for privacy.

### GolfLive Friend Stats

- Product: GolfLive WeChat mini program
- Entry path: `历史` -> `球友统计`.
- Main purpose: Compare playing partners/friends.
- Core metrics:
  - WeChat nickname
  - Name
  - Count
  - Average
  - Best
  - Worst
- Main interactions:
  - Table view; row data not recorded for privacy.
- Information hierarchy:
  - Header table with friend-related columns.
- Strengths:
  - Useful for social golf and group games.
- Weaknesses:
  - Contains private social data; not central to our private AI Caddie MVP.
- What we should borrow:
  - Optional "played with" aggregation only if user wants it.
- What we can do better:
  - Keep social data out of default analysis.
- Evidence assets:
  - Live inspected through iPhone Mirroring; screenshots omitted for privacy.

## Specific Questions

### 1. History Review

Garmin Golf:

- Presents history primarily as a recent activity list.
- Round cards are optimized for fast recall: course, date, score, to-par, and per-hole color strip.
- No visible annual summary or course map in the inspected Garmin history tab.

GolfLive:

- Presents history as a module hub.
- Includes timeline, scorecard archive, recent results, score distribution, play frequency, played courses, course map, annual summary, and secondary social/competition archives.
- Annual summary and score distribution are stronger than Garmin's visible history surfaces.

Our opportunity:

- Use GolfLive's breadth but with Garmin's cleaner round cards.
- Add confidence and data coverage to every historical summary.

### 2. Statistics

Observed Garmin stats:

- Differential.
- 9-hole and 18-hole round counts.
- Best/average recent scores.
- Game-phase performance: tee shot, approach, short game, putting.
- Course-level score and tee direction stats.
- Club normal/max distances.
- Fairway, GIR, putts, penalties in scorecard detail.

Observed GolfLive stats:

- Score distribution pyramid and histogram.
- Quarterly average/best/worst.
- Birdie/eagle/double counts.
- Play frequency.
- Course count/map.
- Friend comparison table.
- Round counts.

Unknown / not visible in inspected account:

- GolfLive shot-level map/trajectory detail beyond the `打球轨迹` entry.
- GolfLive club statistics.
- Garmin strokes gained detail, if present behind pages not inspected.

### 3. Round Review

Garmin:

- Round review is scorecard plus stats.
- Good for facts, weak for explanation.

GolfLive:

- Round review is group/competition score table plus action buttons.
- AI review is attached to round detail but token-gated.

Our opportunity:

- Build a single round review that includes scorecard, shot route, hazards, lost-stroke explanation, alternative route, and data quality.

### 4. Course And Hole History

Garmin:

- Course stats are present and useful.
- Hole-specific repeated history was not clearly visible in inspected pages.

GolfLive:

- Played course list/map exists.
- Course and hole performance details were not fully visible in this pass.

Our opportunity:

- This is a major gap. Use `globalId + localHole` to build hole history, shot pattern, and route suggestions.

### 5. Club Statistics

Garmin:

- Club stats are visible and useful but basic: normal and max distance.

GolfLive:

- No club stat page observed in the inspected mini program history flow.

Our opportunity:

- Build a stronger club model: median, p10/p90, sample size, lie filtering, miss pattern, and confidence.

### 6. Actionability

Garmin:

- Some actionable stats, especially tee direction split and club distances.
- Little narrative recommendation.

GolfLive:

- AI review CTA exists, but input transparency and output quality were not inspected because generation is point-gated.

Our opportunity:

- Make actionability explicit: "what happened", "why it cost strokes", "what to do next", "what data is missing".

## Feature Matrix

| Feature | Garmin Golf | GolfLive | Our current data supports? | Should we build? | Priority | Notes |
|---|---|---|---|---|---|---|
| Recent round cards | yes | yes | yes | yes | P0 | Use Garmin-style cards plus GolfLive counts. |
| Per-hole color/score strip | yes | partial | yes | yes | P0 | We have hole scores. |
| Scorecard archive | yes | yes | yes | yes | P0 | Already partly built. |
| Expandable scorecard detail | yes | partial | yes/partial | yes | P0 | FIR/GIR/putts available for many rounds. |
| Round shot map | yes | partial/unknown | yes/partial | yes | P0 | Garmin shots available; geometry coverage partial. |
| Round AI review | no/partial | yes | yes | yes | P0 | Need fact-first brief. |
| Annual summary | unknown/not visible | yes | yes | yes | P0 | GolfLive pattern is strong. |
| Quarterly summary | unknown/not visible | yes | yes | yes | P0 | Use average/best/worst/event counts. |
| Monthly trend | unknown/not visible | partial | yes | yes | P0 | Already in history service. |
| Score distribution pyramid | no | yes | yes | yes | P0 | Good visual for history v2. |
| Score histogram | partial | yes | yes | yes | P0 | Build with score bins. |
| Play frequency | unknown/not visible | yes | yes | yes | P1 | Useful but secondary. |
| Course map | unknown/not visible | yes | yes | yes | P0 | Already WGS84 capable. |
| Played course list | yes via course stats | yes | yes | yes | P0 | Need course detail drill-down. |
| Course stats | yes | partial | yes | yes | P0 | Average/best/worst/round count. |
| Hole history | weak/unknown | unknown | yes/partial | yes | P0 | Major differentiator. |
| Tee miss direction | yes | no/unknown | partial | yes | P1 | Garmin fairway direction can support some. |
| FIR/GIR/putts | yes | unknown | partial | yes | P0 | Older data gaps must be shown. |
| Penalties | yes | unknown | partial | yes | P1 | Useful for lost-stroke explanation. |
| Club normal/max distance | yes | unknown | yes | yes | P0 | Improve with percentiles. |
| Club dispersion | no visible | unknown | partial | yes | P1 | Requires shot coordinates and club mapping. |
| Social/friend stats | no visible | yes | no/partial | optional | P2 | Not core private MVP. |
| Tournament/PK modes | no visible | yes | no | no | No | Not near-term AI Caddie focus. |
| Data quality page | no | no | yes | yes | P0 | Clear differentiator. |
| Route recommendation | no | no visible | partial | yes | P0 | Core AI Caddie value. |

## Metrics Catalog

| Metric | Garmin Golf | GolfLive | Meaning | Our Garmin data supports? | Notes |
|---|---|---|---|---|---|
| Total rounds | yes | yes | Number of rounds played | yes | Summary/detail data. |
| 9-hole rounds | yes | unknown | Short round count | yes | Need merge policy. |
| 18-hole rounds | yes | partial | Full round count | yes | Already computed. |
| Average 18-hole score | yes | yes | Scoring average | yes | Need normalize 9-hole separately. |
| Best score | yes | yes | Lowest total | yes | Course/par context needed. |
| Worst score | unknown | yes | Highest total | yes | Useful but should avoid shame UX. |
| To-par | yes | partial | Score relative to par | yes | Detail has par. |
| Differential/handicap-like value | yes | yes | Relative performance index | partial/no | Need rating/slope for real handicap. |
| Recent 10 average | yes | unknown | Current form | yes | Easy to compute. |
| Score distribution | partial | yes | Count by score range | yes | Use histogram/pyramid. |
| Birdies | implicit | yes | Holes one under par | yes | From hole score and par. |
| Eagles | implicit | yes | Holes two under par | yes | From hole score and par. |
| Pars | implicit | partial | Holes at par | yes | From hole score and par. |
| Bogeys | implicit | partial | Holes one over par | yes | From hole score and par. |
| Double+ | implicit | yes | High-cost holes | yes | From hole score and par. |
| FIR | yes | unknown | Fairway in regulation | partial | Garmin detail availability varies. |
| GIR | yes | unknown | Green in regulation | partial | Garmin detail availability varies. |
| Putts | yes | unknown | Putts per hole/round | partial | Older rounds may lack putts. |
| Penalties | yes | unknown | Penalty strokes | partial | Detail availability varies. |
| Tee direction | yes | unknown | Left/fairway/right tendency | partial | From fairway direction fields where present. |
| Shot distance | yes | unknown | Per-shot meters/yards | yes/partial | Requires shot files. |
| Club normal distance | yes | unknown | Typical club distance | yes | Better as median. |
| Club max distance | yes | unknown | Longest observed shot | yes | Should not drive recommendations. |
| Club sample count | hidden/partial | unknown | Number of valid shots | yes | Important confidence signal. |
| Club dispersion | no visible | unknown | Left/right/short/long spread | partial | Need reliable start/end and target line. |
| Course rounds | yes | yes | Rounds per course | yes | Need canonical course merge. |
| Course average | yes | partial | Average score on course | yes | Already supportable. |
| Course best/worst | partial | partial | Best/worst at course | yes | Useful for course detail. |
| Hole average | unknown | unknown | Average score on same hole | yes/partial | Needs `globalId + localHole`. |
| Hole shot pattern | unknown | unknown | Repeated shot landing pattern | partial | Needs shots and geometry. |
| Hazard proximity | no visible | no visible | Distance/relationship to hazards | partial | Core prodgeometry feature. |
| Data quality | no | no | Missing/weak data status | yes | Should be P0. |

## UX Patterns

- Navigation model:
  - Garmin: bottom tabs with activity/stat/profile/settings; statistics are grouped into large cards.
  - GolfLive: bottom tabs plus a separate history hub with many modules.
- First-screen emphasis:
  - Garmin activity: recent rounds.
  - Garmin stats: differential and game phase.
  - GolfLive home: mostly non-history modules, with `历史` as a bottom tab.
  - GolfLive history: module list with counts.
- Dashboard card usage:
  - Garmin uses large white rounded cards with high information density.
  - GolfLive uses list rows for modules, cards for scorecards/timelines, and bright icons.
- Chart types:
  - Garmin: comparison bars, direction fan, score range line, simple tables.
  - GolfLive: pyramid, histogram, quarterly cards, map markers.
- Table/list structures:
  - Garmin scorecard table expands to detail rows.
  - GolfLive group scorecard uses player rows and hole columns.
- Map usage:
  - Garmin course stats uses hole image/shot illustration.
  - GolfLive course distribution uses a geographic map.
- Drill-down path:
  - Garmin: round -> scorecard/shot map; stats -> course/club.
  - GolfLive: history hub -> module -> list/map/summary -> round detail.
- Filter patterns:
  - GolfLive play records expose all competitions and year/month filters.
  - Garmin visible pages rely more on selection lists.
- Mix of data and narrative:
  - Garmin: data-heavy, little narrative.
  - GolfLive: data plus AI review CTA, but generated narrative not inspected.

## Opportunities For Our AI Caddie

1. Build a single history hub that combines Garmin's clean data cards and GolfLive's module breadth.
2. Make every statistic drill down to concrete rounds, holes, and shots.
3. Add data quality to the UI, not only logs.
4. Add hole history based on actual Garmin course IDs, not only course names.
5. Link course geometry and hazards to shot outcome.
6. Use the club model for decisions, not only static display.
7. Explain round quality with evidence: "lost strokes came from tee miss on holes X/Y, three-putt on Z, and bunker recovery on A."
8. Generate AI narrative only from structured facts.
9. Provide route alternatives with risk/carry/layup distances.
10. Keep social/tournament features out of MVP; only preserve optional context when it helps identify a round.

## Proposed History Review v2

### 1. Overview

- Goal: Give one-screen status of golf history, recent form, data coverage, and next review target.
- Core metrics: rounds, 18-hole average, recent 10 average, best score, most played course, shot coverage, geometry coverage.
- Charts/lists: recent round cards, score trend, score distribution mini chart, data quality chips.
- Drill-down: round, trend, course, data quality.
- Required data: scorecard summary/detail, shots optional, geometry coverage metadata.

### 2. Annual Review

- Goal: Summarize yearly and quarterly progress.
- Core metrics: rounds, courses, average, best/worst, birdies/pars/bogeys/double+, putts when available.
- Charts/lists: quarterly cards, month trend, event count distribution.
- Drill-down: quarter -> rounds; scoring event -> holes.
- Required data: hole scores/par, dates, course names, putts optional.

### 3. Timeline

- Goal: Chronological archive for finding rounds.
- Core metrics: date, course, score, to-par, tee/course segment, shot availability, report availability.
- Charts/lists: month-grouped timeline, Garmin-style cards.
- Drill-down: round review.
- Required data: scorecard summary/detail.

### 4. Round Review

- Goal: Explain one completed round.
- Core metrics: score, to-par, hole deltas, putts, penalties, FIR/GIR, shot count, high-cost holes.
- Charts/lists: scorecard, hole issue tags, shot route map, report brief.
- Drill-down: hole review, shot details.
- Required data: scorecard detail, shots, club mapping, geometry when available.

### 5. Course Review

- Goal: Show repeated course performance and recurring risks.
- Core metrics: rounds, average, best/worst, recent form, score distribution, common miss type.
- Charts/lists: course cards, map, trend, hole ranking.
- Drill-down: hole review, rounds at course.
- Required data: canonical course mapping, scorecards, shots optional.

### 6. Hole Review

- Goal: Turn history into strategy for a specific hole.
- Core metrics: average score, score distribution, common landing zones, hazard proximity, best/worst routes.
- Charts/lists: shot overlay, hole score histogram, route comparison.
- Drill-down: individual historical shots/rounds.
- Required data: `globalId + localHole`, shots, prodgeometry/raster, scorecard holes.

### 7. Club Stats

- Goal: Build trustworthy personal club distances.
- Core metrics: median, p10/p90, max, sample count, lie filter, miss pattern, confidence.
- Charts/lists: club table, distribution chart, outlier list.
- Drill-down: club -> shots.
- Required data: shot club IDs, `clubs.json`, WGS84 start/end or Garmin distance.

### 8. Shot Map

- Goal: Show actual route and alternatives on course context.
- Core metrics: shot distance, remain distance, lie, hazard proximity, carry/layup distances.
- Charts/lists: Garmin raster, satellite, prodgeometry tabs; labels for distances and putts.
- Drill-down: shot -> raw data/confidence.
- Required data: shots, Garmin raster pixel data when available, WGS84, geometry.

### 9. Data Quality

- Goal: Prevent false certainty.
- Core metrics: missing shots, missing putts, missing geometry, weak club sample, weak raster fit, report missing.
- Charts/lists: issue table by round/course/hole, sync actions.
- Drill-down: issue -> round/hole.
- Required data: local file inventory, scorecard/shots/geometry/report status.

## Implementation Implications

For the current AI Caddie Web:

1. Add a History v2 overview that mirrors GolfLive's module hub but uses tighter cards.
2. Add Garmin-style recent round cards with per-hole strips.
3. Add GolfLive-style annual/quarterly summary cards.
4. Add score distribution pyramid/histogram.
5. Upgrade course map markers with count, average, best, and geometry coverage.
6. Add hole history as a first-class page.
7. Add club model confidence and percentile distribution.
8. Place AI report generation/review directly on round detail, but show facts and confidence first.
9. Keep a data-quality page visible from the history hub.
10. Do not prioritize tournament/PK/social features for the private MVP.
