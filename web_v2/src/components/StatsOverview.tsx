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

function displayNumber(value: unknown) {
  const number = asNumber(value)
  return number === null ? '-' : String(number)
}

export function StatsOverview({ data, onSelectRef }: StatsOverviewProps) {
  const scoreBands = asRows(data.scoring.scoreBands)
  const recentMonths = asRows(data.time.byMonth).slice(0, 4)

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
      </section>
    </section>
  )
}
