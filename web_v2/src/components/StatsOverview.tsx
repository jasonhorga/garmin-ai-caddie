import type { HistoryStatsResponse } from '../types'
import { SourceRefs } from './SourceRefs'
import { StatsQualityChips } from './StatsQualityChips'

interface StatsOverviewProps {
  data: HistoryStatsResponse
  onSelectRef?: (sourceRef: string) => void
}

function asNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function asString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null
}

function asRows(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value.filter((row): row is Record<string, unknown> => row !== null && typeof row === 'object') : []
}

function asRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {}
}

function displayNumber(value: unknown) {
  const number = asNumber(value)
  return number === null ? '-' : String(number)
}

function displaySigned(value: unknown) {
  const number = asNumber(value)
  if (number === null) return '-'
  return number > 0 ? `+${number}` : String(number)
}

function roundLabel(value: unknown) {
  const number = asNumber(value)
  return `${number === null ? '-' : number} rounds`
}

function refsFor(row: Record<string, unknown>) {
  const refs = row.roundRefs ?? row.holeRefs ?? row.shotRefs ?? row.sourceRefs ?? row.refs ?? row.roundIds
  if (refs) return refs
  const singular = row.roundRef ?? row.holeRef ?? row.shotRef
  return singular ? [singular] : []
}

function recordScore(row: Record<string, unknown>) {
  const score = displayNumber(row.score)
  const toPar = displaySigned(row.toPar)
  return `${score} / ${toPar}`
}

function metadataCoverage(value: unknown): string | null {
  const row = asRecord(value)
  const ready = asNumber(row.ready)
  const total = asNumber(row.total)
  const pct = asNumber(row.pct)
  if (ready === null || total === null) return null
  return `coverage ${ready}/${total}${pct === null ? '' : ` ${pct}%`}`
}

function AggregateMeta({ row }: { row: Record<string, unknown> }) {
  const coverage = metadataCoverage(row.coverage)
  const confidence = asString(row.confidence)
  if (!coverage && !confidence) return null
  return (
    <span className="aggregate-meta">
      {coverage ? <span className="fact-chip muted">{coverage}</span> : null}
      {confidence ? <span className="fact-chip muted">{confidence} confidence</span> : null}
    </span>
  )
}

function nonzeroRows(value: unknown, limit: number) {
  return asRows(value)
    .filter((row) => (asNumber(row.count) ?? 0) > 0)
    .slice(0, limit)
}

function PeriodEvidence({ row, onSelectRef }: { row: Record<string, unknown>; onSelectRef?: (sourceRef: string) => void }) {
  const bands = nonzeroRows(row.scoreBands, 2)
  const histogram = nonzeroRows(row.scoreHistogram, 2)
  const outcomes = nonzeroRows(row.outcomeRows, 2)
  return (
    <span className="period-detail">
      {asNumber(row.eighteenHoleRounds) !== null ? <span className="fact-chip muted">18H {displayNumber(row.eighteenHoleRounds)}</span> : null}
      {asNumber(row.nineHoleRounds) !== null ? <span className="fact-chip muted">9H {displayNumber(row.nineHoleRounds)}</span> : null}
      {asNumber(row.median18) !== null ? <span className="fact-chip muted">median {displayNumber(row.median18)}</span> : null}
      {asNumber(row.worstScore) !== null ? <span className="fact-chip muted">worst {displayNumber(row.worstScore)}</span> : null}
      {bands.map((band) => (
        <span key={`band-${asString(band.label) ?? 'band'}`} className={`fact-chip score-${asString(band.className) ?? 'par'}`}>
          {asString(band.label) ?? 'band'} {displayNumber(band.count)}
        </span>
      ))}
      {histogram.map((bucket) => (
        <span key={`bucket-${asString(bucket.label) ?? 'bucket'}`} className="fact-chip muted">
          {asString(bucket.label) ?? 'bucket'} {displayNumber(bucket.count)}
        </span>
      ))}
      {outcomes.map((outcome) => (
        <span key={`outcome-${asString(outcome.key) ?? asString(outcome.label) ?? 'outcome'}`} className={`fact-chip score-${asString(outcome.className) ?? 'par'}`}>
          {asString(outcome.label) ?? 'Outcome'} {displayNumber(outcome.count)}
        </span>
      ))}
      <SourceRefs refs={refsFor(row)} maxVisible={4} onSelectRef={onSelectRef} />
    </span>
  )
}

