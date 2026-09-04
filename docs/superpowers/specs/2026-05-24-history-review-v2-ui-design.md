# History Review v2 UI Design

> **2026-07-16 AUTHORITY CORRECTION — HISTORICAL DESIGN：**§Open Questions 不再生成当前 Owner 队列：产品名已锁为 AI Caddie，原生 iOS 已成为正式产品面；score strip 细节与 AI 叙述密度由原型和最终规格审批处理。当前全仓分类见[Owner-gate 审计](../../reviews/2026-07-16-repository-wide-owner-gate-authority-and-drift-audit.md)。

## Goal

Design the next AI Caddie history experience around a unified Garmin Pro visual
language that can scale from Web to a future mobile app and Apple Watch.

The next implementation pass should improve the History Review experience. It
should not keep extending the old UI structure just because it exists.

## Source Inputs

- `COMPETITOR_RESEARCH.md`
- `HISTORY_REVIEW_RESEARCH_SUMMARY.md`
- `visual_companion/history_review_v2.html`
- Current Web app: `ai_caddie_web.py`
- Current services: `ai_caddie/history.py`, `ai_caddie/analysis.py`

## Selected Visual Direction

Use **Garmin Pro** as the base direction.

Rationale:

- It matches the trust and precision expected from Garmin data.
- It avoids GolfLive's mini-program module clutter.
- It supports dense stats without feeling like a generic enterprise dashboard.
- It can later support app/watch surfaces without changing the product language.

The final style should still have some golf memory and course texture, but it
should remain quiet, professional, and evidence-led.

## Visual Principles

1. **Evidence first**
   Every visual module should answer a concrete golf question. Avoid decorative
   tiles that only repeat navigation labels.

2. **Golf-native colors**
   Use golf semantics for scoring, risk, and map layers.

3. **Dense but calm**
   Show a lot of history without creating a crowded mini-program feel.

4. **Maps and score strips as identity**
   The visual identity should come from course maps, hole strips, and score
   distribution components, not from gradients or marketing hero sections.

5. **Confidence is visible**
   Data quality should appear as chips, badges, and coverage indicators across
   the product.

## Core Color Semantics

Scoring:

- Eagle or better: deep blue
- Birdie: light blue
- Par: green
- Bogey: amber
- Double+ or worse: red

Golf features:

- Fairway: medium green
- Green: brighter green
- Rough/tree: muted olive
- Bunker: sand gold
- Water: blue
- Risk/penalty: red
- Unknown/missing data: neutral gray

UI base:

- Background: warm gray-white
- Panel: white
- Text: dark green-black
- Muted text: gray-green
- Borders: soft gray

Avoid:

- Purple/blue gradients as a main theme
- Beige-heavy retro scorebook theme
- Overly bright mini-program icon colors
- Dark-mode-first design for history pages

## Core Components

### Round Card

Purpose: the main unit of memory and drill-down.

Fields:

- Course name
- Date
- Tee / course segment when available
- Score
- To-par
- Holes completed
- Per-hole score strip
- Data badges:
  - shots
  - putts
  - geometry
  - AI report
  - data gaps
- Optional issue tag:
  - tee miss
  - putting
  - penalty
  - missing shots
  - low confidence

Interaction:

- Click opens Round Review.
- Score strip hover/click opens hole context when available.

### Score Strip

Purpose: fast visual read of a round.

Rules:

- Use 18 fixed cells for 18-hole rounds.
- Use 9 fixed cells for 9-hole rounds.
- Color by score relative to par.
- Keep text inside cells short: score or relative symbol.
- Shape can encode under-par:
  - eagle/birdie cells can be rounded/pill-shaped
  - par/bogey/double remain rectangular

### Score Distribution

Purpose: long-term scoring identity.

Layout:

- Left: pyramid/bands
  - 70s
  - 80s
  - 90s
  - 100+
- Right: histogram by 5-stroke bucket
- Bottom: clicked band round list

Colors:

- 70s: deep blue
- 80s: light blue
- 90s: amber
- 100+: red

### Annual / Quarterly Card

Purpose: GolfLive-style long-term summary with more polish and evidence.

Fields:

- Period
- Rounds
- Courses
- Average
- Recent trend
- Best
- Worst
- Birdie / par / bogey / double+ counts
- Data coverage chips

Interaction:

- Click period to filter timeline and distribution.

### Course Map Panel

Purpose: memory surface for where the user has played.

Rules:

- Use real WGS84 map tiles or a generated map from course coordinates.
- Marker size = round count.
- Marker color = selected metric:
  - default: average score band
  - optional: geometry coverage
  - optional: recent form
