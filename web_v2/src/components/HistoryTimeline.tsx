import type { HistoryRoundsResponse, MonthRoundGroup, RoundsFilters } from '../types'
import { ProductNav, type ProductPage } from './ProductNav'
import { RoundCard } from './RoundCard'

interface HistoryTimelineProps {
  data: HistoryRoundsResponse
  filters?: RoundsFilters
  onFilterChange?: (filters: RoundsFilters) => void
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

export function HistoryTimeline({ data, filters, onFilterChange, onNavigate, onSelectRef, onOpenRoundDetail }: HistoryTimelineProps) {
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

      {onFilterChange ? (
        <section className="panel timeline-filters" aria-label="Timeline filters">
          <label>
            Year
            <select
              value={filters?.year ?? ''}
              onChange={(event) => onFilterChange({ ...filters, year: event.target.value || undefined })}
            >
              <option value="">All years</option>
              {(data.availableYears ?? []).map((year) => (
                <option key={year} value={year}>{year}</option>
              ))}
            </select>
          </label>
          <label>
            Course
            <select
              value={filters?.course ?? ''}
              onChange={(event) => onFilterChange({ ...filters, course: event.target.value || undefined })}
            >
              <option value="">All courses</option>
              {(data.availableCourses ?? []).map((course) => (
                <option key={course.key} value={course.key}>{course.label}</option>
              ))}
            </select>
          </label>
          <label className="filter-toggle">
            <input
              type="checkbox"
              checked={filters?.hasShots ?? false}
              onChange={(event) => onFilterChange({ ...filters, hasShots: event.target.checked || undefined })}
            />
            Has shots
          </label>
          <label className="filter-toggle">
            <input
              type="checkbox"
              checked={filters?.hasReport ?? false}
              onChange={(event) => onFilterChange({ ...filters, hasReport: event.target.checked || undefined })}
            />
            Has report
          </label>
        </section>
      ) : null}

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
