import type { HistoryStatsResponse } from '../types'
import { SourceRefs } from './SourceRefs'

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

function roundLabel(value: unknown) {
  const number = asNumber(value)
  return `${number === null ? '-' : number} rounds`
}

function refsFor(row: Record<string, unknown>) {
  return row.roundRefs ?? row.holeRefs ?? row.shotRefs ?? row.sourceRefs ?? row.refs ?? row.roundIds
}

function phaseFact(row: Record<string, unknown>) {
  const phase = asString(row.phase)
  if (phase === 'Approach' && asNumber(row.girPct) !== null) return `GIR ${displayNumber(row.girPct)}%`
  if (phase === 'Putting' && asNumber(row.averagePutts) !== null) return `avg putts ${displayNumber(row.averagePutts)}`
  if (phase === 'Tee' && asNumber(row.fairwaysHit) !== null) return `${displayNumber(row.fairwaysHit)} fairways`
  if (phase === 'Short Game' && asNumber(row.roughOrBunkerShots) !== null) return `${displayNumber(row.roughOrBunkerShots)} rough/bunker`
  return `${displayNumber(row.sampleCount ?? row.count ?? row.roundCount)} records`
}

export function StatsOverview({ data, onSelectRef }: StatsOverviewProps) {
  const scoreBands = asRows(data.scoring.scoreBands)
  const recentMonths = asRows(data.time.byMonth).slice(0, 4)
  const recentWindows = [
    ['Recent 5', data.summary.recent5Average],
    ['Recent 10', data.summary.recent10Average],
    ['Recent 20', data.summary.recent20Average],
  ]
  const quarters = asRows(data.time.byQuarter).slice(0, 4)
  const playFrequency = asRecord(data.time.playFrequency)
  const phaseStats = asRows(data.scoring.phaseStats)
  const courseMix = data.courses.slice(0, 5)

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

      <section className="stats-grid">
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
      </section>
    </section>
  )
}