function phaseFact(row: Record<string, unknown>) {
  const phase = asString(row.phase)
  if (phase === 'Approach' && asNumber(row.girPct) !== null) return `GIR ${displayNumber(row.girPct)}%`
  if (phase === 'Putting' && asNumber(row.averagePutts) !== null) return `avg putts ${displayNumber(row.averagePutts)}`
  if (phase === 'Tee' && asNumber(row.fairwaysHit) !== null) return `${displayNumber(row.fairwaysHit)} fairways`
  if (phase === 'Short Game' && asNumber(row.roughOrBunkerShots) !== null) return `${displayNumber(row.roughOrBunkerShots)} rough/bunker`
  return `${displayNumber(row.sampleCount ?? row.count ?? row.roundCount)} records`
}

function locationLabel(value: unknown): string {
  const location = asRecord(value)
  const latitude = asNumber(location.latitude)
  const longitude = asNumber(location.longitude)
  if (latitude === null || longitude === null) return '-'
  return `${latitude}, ${longitude}`
}

export function StatsOverview({ data, onSelectRef }: StatsOverviewProps) {
  const scoreBands = asRows(data.scoring.scoreBands)
  const yearRows = asRows(data.time.byYear).slice(0, 4)
  const recentMonths = asRows(data.time.byMonth).slice(0, 4)
  const recentWindows = [
    ['Recent 5', data.summary.recent5Average],
    ['Recent 10', data.summary.recent10Average],
    ['Recent 20', data.summary.recent20Average],
  ]
  const quarters = asRows(data.time.byQuarter).slice(0, 4)
  const playFrequency = asRecord(data.time.playFrequency)
  const improvement = asRecord(data.time.improvement)
  const phaseStats = asRows(data.scoring.phaseStats)
  const teeDirection = asRecord(data.scoring.teeDirection)
  const dominantTeeMiss = asString(teeDirection.dominantMiss)
  const approachMiss = asRecord(data.scoring.approachMiss)
  const dominantApproachMiss = asString(approachMiss.dominantMiss)
  const parScoring = asRows(data.scoring.byPar)
  const scoringOutcomes = asRecord(data.scoring.outcomes)
  const scoreOutcomeRows = asRows(data.scoring.outcomeRows)
  const outcomeRows = scoreOutcomeRows.length
    ? scoreOutcomeRows
    : [
        { label: 'Eagle+', count: scoringOutcomes.eagleOrBetter, className: 'eagle' },
        { label: 'Birdie', count: scoringOutcomes.birdie, className: 'birdie' },
        { label: 'Par', count: scoringOutcomes.par, className: 'par' },
        { label: 'Bogey', count: scoringOutcomes.bogey, className: 'bogey' },
        { label: 'Double+', count: scoringOutcomes.doubleOrWorse, className: 'double' },
      ]
  const courseDistribution = data.courseDistribution.slice(0, 6)
  const courseMix = data.courses.slice(0, 5)
  const records = asRecord(data.records)
  const best18 = asRecord(records.best18)
  const worst18 = asRecord(records.worst18)
  const bestNine = asRecord(records.bestNine)
  const mostPlayedCourse = asRecord(records.mostPlayedCourse)
  const longestShot = asRows(records.longestShots)[0] ?? {}
  const bestHole = asRows(records.bestHoleOutcomes)[0] ?? {}

  return (
    <section className="stats-page" aria-label="Statistics overview">
      <div className="section-head stats-head">
        <div>
          <p className="eyebrow">History Intelligence</p>
          <h1>Statistics Overview</h1>
          <p>Score shape, recent form, and source coverage from the backend stats contract.</p>
        </div>
        <span className="mode-pill">{data.dataMode} mode</span>
      </div>

      <section className="metric-grid" aria-label="Statistics summary">
        <article className="metric-card">
          <span>Total rounds</span>
          <b>{displayNumber(data.summary.totalRounds)}</b>
        </article>
        <article className="metric-card">
          <span>18H average</span>
          <b>{displayNumber(data.summary.average18)}</b>
        </article>
        <article className="metric-card">
          <span>Best score</span>
          <b>{displayNumber(data.summary.bestScore)}</b>
        </article>
        <article className="metric-card">
          <span>Shot rows</span>
          <b>{displayNumber(data.summary.shotCount)}</b>
        </article>
      </section>

      <section className="panel compact-panel" aria-label="Round format">
        <div className="section-head">
          <div>
            <h2>Round Format</h2>
            <p>18-hole, 9-hole, and merged same-day history separation.</p>
          </div>
        </div>
        <div className="mini-metric-grid">
          <article className="mini-metric">
            <span>18-hole rounds</span>
            <b>{displayNumber(data.summary.eighteenHoleRounds)}</b>
          </article>
          <article className="mini-metric">
            <span>9-hole rounds</span>
            <b>{displayNumber(data.summary.nineHoleRounds)}</b>
          </article>
          <article className="mini-metric">
            <span>Merged same-day rounds</span>
            <b>{displayNumber(data.summary.mergedRounds)}</b>
          </article>
          <article className="mini-metric">
            <span>Courses played</span>
            <b>{displayNumber(data.summary.courseCount)}</b>
          </article>
        </div>
      </section>

      <section className="panel compact-panel" aria-label="Recent form">
        <div className="section-head">
          <div>
            <h2>Recent Form</h2>
            <p>Rolling 18-hole averages for trend comparison.</p>
          </div>
        </div>
        <div className="mini-metric-grid">
          {recentWindows.map(([label, value]) => (
            <article key={String(label)} className="mini-metric">
              <span>{String(label)}</span>
              <b>{displayNumber(value)}</b>
            </article>
          ))}
          <article className="mini-metric">
            <span>Median 18</span>
            <b>{displayNumber(data.summary.median18)}</b>
          </article>
          <article className="mini-metric">
            <span>Worst 18</span>
            <b>{displayNumber(data.summary.worstScore)}</b>
          </article>
        </div>
      </section>

      {Object.keys(improvement).length ? (
        <section className="panel compact-panel" aria-label="Improvement pace">
          <div className="section-head">
            <div>
              <h2>Improvement Pace</h2>
              <p>Baseline vs recent 18-hole scoring, with per-round trend and source rounds.</p>
            </div>
            <span className={`confidence-pill ${asString(improvement.confidence) ?? 'low'}`}>
              {asString(improvement.confidence) ?? 'unknown'}
            </span>
          </div>
          <div className="mini-metric-grid">
            <article className="mini-metric">
              <span>Direction</span>
              <b>{asString(improvement.direction) ?? '-'}</b>
            </article>
            <article className="mini-metric">
              <span>Baseline</span>
              <b>{displayNumber(improvement.baselineAverage18)}</b>
            </article>
            <article className="mini-metric">
              <span>Recent</span>
              <b>{displayNumber(improvement.recentAverage18)}</b>
            </article>
            <article className="mini-metric">
              <span>Delta</span>
              <b>{displaySigned(improvement.deltaAverage18)} strokes</b>
            </article>
            <article className="mini-metric">
              <span>Trend</span>
              <b>{displaySigned(improvement.strokesPerRoundTrend)}/round</b>
            </article>
          </div>
          <div className="stat-list improvement-refs">
            <div className="stat-row">
              <span>Baseline refs</span>
              <b>{displayNumber(improvement.windowSize)} rounds</b>
              <SourceRefs refs={improvement.baselineRoundRefs} maxVisible={4} onSelectRef={onSelectRef} />
            </div>
            <div className="stat-row">
              <span>Recent refs</span>
              <b>{displayNumber(improvement.windowSize)} rounds</b>
              <SourceRefs refs={improvement.recentRoundRefs} maxVisible={4} onSelectRef={onSelectRef} />
            </div>
          </div>
        </section>
      ) : null}

      <section className="stats-grid">
        <section className="panel compact-panel" aria-label="Year summary">
          <div className="section-head">
            <div>
              <h2>Year Summary</h2>
              <p>Annual scoring trend with direct source rounds.</p>
            </div>
          </div>
          <div className="stat-list">
            {yearRows.map((year) => (
              <div key={asString(year.key) ?? asString(year.year) ?? 'unknown'} className="stat-row">
                <span>{asString(year.year) ?? asString(year.key) ?? 'Unknown'}</span>
                <b>{roundLabel(year.roundCount)}</b>
                <PeriodEvidence row={year} onSelectRef={onSelectRef} />
              </div>
            ))}
          </div>
        </section>

        <section className="panel compact-panel" aria-label="Score outcomes">
          <div className="section-head">
            <div>
              <h2>Score Outcomes</h2>
              <p>Hole-level scoring shape across the loaded history.</p>
            </div>
          </div>
          <div className="score-outcome-grid">
            {outcomeRows.map((outcome) => (
              <span key={asString(outcome.key) ?? asString(outcome.label) ?? 'outcome'} className={`score-outcome score-${asString(outcome.className) ?? 'par'}`}>
                <strong>{asString(outcome.label) ?? 'Outcome'}</strong>
                <b>{displayNumber(outcome.count)}</b>
                {asNumber(outcome.pct) !== null ? <em>{displayNumber(outcome.pct)}%</em> : null}
                <SourceRefs refs={refsFor(outcome)} maxVisible={4} onSelectRef={onSelectRef} />
              </span>
            ))}
          </div>
        </section>

        <section className="panel compact-panel" aria-label="Score bands">
          <div className="section-head">
            <div>
              <h2>Score Bands</h2>
              <p>18-hole score distribution with source round counts.</p>
            </div>
          </div>
          <div className="stat-list">
            {scoreBands.map((band) => (
              <div key={asString(band.label) ?? 'unknown'} className="stat-row">
                <span>{asString(band.label) ?? 'Unknown'}</span>
                <b>{displayNumber(band.count)}</b>
                <SourceRefs refs={band.roundRefs ?? band.roundIds} maxVisible={4} onSelectRef={onSelectRef} />
              </div>
            ))}
          </div>
        </section>

        {parScoring.length ? (
          <section className="panel compact-panel" aria-label="Par type scoring">
            <div className="section-head">
              <div>
                <h2>Par Type Scoring</h2>
                <p>Scoring cost by par type, with source hole refs.</p>
              </div>
            </div>
            <div className="stat-list">
              {parScoring.map((row) => (
                <div key={asString(row.key) ?? asString(row.label) ?? 'par-type'} className="stat-row">
                  <span>{asString(row.label) ?? 'Par type'}</span>
                  <b>avg {displaySigned(row.averageToPar)}</b>
                  <span className="record-evidence">
                    <span className="fact-chip muted">score {displayNumber(row.averageScore)}</span>
                    <span className="fact-chip muted">par+ {displayNumber(row.parOrBetterPct)}%</span>
                    <span className="fact-chip muted">bogey+ {displayNumber(row.bogeyOrWorsePct)}%</span>
                    <SourceRefs refs={refsFor(row)} maxVisible={4} onSelectRef={onSelectRef} />
                  </span>
                </div>
              ))}
            </div>
          </section>
        ) : null}

        <section className="panel compact-panel" aria-label="Recent months">
          <div className="section-head">
            <div>
              <h2>Recent Months</h2>
              <p>Monthly form from newest Garmin rounds.</p>
            </div>
          </div>
          <div className="stat-list">
            {recentMonths.map((month) => (
              <div key={asString(month.key) ?? 'unknown'} className="stat-row">
                <span>{asString(month.key) ?? 'Unknown'}</span>
                <b>avg {displayNumber(month.average18)}</b>
                <PeriodEvidence row={month} onSelectRef={onSelectRef} />
              </div>
            ))}
          </div>
        </section>

        <section className="panel compact-panel" aria-label="Quarter trend">
          <div className="section-head">
            <div>
              <h2>Quarter Trend</h2>
              <p>Quarter-level scoring shape and source rounds.</p>
            </div>
          </div>
          <div className="stat-list">
            {quarters.map((quarter) => (
              <div key={asString(quarter.key) ?? 'unknown'} className="stat-row">
                <span>{asString(quarter.key) ?? 'Unknown'}</span>
                <b>{roundLabel(quarter.roundCount)}</b>
                <PeriodEvidence row={quarter} onSelectRef={onSelectRef} />
              </div>
            ))}
          </div>
        </section>

        <section className="panel compact-panel" aria-label="Play frequency">
          <div className="section-head">
            <div>
              <h2>Play Frequency</h2>
              <p>How often history is being refreshed by real rounds.</p>
            </div>
          </div>
          <div className="stat-list">
            <div className="stat-row">
              <span>Rounds per month</span>
              <b>{displayNumber(playFrequency.roundsPerMonth)} rounds/mo</b>
              <span>{displayNumber(playFrequency.totalMonths)} months</span>
            </div>
            <div className="stat-row">
              <span>Most active</span>
              <b>{asString(asRecord(playFrequency.mostActiveMonth).key) ?? '-'}</b>
              <span>{roundLabel(asRecord(playFrequency.mostActiveMonth).roundCount)}</span>
            </div>
          </div>
        </section>

        <section className="panel compact-panel" aria-label="Phase stats">
          <div className="section-head">
            <div>
              <h2>Phase Stats</h2>
              <p>Tee, approach, short game, and putting signals.</p>
            </div>
          </div>
          <div className="stat-list">
            {phaseStats.map((phase) => (
              <div key={asString(phase.phase) ?? 'phase'} className="stat-row">
                <span>{asString(phase.phase) ?? 'Unknown'}</span>
                <b>{phaseFact(phase)}</b>
                <SourceRefs refs={refsFor(phase)} maxVisible={4} onSelectRef={onSelectRef} />
              </div>
            ))}
          </div>
        </section>

        {Object.keys(teeDirection).length ? (
          <section className="panel compact-panel" aria-label="Tee direction">
            <div className="section-head">
              <div>
                <h2>Tee Direction</h2>
                <p>Fairway hit rate and dominant tee miss, with source hole refs.</p>
              </div>
              {dominantTeeMiss ? <span className={`semantic-chip tee-${dominantTeeMiss}`}>dominant {dominantTeeMiss}</span> : null}
            </div>
            <div className="stat-list">
              <div className="stat-row">
                <span>FIR {displayNumber(teeDirection.hitPct)}%</span>
                <b>{displayNumber(teeDirection.hit)} hit</b>
                <SourceRefs refs={teeDirection.hitRefs} maxVisible={4} onSelectRef={onSelectRef} />
              </div>
              <div className="stat-row">
                <span>miss {displayNumber(teeDirection.missPct)}%</span>
                <b>{displayNumber(teeDirection.miss)} misses</b>
                <SourceRefs refs={teeDirection[`${dominantTeeMiss ?? 'miss'}Refs`] ?? teeDirection.sourceRefs} maxVisible={4} onSelectRef={onSelectRef} />
              </div>
            </div>
          </section>
        ) : null}

        {Object.keys(approachMiss).length ? (
          <section className="panel compact-panel" aria-label="Approach miss">
            <div className="section-head">
              <div>
                <h2>Approach Miss</h2>
                <p>GIR rate and dominant green miss direction, with source hole refs.</p>
              </div>
              {dominantApproachMiss ? <span className={`semantic-chip approach-${dominantApproachMiss}`}>dominant {dominantApproachMiss}</span> : null}
            </div>
            <div className="stat-list">
              <div className="stat-row">
                <span>GIR {displayNumber(approachMiss.girPct)}%</span>
                <b>{displayNumber(approachMiss.gir)} hit</b>
                <SourceRefs refs={approachMiss.girRefs} maxVisible={4} onSelectRef={onSelectRef} />
              </div>
              <div className="stat-row">
                <span>green miss {displayNumber(approachMiss.missPct)}%</span>
                <b>{displayNumber(approachMiss.missed)} misses</b>
                <SourceRefs refs={approachMiss[`${dominantApproachMiss ?? 'missed'}Refs`] ?? approachMiss.missedRefs} maxVisible={4} onSelectRef={onSelectRef} />
              </div>
            </div>
          </section>
        ) : null}

        <section className="panel compact-panel" aria-label="Course mix">
          <div className="section-head">
            <div>
              <h2>Course Mix</h2>
              <p>Course distribution fallback until map coverage is available.</p>
            </div>
          </div>
          <div className="stat-list">
            {courseMix.map((course) => (
              <div key={asString(course.courseKey) ?? asString(course.courseName) ?? 'course'} className="stat-row">
                <span>{asString(course.courseName) ?? 'Unknown course'}</span>
                <b>{roundLabel(course.roundCount)}</b>
                <SourceRefs refs={refsFor(course)} maxVisible={4} onSelectRef={onSelectRef} />
              </div>
            ))}
          </div>
        </section>

        <section className="panel compact-panel" aria-label="Course distribution map">
          <div className="section-head">
            <div>
              <h2>Course Distribution Map</h2>
              <p>Coordinate-backed course distribution, with refs ready for drill-down.</p>
            </div>
          </div>
          <div className="course-distribution-map">
            {courseDistribution.map((course) => (
              <div key={asString(course.courseKey) ?? asString(course.courseName) ?? 'course'} className="course-distribution-row">
                <span className="course-map-pin" aria-hidden="true" />
                <div>
                  <strong>{asString(course.courseName) ?? asString(course.courseKey) ?? 'Unknown course'}</strong>
                  <span>
                    {displayNumber(course.pct)}% / {roundLabel(course.roundCount)}
                  </span>
                  <em>{locationLabel(course.location)}</em>
                </div>
                <SourceRefs refs={refsFor(course)} maxVisible={4} onSelectRef={onSelectRef} />
              </div>
            ))}
          </div>
        </section>

        <section className="panel compact-panel" aria-label="Data coverage">
          <div className="section-head">
            <div>
              <h2>Data Coverage</h2>
              <p>Coverage and missing-data signals that constrain the statistics above.</p>
            </div>
          </div>
          <StatsQualityChips data={data} labels={['shots', 'putts', 'club_samples', 'annotations', 'corrections', 'reports', 'weather']} />
          <div className="stat-list">
            {data.dataQuality
              .filter((finding) => ['shots', 'putts', 'club_samples', 'annotations', 'corrections', 'reports', 'weather'].includes(asString(finding.label) ?? ''))
              .map((finding) => (
                <div key={asString(finding.label) ?? 'quality'} className="stat-row">
                  <span>{asString(finding.label) ?? 'quality'}</span>
                  <b>{asString(finding.state) ?? 'unknown'}</b>
                  <SourceRefs refs={finding.refs} maxVisible={4} onSelectRef={onSelectRef} />
                </div>
              ))}
          </div>
        </section>

        <section className="panel compact-panel" aria-label="Record book">
          <div className="section-head">
            <div>
              <h2>Record Book</h2>
              <p>Personal bests and notable source-linked rounds, holes, and shots.</p>
            </div>
          </div>
          <div className="stat-list">
            <div className="stat-row">
              <span>Best 18</span>
              <b>{recordScore(best18)}</b>
              <span className="record-evidence">
                <AggregateMeta row={best18} />
                <SourceRefs refs={refsFor(best18)} onSelectRef={onSelectRef} />
              </span>
            </div>
            <div className="stat-row">
              <span>Worst 18</span>
              <b>{recordScore(worst18)}</b>
              <span className="record-evidence">
                <AggregateMeta row={worst18} />
                <SourceRefs refs={refsFor(worst18)} onSelectRef={onSelectRef} />
              </span>
            </div>
            <div className="stat-row">
              <span>Best 9</span>
              <b>{recordScore(bestNine)}</b>
              <span className="record-evidence">
                <AggregateMeta row={bestNine} />
                <SourceRefs refs={refsFor(bestNine)} onSelectRef={onSelectRef} />
              </span>
            </div>
            <div className="stat-row">
              <span>Most played</span>
              <b>{asString(mostPlayedCourse.courseName) ?? '-'}</b>
              <span className="record-evidence">
                <AggregateMeta row={mostPlayedCourse} />
                <SourceRefs refs={refsFor(mostPlayedCourse)} onSelectRef={onSelectRef} />
              </span>
            </div>
            <div className="stat-row">
              <span>Longest shot</span>
              <b>
                {asString(longestShot.club) ?? '-'} {displayNumber(longestShot.distance)}m
              </b>
              <span className="record-evidence">
                <AggregateMeta row={longestShot} />
                <SourceRefs refs={refsFor(longestShot)} onSelectRef={onSelectRef} />
              </span>
            </div>
            <div className="stat-row">
              <span>Best hole</span>
              <b>{recordScore(bestHole)}</b>
              <span className="record-evidence">
                <AggregateMeta row={bestHole} />
                <SourceRefs refs={refsFor(bestHole)} onSelectRef={onSelectRef} />
              </span>
            </div>
          </div>
        </section>
      </section>
    </section>
  )
}
