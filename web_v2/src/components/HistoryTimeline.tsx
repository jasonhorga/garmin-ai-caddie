import { useState } from 'react'
import type { HistoryRoundsResponse, MonthRoundGroup, RoundsFilters } from '../types'
import { cleanCourseName } from '../units'
import { RoundCard } from './RoundCard'

interface HistoryTimelineProps {
  data: HistoryRoundsResponse
  filters?: RoundsFilters
  onFilterChange?: (filters: RoundsFilters) => void
  onSelectRef?: (sourceRef: string) => void
  onOpenRoundDetail?: (roundRef: string) => void
  // First paint loads only the first page; revealing past it asks the parent to
  // pull the full archive (data.total) in the background. loadingMore reflects
  // that fetch so the button can disable + show progress.
  onLoadAll?: () => void
  loadingMore?: boolean
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

// emptyState arrives with backend English copy; map by the closed
// emptyState.kind vocabulary and keep the backend strings for unknown kinds.
const EMPTY_STATE_ZH: Record<string, { title: string; detail: string }> = {
  no_rounds: {
    title: '还没有本地球局数据',
    detail: '先在 设置·同步 里完成一次同步,球局会出现在这里。',
  },
}

function monthSummary(group: MonthRoundGroup) {
  return `${group.count} 场`
}

// 435 real rounds froze the page when every card rendered at once — show the
// first batch and append on demand. Pure display truncation; data unchanged.
const ROUNDS_BATCH = 60

function truncatedGroups(groups: MonthRoundGroup[], cap: number): MonthRoundGroup[] {
  const out: MonthRoundGroup[] = []
  let used = 0
  for (const group of groups) {
    if (used >= cap) break
    const take = Math.min(group.rounds.length, cap - used)
    out.push(take === group.rounds.length ? group : { ...group, rounds: group.rounds.slice(0, take) })
    used += take
  }
  return out
}

export function HistoryTimeline({ data, filters, onFilterChange, onSelectRef, onOpenRoundDetail, onLoadAll, loadingMore }: HistoryTimelineProps) {
  // Filter-change reset via the last-key idiom (PrepPage lastGlobalId): a new
  // filter combination must restart at the first batch, never keep an
  // expanded window from the previous result set.
  const filterKey = JSON.stringify(filters ?? {})
  const [lastFilterKey, setLastFilterKey] = useState(filterKey)
  const [visibleCount, setVisibleCount] = useState(ROUNDS_BATCH)
  if (filterKey !== lastFilterKey) {
    setLastFilterKey(filterKey)
    setVisibleCount(ROUNDS_BATCH)
  }

  const loadedRounds = data.groups.reduce((sum, group) => sum + group.rounds.length, 0)
  const serverTotal = data.total
  const visibleGroups = loadedRounds > visibleCount ? truncatedGroups(data.groups, visibleCount) : data.groups
  // Rounds still to reveal = those not yet shown client-side PLUS those not yet
  // fetched from the server (first paint loaded only the first page).
  const remainingRounds = Math.max(0, serverTotal - visibleCount)
  const hasMoreOnServer = loadedRounds < serverTotal

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
                <option key={course.key} value={course.key}>{cleanCourseName(course.label)}</option>
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
          <h2>{EMPTY_STATE_ZH[data.emptyState.kind]?.title ?? data.emptyState.title}</h2>
          <p>{EMPTY_STATE_ZH[data.emptyState.kind]?.detail ?? data.emptyState.detail}</p>
        </section>
      ) : null}

      <section className="timeline-stack" aria-label="球局时间线">
        {visibleGroups.map((group) => (
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

      {remainingRounds > 0 || loadingMore ? (
        <div className="w4-load-more">
          <button
            type="button"
            className="w4-load-more-btn"
            disabled={loadingMore}
            onClick={() => {
              const next = visibleCount + ROUNDS_BATCH
              setVisibleCount(next)
              // Crossing the fetched first page pulls the full archive in the
              // background; the already-advanced window reveals it on arrival.
              if (next > loadedRounds && hasMoreOnServer) onLoadAll?.()
            }}
          >
            {loadingMore ? '加载中…' : `加载更多(还有 ${remainingRounds} 场)`}
          </button>
        </div>
      ) : null}
    </>
  )
}
