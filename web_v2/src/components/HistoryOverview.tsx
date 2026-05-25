import type { HistoryOverviewResponse } from '../types'
import { DataQualityChips } from './DataQualityChips'
import { DistributionPanel } from './DistributionPanel'
import { ProductNav, type ProductPage } from './ProductNav'
import { RoundCard } from './RoundCard'

interface HistoryOverviewProps {
  data: HistoryOverviewResponse
  onNavigate?: (page: ProductPage) => void
}

function metricValue(value: number | null) {
  return value === null ? '-' : String(value)
}

export function HistoryOverview({ data, onNavigate = () => undefined }: HistoryOverviewProps) {
  const metrics = data.metrics

  return (
    <main className="app-shell">
      <ProductNav activePage="overview" onNavigate={onNavigate} />

      <section className="overview-hero">
        <div>
          <p className="eyebrow">History Intelligence</p>
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
