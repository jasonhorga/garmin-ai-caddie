# Competitor Research Request For Mac Codex

## Context

We are building a private Garmin AI Caddie project.

The long-term product goal is not only a golf dashboard. It should become a
personal golf history, statistics, review, and caddie decision system based on
the user's Garmin data, shot history, club distances, course geometry, and hole
history.

We want to learn from:

- Garmin Golf app
- GolfLive WeChat mini program

The main research goal is to understand their history review, statistics,
scorecard, course, hole, club, and post-round review experiences, then identify
where our product can be better.

Please actually inspect the products on the Mac/iPhone environment if possible.
Do not rely only on public web descriptions.

## Privacy Rules

- Do not export or reveal account secrets, phone numbers, personal identifiers,
  friend names, WeChat IDs, payment information, or private contact data.
- If screenshots or recordings include sensitive information, blur or crop it.
- It is fine to record product structure, metric names, layouts, and anonymized
  examples.
- Do not attempt to bypass login, decrypt app packages, or access non-public
  data through unsupported means.

## Deliverables

Create:

```text
COMPETITOR_RESEARCH.md
research_assets/
```

`COMPETITOR_RESEARCH.md` should be the main research report.

`research_assets/` can contain screenshots, short screen recordings, or cropped
images referenced by the report. Use descriptive filenames, for example:

```text
research_assets/garmin_scorecard_list.png
research_assets/garmin_club_stats.png
research_assets/golflive_year_summary.png
research_assets/golflive_course_list.png
```

## Products To Research

### Garmin Golf App

Inspect as many of these areas as available:

- Home / dashboard
- Scorecards / history list
- Round detail
- Scorecard detail
- Hole detail
- Shot map / shot tracking map
- Club stats
- Performance stats
- Course stats
- Strokes gained, handicap, trends, or similar performance pages if present
- Annual, monthly, or trend review pages if present
- How Garmin organizes round, course, club, shot, and player statistics

### GolfLive WeChat Mini Program

Inspect as many of these areas as available:

- Home
- Score analysis
- Score distribution / pyramid
- Round timeline
- Annual summary
- Played course list
- Course detail
- Round detail
- Scorecard detail
- Hole detail, if present
- Friend/player statistics
- Team, tournament, PK, group match pages if present
- Track, map, trajectory, or video replay pages if present
- AI swing or AI analysis pages if present

## Page-Level Notes

For each page you inspect, use this format:

```markdown
### Page Name

- Product: Garmin Golf / GolfLive
- Entry path: How to reach this page
- Main purpose: What user question this page answers
- Core metrics:
  - Metric 1
  - Metric 2
- Main interactions:
  - Filters
  - Time range
  - Drill-down
  - Map/chart/list/table behavior
- Information hierarchy:
  - First viewport
  - What appears after scroll/click
- Strengths:
- Weaknesses:
- What we should borrow:
- What we can do better:
- Evidence assets:
  - `research_assets/example.png`
```

## Specific Questions To Answer

### 1. History Review

How do the products present long-term golf history?

Look for:

- Timeline
- Calendar or heatmap
- Annual review
- Monthly/quarterly trend
- Recent form
- Best/worst rounds
- Course map
- Course list
- Personal milestones
- Round archive

### 2. Statistics

Which statistics exist?

Check for:

- Average score
- Best/worst score
- Score standard deviation or stability
- Handicap or handicap trend
- Par 3 / par 4 / par 5 performance
- Birdie / par / bogey / double+ distribution
- FIR
- GIR
- Putts
- Penalties
- Driving distance
- Approach performance
- Short game
- Strokes gained
- Club distance
- Club usage
- Course performance
- Hole performance
- Friend/player comparison

### 3. Round Review

How does each product present one completed round?

Look for:

- Scorecard structure
- Hole-by-hole table
- Shot map
- Highlights
- Mistakes
- Lost-stroke explanation
- Comparison to personal average
- Comparison to course average
- Any recommended next action

### 4. Course And Hole History

How do they handle course-level and hole-level history?

Look for:

- Same course repeated rounds
- Same hole repeated performance
- Course average / best / worst
- Hole average / scoring distribution
- Hole shot pattern
- Map or satellite overlay
- Strategy or route suggestions

### 5. Club Statistics

How are club stats shown?

Look for:

