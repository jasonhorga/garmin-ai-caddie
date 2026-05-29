# History Review Research Summary

Date: 2026-05-24

This is the short handoff for continuing implementation on the remote server.
The full research report is `COMPETITOR_RESEARCH.md`.

## Scope Decision

Focus only on history review.

Out of scope for the next implementation pass:

- GolfLive homepage modules: `AI工具`, `球场`, `高球圈`, `我的球队`, `更多`.
- GolfLive top entries: `赛事广场`, `比赛/报名`.
- Video/feed/social product surfaces.
- Tournament/PK/team features, except as optional context already embedded in a historical round.

## Main Product Conclusion

Garmin Golf is better at clean personal golf data display.
GolfLive is better at broad history navigation and long-term summaries.

Our AI Caddie should combine:

- Garmin-style round cards and scorecard detail.
- GolfLive-style history hub, score distribution, annual/quarterly summary, course map, and timeline.
- Our own differentiators: data quality, shot geometry, hazard context, hole history, and fact-based AI review.

## Build Priorities

### P0

1. History overview page.
   - Recent round cards.
   - Round count, 18H average, recent 10 average, best score.
   - Data coverage chips: shots, putts, geometry, reports.

2. Timeline.
   - Month-grouped rounds.
   - Garmin-style per-hole color/score strip.
   - Filters: year, course, has shots, has report.

3. Annual / quarterly summary.
   - Rounds, courses, average, best, worst.
   - Birdie/par/bogey/double+ counts.
   - Putts only when available.

4. Score distribution.
   - GolfLive-style pyramid or banded distribution.
   - Histogram by score range.
   - Click band -> rounds in that band.

5. Round review.
   - Scorecard.
   - Hole issue tags.
   - Shot route map when shots exist.
   - AI report brief generated from structured facts.
   - Data quality for the round.

6. Course review.
   - Course list/map.
   - Rounds, average, best/worst, recent form.
   - Drill down to holes.

7. Hole review.
   - `globalId + localHole` aggregation.
   - Average score, score distribution, repeated shot pattern.
   - Overlay with route and hazards.
   - Route suggestions only when geometry/shot confidence is enough.

8. Data quality.
   - Missing shots.
   - Missing putts.
   - Missing geometry.
   - Weak club samples.
   - Missing reports.

### P1

1. Club model page.
   - Median, p10/p90, sample count, max, confidence.
   - Shot drill-down.

2. Tee direction / miss pattern.
   - Based on Garmin FIR/direction fields when available.

3. Play frequency.
   - Monthly/quarterly counts.
   - Useful, but not as important as score and round review.

## Do Not Build Now

- Friend comparison.
- Team/tournament/PK workflows.
- Booking/navigation/course-commerce workflows.
- Swing video AI tools.
- Social feed.

## Implementation Notes

Use existing app structure:

- Web entry: `ai_caddie_web.py`.
- History service: `ai_caddie/history.py`.
- Round/shot data access: `ai_caddie/data.py`.
- Analysis/overlay: `ai_caddie/analysis.py`.

Before pushing remote changes:

```bash
uv run python -m unittest discover -s tests -v
```

Keep WGS84 as the coordinate source. Do not mix GCJ-02 into Garmin shot or
geometry validation.
