import type { HistoryRoundsResponse, MonthRoundGroup } from '../types'
import { ProductNav, type ProductPage } from './ProductNav'
import { RoundCard } from './RoundCard'

interface HistoryTimelineProps {
  data: HistoryRoundsResponse
  onNavigate: (page: ProductPage) => void
  onSelectRef?: (sourceRef: string) => void
  onOpenRoundDetail?: (roundRef: string) => void
}

function metric(value: number | null) {
  return value === null ? '-' : String(value)
}

function monthSummary(group: MonthRoundGroup) {
  return `${group.count} ${group.count === 1 ? 'round' : 'rounds'}`
}

export function HistoryTimeline({ data, onNavigate, onSelectRef, onOpenRoundDetail }: HistoryTimelineProps) {
  return (
    <main className="app-shell">
      <ProductNav activePage="rounds" onNavigate={onNavigate} />

      <section className="overview-hero">
        <div>
          <p className="eyebrow">Round Archive</p>
          <h1>Rounds</h1>
          <p className="lead">Month-grouped Garmin rounds with score strips, scoring shape, and coverage context.</p>
        </div>
      </section>

      {data.emptyState ? (
        <section className="panel empty-state">
          <h2>{data.emptyState.title}</h2>
          <p>{data.emptyState.detail}</p>
        </section>
      ) : null}

      <section className="timeline-stack" aria-label="History timeline">
        {data.groups.map((group) => (
          <section className="timeline-month" key={group.key}>
            <div className="timeline-month-head">
              <div>
                <h2>{group.label}</h2>
                <p>{monthSummary(group)}</p>
              </div>
              <div className="timeline-month-stats">
                <span>avg {metric(group.average18)}</span>
                <span>best {metric(group.bestScore)}</span>
              </div>
            </div>
            <div className="round-list">
              {group.rounds.map((round) => (
                <RoundCard key={round.id} round={round} onSelectRef={onSelectRef} onOpenRoundDetail={onOpenRoundDetail} />
              ))}
            </div>
          </section>
        ))}
      </section>
    </main>
  )
}
