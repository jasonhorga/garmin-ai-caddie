import type { HistoryRoundsResponse, MonthRoundGroup, RoundsFilters } from '../types'
import { RoundCard } from './RoundCard'

interface HistoryTimelineProps {
  data: HistoryRoundsResponse
  filters?: RoundsFilters
  onFilterChange?: (filters: RoundsFilters) => void
  onSelectRef?: (sourceRef: string) => void
  onOpenRoundDetail?: (roundRef: string) => void
}

const MONTH_ZH: Record<string, string> = {
  January: '1', February: '2', March: '3', April: '4',
  May: '5', June: '6', July: '7', August: '8',
  September: '9', October: '10', November: '11', December: '12',
}

function formatMonthLabel(label: string): string {
  const match = label.match(/^([A-Za-z]+)\s+(\d{4})$/)
  if (!match) return label
  const [, monthEn, year] = match
  const monthNum = MONTH_ZH[monthEn]
  if (!monthNum) return label
  return `${year}年${monthNum}月`
}

function metric(value: number | null) {
  return value === null ? '-' : String(value)
}

function monthSummary(group: MonthRoundGroup) {
  return `${group.count} 场`
}

export function HistoryTimeline({ data, filters, onFilterChange, onSelectRef, onOpenRoundDetail }: HistoryTimelineProps) {
  return (
    <>
      <section className="overview-hero">
        <div>
          <p className="eyebrow">球局存档</p>
          <h1>球局</h1>
          <p className="lead">按月分组的球局记录，含成绩条、得分形态与数据覆盖。</p>
        </div>
      </section>

      {onFilterChange ? (
        <section className="w4-filter-bar" aria-label="筛选条件">
          <label className="w4-filter-label">
            年份
            <select
              className="w4-filter-select"
              value={filters?.year ?? ''}
              onChange={(event) => onFilterChange({ ...filters, year: event.target.value || undefined })}
            >
              <option value="">全部年份</option>
              {(data.availableYears ?? []).map((year) => (
                <option key={year} value={year}>{year}</option>
              ))}
            </select>
          </label>
          <label className="w4-filter-label">
            球场
            <select
              className="w4-filter-select"
              value={filters?.course ?? ''}
              onChange={(event) => onFilterChange({ ...filters, course: event.target.value || undefined })}
            >
              <option value="">全部球场</option>
              {(data.availableCourses ?? []).map((course) => (
                <option key={course.key} value={course.key}>{course.label}</option>
              ))}
            </select>
          </label>
          <label className="w4-filter-check">
            <input
              type="checkbox"
              checked={filters?.hasShots ?? false}
              onChange={(event) => onFilterChange({ ...filters, hasShots: event.target.checked || undefined })}
            />
            有击球
          </label>
          <label className="w4-filter-check">
            <input
              type="checkbox"
              checked={filters?.hasReport ?? false}
              onChange={(event) => onFilterChange({ ...filters, hasReport: event.target.checked || undefined })}
            />
            有报告
          </label>
        </section>
      ) : null}

      {data.emptyState ? (
        <section className="panel empty-state">
          <h2>{data.emptyState.title}</h2>
          <p>{data.emptyState.detail}</p>
        </section>
      ) : null}

      <section className="timeline-stack" aria-label="球局时间线">
        {data.groups.map((group) => (
          <section className="timeline-month" key={group.key}>
            <div className="timeline-month-head">
              <div>
                <h2>{formatMonthLabel(group.label)}</h2>
                <p>{monthSummary(group)}</p>
              </div>
              <div className="timeline-month-stats">
                <span>均 {metric(group.average18)}</span>
                <span>最佳 {metric(group.bestScore)}</span>
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
    </>
  )
}