- Average distance
- Longest shot
- Distribution or percentile
- Carry vs total
- Accuracy
- Miss pattern
- Club usage count
- Retired clubs or bag changes
- Whether statistics are actionable

### 6. Actionability

Do the products tell the golfer what to do next?

Look for:

- Practice suggestions
- Strategy suggestions
- Hole-specific advice
- Club recommendation
- Risk warning
- Trend-based coaching
- AI-generated review

## Feature Matrix

Create a feature matrix:

```markdown
| Feature | Garmin Golf | GolfLive | Our current data supports? | Should we build? | Priority | Notes |
|---|---|---|---|---|---|---|
| Score timeline | yes/no/partial | yes/no/partial | yes/no/partial | yes/no | P0/P1/P2 | ... |
```

Use these priority definitions:

- `P0`: Needed for History Review v2 MVP
- `P1`: Important next iteration
- `P2`: Nice to have
- `No`: Do not build for now

## Metrics Catalog

Create a metrics catalog:

```markdown
| Metric | Garmin Golf | GolfLive | Meaning | Our Garmin data supports? | Notes |
|---|---|---|---|---|---|
| Average 18-hole score | yes/no | yes/no | ... | yes/no/partial | ... |
```

Be explicit about whether our current project data can support each metric.

Our known data sources include:

- Garmin scorecard summary/detail JSON
- Garmin hole scores
- FIR/GIR/putts/penalties when available
- Garmin shot data with WGS84 lat/lon and meters
- Club IDs and local `clubs.json` overrides
- Course snapshot/course metadata
- Garmin CourseView/prodgeometry geometry when downloaded
- Locally generated hazard/mesh files

Known gaps:

- Friend names are not reliably available from Garmin data
- Some older rounds lack putts
- Some rounds lack shot data
- Geometry coverage is partial unless prodgeometry is downloaded
- Lie quality and intent labels may be incomplete

## UX Patterns

Summarize the UX patterns you observe:

- Navigation model
- First-screen emphasis
- Dashboard card usage
- Chart types
- Table/list structures
- Map usage
- Drill-down path
- Filter patterns
- Time range controls
- How they mix data and narrative

## Opportunities For Our AI Caddie

List the most important opportunities where we can exceed Garmin Golf and
GolfLive.

Focus on:

- More complete personal history review
- Better long-term statistics
- Better course/hole history
- Better shot map and geometry overlay
- Better club distance model
- Better explanation of why a round was good or bad
- Better link from statistics to caddie decisions
- Better data quality transparency

## Proposed History Review v2

Based on the research, propose our product structure for History Review v2.

Use this structure:

```markdown
## Proposed History Review v2

### 1. Overview

- Goal:
- Core metrics:
- Charts/lists:
- Drill-down:
- Required data:

### 2. Annual Review

- Goal:
- Core metrics:
- Charts/lists:
- Drill-down:
- Required data:

### 3. Timeline

- Goal:
- Core metrics:
- Charts/lists:
- Drill-down:
- Required data:

### 4. Round Review

- Goal:
- Core metrics:
- Charts/lists:
- Drill-down:
- Required data:

### 5. Course Review

- Goal:
- Core metrics:
- Charts/lists:
- Drill-down:
- Required data:

### 6. Hole Review

- Goal:
- Core metrics:
- Charts/lists:
- Drill-down:
- Required data:

### 7. Club Stats

- Goal:
- Core metrics:
- Charts/lists:
- Drill-down:
- Required data:

### 8. Shot Map

- Goal:
- Core metrics:
- Charts/lists:
- Drill-down:
- Required data:

### 9. Data Quality

- Goal:
- Core metrics:
- Charts/lists:
- Drill-down:
- Required data:
```

## Final Executive Summary

At the top of `COMPETITOR_RESEARCH.md`, include an executive summary with:

- 10-20 most important findings
- 5 things Garmin Golf does well
- 5 things GolfLive does well
- 5 things both products do poorly
- 5 things our AI Caddie should do first

## Important Tone

Be concrete. Avoid generic statements like "good UX" or "many statistics."

Prefer:

- "GolfLive's annual summary first shows total rounds, total courses, best score,
  and score distribution, then lets the user drill into monthly records."

Avoid:

- "GolfLive has a nice annual summary."

When you are unsure, mark it as:

```text
Unknown / not visible in inspected account
```

