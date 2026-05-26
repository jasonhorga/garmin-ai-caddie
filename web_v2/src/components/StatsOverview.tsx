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
  return row.roundRefs ?? row.holeRefs ?? row.shotRefs ?? row.sourceRefs ?? row.refs ?? row.roundIds
}

function recordScore(row: Record<string, unknown>) {
  const score = displayNumber(row.score)
  const toPar = displaySigned(row.toPar)
  return `${score} / ${toPar}`
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
  const scoringOutcomes = asRecord(data.scoring.outcomes)
  const outcomeRows = [
    ['Eagle+', scoringOutcomes.eagleOrBetter, 'eagle'],
    ['Birdie', scoringOutcomes.birdie, 'birdie'],
    ['Par', scoringOutcomes.par, 'par'],
    ['Bogey', scoringOutcomes.bogey, 'bogey'],
    ['Double+', scoringOutcomes.doubleOrWorse, 'double'],
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
              <SourceRefs refs={improvement.baselineRoundRefs} onSelectRef={onSelectRef} />
            </div>
            <div className="stat-row">
              <span>Recent refs</span>
              <b>{displayNumber(improvement.windowSize)} rounds</b>
              <SourceRefs refs={improvement.recentRoundRefs} onSelectRef={onSelectRef} />
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
                <SourceRefs refs={refsFor(year)} onSelectRef={onSelectRef} />
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
            {outcomeRows.map(([label, value, className]) => (
              <span key={String(label)} className={`score-outcome score-${String(className)}`}>
                <strong>{String(label)}</strong>
                <b>{displayNumber(value)}</b>
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
                <SourceRefs refs={band.roundRefs ?? band.roundIds} onSelectRef={onSelectRef} />
              </div>
            ))}
          </div>
        </section>

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
                <SourceRefs refs={month.roundRefs ?? month.roundIds} onSelectRef={onSelectRef} />
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
                <SourceRefs refs={refsFor(quarter)} onSelectRef={onSelectRef} />
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
                <SourceRefs refs={refsFor(phase)} onSelectRef={onSelectRef} />
              </div>
            ))}
          </div>
        </section>

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
                <SourceRefs refs={refsFor(course)} onSelectRef={onSelectRef} />
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
                <SourceRefs refs={refsFor(course)} onSelectRef={onSelectRef} />
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
          <StatsQualityChips data={data} labels={['shots', 'annotations', 'corrections', 'reports', 'weather']} />
          <div className="stat-list">
            {data.dataQuality
              .filter((finding) => ['shots', 'annotations', 'corrections', 'reports', 'weather'].includes(asString(finding.label) ?? ''))
              .map((finding) => (
                <div key={asString(finding.label) ?? 'quality'} className="stat-row">
                  <span>{asString(finding.label) ?? 'quality'}</span>
                  <b>{asString(finding.state) ?? 'unknown'}</b>
                  <SourceRefs refs={finding.refs} onSelectRef={onSelectRef} />
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
              <SourceRefs refs={best18.roundRef ? [String(best18.roundRef)] : []} onSelectRef={onSelectRef} />
            </div>
            <div className="stat-row">
              <span>Worst 18</span>
              <b>{recordScore(worst18)}</b>
              <SourceRefs refs={worst18.roundRef ? [String(worst18.roundRef)] : []} onSelectRef={onSelectRef} />
            </div>
            <div className="stat-row">
              <span>Best 9</span>
              <b>{recordScore(bestNine)}</b>
              <SourceRefs refs={bestNine.roundRef ? [String(bestNine.roundRef)] : []} onSelectRef={onSelectRef} />
            </div>
            <div className="stat-row">
              <span>Most played</span>
              <b>{asString(mostPlayedCourse.courseName) ?? '-'}</b>
              <SourceRefs refs={refsFor(mostPlayedCourse)} onSelectRef={onSelectRef} />
            </div>
            <div className="stat-row">
              <span>Longest shot</span>
              <b>
                {asString(longestShot.club) ?? '-'} {displayNumber(longestShot.distance)}m
              </b>
              <SourceRefs refs={longestShot.shotRef ? [String(longestShot.shotRef)] : []} onSelectRef={onSelectRef} />
            </div>
            <div className="stat-row">
              <span>Best hole</span>
              <b>{recordScore(bestHole)}</b>
              <SourceRefs refs={bestHole.holeRef ? [String(bestHole.holeRef)] : []} onSelectRef={onSelectRef} />
            </div>
          </div>
        </section>
      </section>
    </section>
  )
}
