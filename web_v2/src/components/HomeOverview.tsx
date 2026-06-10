import { useRef, useState, type FormEvent } from 'react'
import type {
  CourseSearchMatch,
  CourseSearchResponse,
  HistoryOverviewResponse,
  HistoryStatsResponse,
  MobileCourseOption,
  MobileCourseOptionsResponse,
  RoundCard as RoundCardType,
} from '../types'
import { issueLabel } from '../issueLabels'

interface HomeOverviewProps {
  overview: HistoryOverviewResponse
  stats: HistoryStatsResponse | null // all-window; null → 近期状态 shows loading dashes
  courseOptions: MobileCourseOptionsResponse | null
  onSearchCourses: (name: string) => Promise<CourseSearchResponse>
  onPrepCourse: (globalId: number) => void
  onOpenRoundDetail?: (roundRef: string) => void
  onNavigateHistory: () => void
  onNavigateAnalysis: () => void
}

type SearchState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ready'; matches: CourseSearchMatch[] }
  | { status: 'error'; message: string }

function asNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function asString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null
}

function asRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {}
}

function asRows(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value.filter((row): row is Record<string, unknown> => row !== null && typeof row === 'object') : []
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

function frequentCourses(courseOptions: MobileCourseOptionsResponse | null): MobileCourseOption[] {
  if (!courseOptions || !Array.isArray(courseOptions.courses)) return []
  return courseOptions.courses
    .filter(
      (course): course is MobileCourseOption =>
        course !== null &&
        typeof course === 'object' &&
        typeof course.globalId === 'number' &&
        typeof course.name === 'string',
    )
    .sort((a, b) => (asNumber(b.roundCount) ?? 0) - (asNumber(a.roundCount) ?? 0))
    .slice(0, 3)
}

function matchMeta(match: CourseSearchMatch): string {
  const holes = asNumber(match.holes)
  return [asString(match.city), holes === null ? null : `${holes}洞`].filter(Boolean).join(' · ')
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
  stats,
  courseOptions,
  onSearchCourses,
  onPrepCourse,
  onOpenRoundDetail,
  onNavigateHistory,
  onNavigateAnalysis,
}: HomeOverviewProps) {
  const [query, setQuery] = useState('')
  const [search, setSearch] = useState<SearchState>({ status: 'idle' })
  const searchSeq = useRef(0)

  async function handleSearchSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const name = query.trim()
    if (!name) return
    const seq = ++searchSeq.current
    setSearch({ status: 'loading' })
    try {
      const data = await onSearchCourses(name)
      if (searchSeq.current !== seq) return
      setSearch({ status: 'ready', matches: Array.isArray(data.matches) ? data.matches : [] })
    } catch (error: unknown) {
      if (searchSeq.current !== seq) return
      setSearch({ status: 'error', message: error instanceof Error ? error.message : '未知错误' })
    }
  }

  const recentRounds: RoundCardType[] = Array.isArray(overview.recentRounds) ? overview.recentRounds : []
  const lastRound = recentRounds[0] ?? null
  const frequents = frequentCourses(courseOptions)
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

  const summary = stats ? asRecord(stats.summary) : {}
  const handicapEstimate = asNumber(summary.handicapEstimate)
  const handicapTrend = asNumber(summary.handicapTrend)
  const recent10Average = asNumber(summary.recent10Average)
  const topIssue = stats ? asString(asRows(stats.issues)[0]?.issue) : null

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
          <h2>想备哪场?</h2>
          <p className="home-prep-sub">搜索球场,或从常打球场直接开备战。</p>
          <form className="home-search" onSubmit={(event) => void handleSearchSubmit(event)}>
            <input
              type="text"
              aria-label="搜索球场"
              placeholder="球场名,如:观澜湖"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
            <button type="submit">搜索</button>
          </form>
          {search.status === 'loading' ? <p className="home-search-state">搜索中…</p> : null}
          {search.status === 'error' ? <p className="home-search-state">搜索失败:{search.message}</p> : null}
          {search.status === 'ready' && search.matches.length === 0 ? <p className="home-search-state">没有找到球场</p> : null}
          {search.status === 'ready' && search.matches.length > 0 ? (
            <ul className="home-search-results">
              {search.matches.map((match) => (
                <li key={match.globalId}>
                  <button type="button" className="home-search-match" onClick={() => onPrepCourse(match.globalId)}>
                    <span className="home-search-match-name">{match.name}</span>
                    <span className="home-search-match-meta">{matchMeta(match)}</span>
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
          {frequents.length > 0 ? (
            <div className="home-frequent">
              <span className="home-frequent-label">常打球场</span>
              <div className="home-frequent-cards">
                {frequents.map((course) => (
                  <article key={course.globalId} className="home-course-card">
                    <b className="home-course-name">{course.name}</b>
                    <span className="home-course-meta">打过 {asNumber(course.roundCount) ?? 0} 次</span>
                    <button type="button" aria-label={`去备战 ${course.name}`} onClick={() => onPrepCourse(course.globalId)}>
                      去备战
                    </button>
                  </article>
                ))}
              </div>
            </div>
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
                {handicapEstimate === null ? '—' : formatNumber(handicapEstimate)}
                {handicapEstimate !== null && handicapTrend !== null && handicapTrend !== 0 ? (
                  <em className={handicapTrend < 0 ? 'home-delta good' : 'home-delta bad'}>
                    {handicapTrend < 0 ? '▼' : '▲'} {formatNumber(Math.abs(handicapTrend))}
                  </em>
                ) : null}
              </b>
            </div>
            <div className="home-stat">
              <span>均杆</span>
              <b>{recent10Average === null ? '—' : formatNumber(recent10Average)}</b>
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
