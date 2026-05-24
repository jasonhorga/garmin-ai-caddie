import type { HistoryOverviewResponse } from '../types'
import { DataQualityChips } from './DataQualityChips'
import { DistributionPanel } from './DistributionPanel'
import { RoundCard } from './RoundCard'

const navItems = ['Overview', 'History', 'Rounds', 'Courses', 'Clubs', 'Caddie']

interface HistoryOverviewProps {
  data: HistoryOverviewResponse
}

function metricValue(value: number | null) {
  return value === null ? '-' : String(value)
}

export function HistoryOverview({ data }: HistoryOverviewProps) {
  const metrics = data.metrics

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-mark" aria-hidden="true" />
        <nav aria-label="Primary">
          {navItems.map((item) => (
            <span key={item} className={item === 'Overview' ? 'active' : undefined} aria-current={item === 'Overview' ? 'page' : undefined}>
              {item}
            </span>
          ))}
        </nav>
      </header>

      <section className="overview-hero">
        <div>
          <p className="eyebrow">AI Caddie v2</p>
          <h1>History Overview</h1>
          <p className="lead">Round memory, scoring shape, and data confidence in one Garmin Pro surface.</p>
        </div>
        <DataQualityChips badges={data.dataQuality} />
      </section>

      {data.emptyState ? (
        <section className="panel empty-state">
          <h2>{data.emptyState.title}</h2>
          <p>{data.emptyState.detail}</p>
        </section>
      ) : null}

      <section className="metric-grid" aria-label="History metrics">
        <article className="metric-card">
          <span>Total rounds</span>
          <b>{metrics.totalRounds}</b>
        </article>
        <article className="metric-card">
          <span>18H average</span>
          <b>{metricValue(metrics.average18)}</b>
        </article>
        <article className="metric-card">
          <span>Recent 10</span>
          <b>{metricValue(metrics.recent10Average)}</b>
        </article>
        <article className="metric-card">
          <span>Best score</span>
          <b>{metricValue(metrics.bestScore)}</b>
        </article>
        <article className="metric-card">
          <span>Courses</span>
          <b>{metrics.courseCount}</b>
        </article>
        <article className="metric-card">
          <span>Shot rows</span>
          <b>{metrics.shotCount}</b>
        </article>
      </section>

      <section className="content-grid">
        <section className="panel">
          <div className="section-head">
            <div>
              <h2>Recent Rounds</h2>
              <p>Newest Garmin rounds with score shape and coverage.</p>
            </div>
          </div>
          <div className="round-list">
            {data.recentRounds.length === 0 ? (
              <p className="round-empty">No recent Garmin rounds</p>
            ) : (
              data.recentRounds.map((round) => <RoundCard key={round.id} round={round} />)
            )}
          </div>
        </section>

        <DistributionPanel distribution={data.distribution} />
      </section>
    </main>
  )
}