- Clicking a marker opens Course Review.

### Hole Review Panel

Purpose: primary differentiator against Garmin and GolfLive.

Layout:

- Header: course, globalId/localHole, sample size, average score, confidence.
- Main visual: tabs for satellite, Garmin raster, prodgeometry geometry.
- Side facts:
  - score distribution
  - common miss/risk
  - best/worst route examples
  - caddie decision when confidence is enough

### Data Quality Chip

Purpose: prevent false confidence.

States:

- Good: available and enough samples
- Partial: available but incomplete
- Missing: absent

Examples:

- `shots 92%`
- `putts partial`
- `geometry 12/18`
- `club sample low`
- `report missing`

### Decision Card

Purpose: bridge history to caddie behavior.

Rules:

- Present only when enough facts exist.
- Keep it compact in History pages.
- Full Decision experience can live in Caddie/Hole Review later.

Fields:

- Selected route
- Recommended club / carry
- Avoid zones
- Evidence
- Confidence
- Outcome audit when round data exists

## Pages

### 1. History Overview

First screen:

- Key metrics:
  - total rounds
  - 18H average
  - recent 10 average
  - best score
  - courses played
  - shot count
- Recent round cards
- Score trend mini chart
- Data health chips
- Module entry row:
  - Timeline
  - Annual
  - Distribution
  - Courses
  - Holes
  - Clubs
  - Data Quality

Design note:

- Module entry row should not look like a GolfLive icon list. Use compact
  metric-backed tiles, not decorative buttons.

### 2. Timeline

Layout:

- Sticky filters:
  - year
  - course
  - has shots
  - has report
  - holes completed
- Month-grouped round cards.

Round cards should use the shared Round Card component.

### 3. Annual Review

Layout:

- Year selector
- Year summary strip
- Quarterly cards
- Monthly trend
- Scoring event distribution
- Period drill-down to rounds.

### 4. Score Distribution

Layout:

- Pyramid bands
- Histogram
- Summary metrics
- Clicked band round list

### 5. Round Review

Layout:

- Header summary
- Scorecard with expandable rows
- Hole issue tags
- Shot/geometry map when available
- Decision audit summary when available
- AI report facts and narrative
- Round data quality

### 6. Course Review

Layout:

- Course map/list hub
- Course detail page:
  - rounds
  - average
  - best/worst
  - recent form
  - score distribution
  - hole ranking
  - geometry coverage

### 7. Hole Review

Layout:

- Hole selector by course/globalId/localHole
- Hole summary
- Historical shot overlay
- Score distribution
- Repeated miss/risk
- Decision card when confidence is enough

### 8. Club Stats

Layout:

- Club table with:
  - median
  - p10/p90
  - sample size
  - max
  - confidence
  - retired/current status
- Click club to see shots.

### 9. Data Quality

Layout:

- Coverage cards:
  - shots
  - putts
  - geometry
  - club samples
  - reports
- Issue table grouped by impact:
  - affects decisions
  - affects stats
  - affects display only
- Actions:
  - sync Garmin
  - generate reports
  - sync geometry
  - inspect round/hole

## Cross-platform Direction

### Web

Primary product surface for now.

Use:

- Dense views
- Tables where needed
- Maps
- Deep drill-down
- Rich History Review

### Mobile App

Possible future surface.

Use:

- Overview cards
- Round timeline
- Course/hole cards
- Compact stats
- Fast review

Avoid:

- Web-style wide tables
- Too many flat module buttons

### Apple Watch

Possible future companion only.

Use:

- Current hole
- Recommended club
- Aim / avoid
- Carry distance
- Confidence

Avoid:

- Historical charts
- Full scorecards
- Course maps beyond a simplified direction/risk prompt

## Implementation Strategy

Do not rewrite all UI at once.

Recommended first implementation pass:

1. Add shared helper/render functions for:
   - score color
   - score strip
   - data quality chip
   - round card
   - distribution band
2. Replace the current history overview content with History Overview v2.
3. Upgrade timeline/round list to month-grouped Round Cards.
4. Upgrade distribution view to pyramid + histogram + round drill-down.
5. Add annual/quarterly summary.

Leave these for a later pass:

- Full Course Review redesign
- Full Hole Review redesign
- Full Club Stats redesign
- Native app/watch implementation

## Open Questions

- Should the long-term product name remain `AI Caddie`, or should history have
  a separate label such as `Golf Journal`?
- Should the score strip cells show total score, relative score, or both on
  hover?
- How much AI narrative should appear on overview pages versus round detail?
- Should the first real mobile implementation be a responsive Web/PWA or native
  iOS?
