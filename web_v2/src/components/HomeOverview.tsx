import type {
  CourseSearchResponse,
  HistoryOverviewResponse,
  HistoryStatsSummaryResponse,
  MobileCourseOptionsResponse,
  RoundCard as RoundCardType,
} from '../types'
import { issueLabel } from '../issueLabels'
import { CourseFinder } from './CourseFinder'

interface HomeOverviewProps {
  overview: HistoryOverviewResponse
  // Slim landing summary (handicap/均杆/top issue). null while loading or on
  // error → 近期状态 shows '…' (loading) or '—' (no data) per statsLoading.
  statsSummary: HistoryStatsSummaryResponse | null
  statsLoading?: boolean
  courseOptions: MobileCourseOptionsResponse | null
  onSearchCourses: (name: string) => Promise<CourseSearchResponse>
  onPrepCourse: (globalId: number, name?: string) => void
  onOpenRoundDetail?: (roundRef: string) => void
  onNavigateHistory: () => void
  onNavigateAnalysis: () => void
  onStartRecord?: () => void
}

function asNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function asString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null
}

function asRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {}
}

function formatNumber(value: number): string {
  return String(Number(value.toFixed(1)))
}

function formatToPar(value: number | null): string {
  if (value === null) return '—'
  return value > 0 ? `+${value}` : String(value)
}

function toParChipClass(value: number | null): string {
  if (value === null) return 'none'
  if (value <= 0) return 'under'
  if (value >= 18) return 'bigover'
  return 'over'
}

function dateLabel(value: string | null): string {
  return typeof value === 'string' && value.length >= 10 ? value.slice(5, 10) : '—'
}

function Sparkline({ values }: { values: number[] }) {
  const width = 220
  const height = 44
  const pad = 4
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || 1
  const x = (index: number) => pad + (index * (width - pad * 2)) / (values.length - 1)
  const y = (value: number) => height - pad - ((value - min) / span) * (height - pad * 2)
  const points = values.map((value, index) => `${x(index).toFixed(1)},${y(value).toFixed(1)}`).join(' ')
  return (
    <svg className="home-sparkline" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" role="img" aria-label="近10场杆数走势">
      <polyline fill="none" points={points} />
    </svg>
  )
}

export function HomeOverview({
  overview,
  statsSummary,
  statsLoading = false,
  courseOptions,
  onSearchCourses,
  onPrepCourse,
  onOpenRoundDetail,
  onNavigateHistory,
  onNavigateAnalysis,
  onStartRecord,
}: HomeOverviewProps) {
  const recentRounds: RoundCardType[] = Array.isArray(overview.recentRounds) ? overview.recentRounds : []
  const lastRound = recentRounds[0] ?? null
  const emptyState = overview.emptyState ?? null

  if (emptyState || overview.metrics.totalRounds === 0) {
    return (
      <section className="home-page" aria-label="概览">
        <header className="home-greeting">
          <h2>你好 👋</h2>
          <p>你的近况一眼看完</p>
        </header>
        <section className="panel home-empty-state" aria-label="暂无球局数据">
          <h2>{emptyState ? emptyState.title : '还没有球局数据'}</h2>
          <p>{emptyState ? emptyState.detail : '同步 Garmin 数据后,这里会展示你的近况。'}</p>
        </section>
      </section>
    )
  }

  const summary = statsSummary ? asRecord(statsSummary.summary) : {}
  const handicapEstimate = asNumber(summary.handicapEstimate)
  const handicapTrend = asNumber(summary.handicapTrend)
  const recent10Average = asNumber(summary.recent10Average)
  const topIssue = statsSummary ? asString(statsSummary.topIssue) : null
  // While the summary loads show '…' (not '—', which reads as a real "no data").
  const statValue = (value: number | null): string => (value !== null ? formatNumber(value) : statsLoading ? '…' : '—')

  const sparkValues = recentRounds
    .slice(0, 10)
    .flatMap((round) => {
      const score = asNumber(round.score)
      return score === null ? [] : [score]
    })
    .reverse()

  return (
    <section className="home-page" aria-label="概览">
      <header className="home-greeting">
        <h2>你好 👋</h2>
        <p>你的近况一眼看完</p>
      </header>

      <div className="home-grid">
        <section className="panel home-card home-prep" aria-label="备战入口">
          <CourseFinder courseOptions={courseOptions} onSearchCourses={onSearchCourses} onSelectCourse={onPrepCourse} />
          {onStartRecord ? (
            <button type="button" className="home-link home-record-link" onClick={onStartRecord}>
              📍 手机记分 →
            </button>
          ) : null}
        </section>

        <section className="panel home-card home-last" aria-label="上一场">
          <div className="home-card-head">
            <h2>上一场</h2>
            {lastRound ? <span className="home-card-sub">{dateLabel(lastRound.date)}</span> : null}
          </div>
          {lastRound ? (
            <>
              <div className="home-last-score">
                <b>{asNumber(lastRound.score) ?? '—'}</b>
                <span className={`home-pchip ${toParChipClass(asNumber(lastRound.toPar))}`}>{formatToPar(asNumber(lastRound.toPar))}</span>
              </div>
              <p className="home-last-course">{lastRound.courseName}</p>
              <button type="button" className="home-link" onClick={() => onOpenRoundDetail?.(lastRound.id)}>
                看复盘 →
              </button>
            </>
          ) : (
            <p className="home-empty">还没有球局</p>
          )}
        </section>

        <section className="panel home-card home-status" aria-label="近期状态">
          <div className="home-card-head">
            <h2>近期状态</h2>
            <span className="home-card-sub">近10场</span>
          </div>
          <div className="home-status-stats">
            <div className="home-stat">
              <span>差点(估算)</span>
              <b>
                {statValue(handicapEstimate)}
                {handicapEstimate !== null && handicapTrend !== null && handicapTrend !== 0 ? (
                  <em className={handicapTrend < 0 ? 'home-delta good' : 'home-delta bad'}>
                    {handicapTrend < 0 ? '▼' : '▲'} {formatNumber(Math.abs(handicapTrend))}
                  </em>
                ) : null}
              </b>
            </div>
            <div className="home-stat">
              <span>均杆</span>
              <b>{statValue(recent10Average)}</b>
            </div>
          </div>
          {sparkValues.length >= 2 ? <Sparkline values={sparkValues} /> : null}
          <button type="button" className="home-link" onClick={onNavigateHistory}>
            看历史 →
          </button>
        </section>
      </div>

      {topIssue ? (
        <section className="home-banner" aria-label="本周该练">
          <p>
            🎯 本周该练:<strong>{issueLabel(topIssue)}</strong>
          </p>
          <button type="button" onClick={onNavigateAnalysis}>
            看强弱分析 →
          </button>
        </section>
      ) : null}
    </section>
  )
}
