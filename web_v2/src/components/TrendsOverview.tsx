import { useState } from 'react'
import type { HistoryStatsResponse, MobileStatsResponse, RoundCard as RoundCardType, StatsWindow } from '../types'
import { issueLabel } from '../issueLabels'

interface TrendsOverviewProps {
  // The 趋势 landing renders from the compact window-aware mobile stats (fast first paint);
  // allStats is the full window=all stats (for the "vs 全部" deltas) only when a deep tab has
  // already loaded it — null on a cold landing, in which case the deltas are simply hidden.
  stats: MobileStatsResponse
  allStats: HistoryStatsResponse | MobileStatsResponse | null
  window: StatsWindow
  onWindowChange: (w: StatsWindow) => void
  recentRounds: RoundCardType[]
  onOpenRoundDetail?: (roundRef: string) => void
}

const WINDOW_OPTIONS: Array<{ key: StatsWindow; label: string }> = [
  { key: 'all', label: '全部' },
  { key: '12m', label: '近12个月' },
  { key: 'last10', label: '近10场' },
]

// 5-bucket outcomes still drive the 帕或更好率 KPI (eagleOrBetter+birdie+par over all holes).
const OUTCOME_BUCKETS: Array<{ key: string; label: string }> = [
  { key: 'eagleOrBetter', label: '老鹰' },
  { key: 'birdie', label: '小鸟' },
  { key: 'par', label: '帕' },
  { key: 'bogey', label: '柏忌' },
  { key: 'doubleOrWorse', label: '双+' },
]

// GolfLive 成绩分析 chips: the 7-bucket par-relative distribution (splits 双柏忌/+3/+4),
// fed by scoring.outcomeDistribution. Labels follow the GolfLive vocabulary the user specified.
const SPREAD_BUCKETS: Array<{ key: string; label: string; varName: string }> = [
  { key: 'eagleOrBetter', label: '老鹰', varName: '--eagle' },
  { key: 'birdie', label: '小鸟', varName: '--green' },
  { key: 'par', label: '标准杆', varName: '--green-bright' },
  { key: 'bogey', label: '柏忌', varName: '--bogey' },
  { key: 'double', label: '双柏忌', varName: '--double' },
  { key: 'triple', label: '+3', varName: '--double' },
  { key: 'quadPlus', label: '+4', varName: '--double' },
]

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

type AnyStats = MobileStatsResponse | HistoryStatsResponse

function outcomeCounts(stats: AnyStats): { counts: Record<string, number>; total: number; parOrBetter: number | null } {
  const outcomes = asRecord(asRecord(stats.scoring).outcomes)
  const counts: Record<string, number> = {}
  let total = 0
  for (const bucket of OUTCOME_BUCKETS) {
    const count = asNumber(outcomes[bucket.key]) ?? 0
    counts[bucket.key] = count
    total += count
  }
  const parOrBetter = asNumber(outcomes.parOrBetter) ?? (total > 0 ? counts.eagleOrBetter + counts.birdie + counts.par : null)
  return { counts, total, parOrBetter }
}

function parOrBetterPct(stats: AnyStats): number | null {
  const { total, parOrBetter } = outcomeCounts(stats)
  if (total <= 0 || parOrBetter === null) return null
  return Math.round((parOrBetter / total) * 100)
}

// GolfLive 成绩分析: the 7-bucket spread (老鹰/小鸟/标准杆/柏忌/双柏忌/+3/+4) from
// scoring.outcomeDistribution. Backend supplies count+pct; we keep its order/labels.
function spreadRows(stats: AnyStats): Array<{ key: string; label: string; varName: string; count: number; pct: number }> {
  const dist = asRows(asRecord(stats.scoring).outcomeDistribution)
  const byKey = new Map(dist.map((row) => [asString(row.key), row]))
  const total = dist.reduce((sum, row) => sum + (asNumber(row.count) ?? 0), 0)
  return SPREAD_BUCKETS.map((bucket) => {
    const row = byKey.get(bucket.key)
    const count = asNumber(row?.count) ?? 0
    const pct = asNumber(row?.pct) ?? (total > 0 ? Math.round((count / total) * 100) : 0)
    return { ...bucket, count, pct }
  })
}

interface ChartPoint {
  label: string
  value: number
}

function chartPoints(
  stats: AnyStats,
  recentRounds: RoundCardType[],
  statsWindow: StatsWindow,
  series: 'score' | 'differential',
): ChartPoint[] {
  if (statsWindow === 'last10') {
    const rounds = [...recentRounds.slice(0, 10)].reverse()
    return rounds.flatMap((round) => {
      const value = series === 'score' ? asNumber(round.score) : asNumber(round.toPar)
      return value === null ? [] : [{ label: dateLabel(round.date), value }]
    })
  }
  const months = [...asRows(asRecord(stats.time).byMonth)].filter((row) => asString(row.key) !== null && row.key !== 'unknown').reverse()
  const field = series === 'score' ? 'average18' : 'averageDifferential'
  return months.flatMap((row) => {
    const value = asNumber(row[field])
    return value === null ? [] : [{ label: String(row.key), value }]
  })
}

function TrendChart({ points }: { points: ChartPoint[] }) {
  const width = 600
  const height = 168
  const pad = 14
  const values = points.map((point) => point.value)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || 1
  const x = (index: number) => (points.length === 1 ? width / 2 : pad + (index * (width - pad * 2)) / (points.length - 1))
  const y = (value: number) => height - pad - ((value - min) / span) * (height - pad * 2)
  const linePoints = points.map((point, index) => `${x(index).toFixed(1)},${y(point.value).toFixed(1)}`).join(' ')
  return (
    <svg className="trends-chart" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" role="img" aria-label="成绩走势图">
      {[0.25, 0.5, 0.75].map((ratio) => (
        <line key={ratio} className="trends-chart-grid" x1="0" y1={height * ratio} x2={width} y2={height * ratio} />
      ))}
      <polyline className="trends-chart-line" fill="none" points={linePoints} />
      {points.map((point, index) => (
        <circle key={`${point.label}-${index}`} className="trends-chart-dot" cx={x(index)} cy={y(point.value)} r={index === points.length - 1 ? 4 : 3} />
      ))}
    </svg>
  )
}

export function TrendsOverview({
  stats,
  allStats,
  window: statsWindow,
  onWindowChange,
  recentRounds,
  onOpenRoundDetail,
}: TrendsOverviewProps) {
  const [series, setSeries] = useState<'score' | 'differential'>('score')

  const summary = asRecord(stats.summary)
  const average18 = asNumber(summary.average18)
  const handicapEstimate = asNumber(summary.handicapEstimate)
  const handicapTrend = asNumber(summary.handicapTrend)
  const bestScore = asNumber(summary.bestScore)
  const worstScore = asNumber(summary.worstScore)

  const allSummary = allStats ? asRecord(allStats.summary) : null
  const allAverage18 = allSummary ? asNumber(allSummary.average18) : null
  const allBestScore = allSummary ? asNumber(allSummary.bestScore) : null
  const allWorstScore = allSummary ? asNumber(allSummary.worstScore) : null
  const allHandicapEstimate = allSummary ? asNumber(allSummary.handicapEstimate) : null
  // Short windows (e.g. last10) often have <5 differential-bearing rounds and no
  // windowed estimate; fall back to the all-window value rather than showing —.
  // The trend sub stays gated on the windowed estimate so no meaningless delta renders.
  const displayHandicapEstimate = handicapEstimate ?? allHandicapEstimate
  const showDeltas = statsWindow !== 'all' && allStats !== null

  const averageDelta = showDeltas && average18 !== null && allAverage18 !== null ? Number((average18 - allAverage18).toFixed(1)) : null
  const windowPct = parOrBetterPct(stats)
  const allPct = allStats ? parOrBetterPct(allStats) : null
  const pctDelta = showDeltas && windowPct !== null && allPct !== null ? windowPct - allPct : null

  const spread = spreadRows(stats)
  const spreadTotal = spread.reduce((sum, bucket) => sum + bucket.count, 0)
  // The compact mobile payload has no issues[] table; its single top issue lives on diagnosis.
  const topIssue = asString(asRecord(stats.diagnosis).topIssue)
  const points = chartPoints(stats, recentRounds, statsWindow, series)
  const rows = recentRounds.slice(0, 10)
  const windowLabel = WINDOW_OPTIONS.find((option) => option.key === statsWindow)?.label ?? '全部'

  return (
    <section className="trends-page" aria-label="趋势总览">
      <div className="trends-range-row">
        <span className="trends-range-label">范围</span>
        <div className="trends-seg" role="group" aria-label="统计范围">
          {WINDOW_OPTIONS.map((option) => (
            <button
              key={option.key}
              type="button"
              aria-pressed={option.key === statsWindow}
              className={option.key === statsWindow ? 'active' : undefined}
              onClick={() => onWindowChange(option.key)}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      <section className="trends-kpis" aria-label="窗口指标">
        <article className="trends-kpi">
          <span className="trends-kpi-label">均杆(18洞)</span>
          <b className="trends-kpi-value">{average18 === null ? '—' : formatNumber(average18)}</b>
          {averageDelta !== null && allAverage18 !== null ? (
            <span className="trends-kpi-sub">
              {averageDelta !== 0 ? (
                <em className={averageDelta < 0 ? 'trends-delta good' : 'trends-delta bad'}>
                  {averageDelta < 0 ? '▼' : '▲'} {formatNumber(Math.abs(averageDelta))}
                </em>
              ) : null}{' '}
              vs 全部({formatNumber(allAverage18)})
            </span>
          ) : null}
        </article>
        <article className="trends-kpi">
          <span className="trends-kpi-label">差点(估算)</span>
          <b className="trends-kpi-value">{displayHandicapEstimate === null ? '—' : formatNumber(displayHandicapEstimate)}</b>
          {handicapEstimate !== null && handicapTrend !== null && handicapTrend !== 0 ? (
            <span className="trends-kpi-sub">
              <em className={handicapTrend < 0 ? 'trends-delta good' : 'trends-delta bad'}>
                {handicapTrend < 0 ? '▼' : '▲'} {formatNumber(Math.abs(handicapTrend))}
              </em>{' '}
              {handicapTrend < 0 ? '近期改善' : '近期上升'}
            </span>
          ) : null}
        </article>
        <article className="trends-kpi">
          <span className="trends-kpi-label">得分区间</span>
          <b className="trends-kpi-value">{bestScore !== null && worstScore !== null ? `${bestScore}–${worstScore}` : '—'}</b>
          {showDeltas && allBestScore !== null && allWorstScore !== null ? (
            <span className="trends-kpi-sub">vs 全部({allBestScore}–{allWorstScore})</span>
          ) : null}
        </article>
        <article className="trends-kpi">
          <span className="trends-kpi-label">帕或更好率</span>
          <b className="trends-kpi-value">{windowPct === null ? '—' : `${windowPct}%`}</b>
          {pctDelta !== null ? (
            <span className="trends-kpi-sub">
              {pctDelta !== 0 ? (
                <em className={pctDelta > 0 ? 'trends-delta good' : 'trends-delta bad'}>
                  {pctDelta > 0 ? '▲' : '▼'} {Math.abs(pctDelta)}%
                </em>
              ) : null}{' '}
              vs 全部
            </span>
          ) : null}
        </article>
      </section>

      <div className="trends-grid">
        <section className="panel trends-panel" aria-label="成绩走势">
          <div className="trends-panel-head">
            <div>
              <h2>成绩走势</h2>
              <span className="trends-panel-sub">
                {windowLabel}
                {statsWindow === 'last10' ? ' · 逐场' : ' · 按月'}
              </span>
            </div>
            <div className="trends-seg trends-seg--mini" role="group" aria-label="走势数据">
              <button type="button" aria-pressed={series === 'score'} className={series === 'score' ? 'active' : undefined} onClick={() => setSeries('score')}>
                杆数
              </button>
              <button
                type="button"
                aria-pressed={series === 'differential'}
                className={series === 'differential' ? 'active' : undefined}
                onClick={() => setSeries('differential')}
              >
                差点
              </button>
            </div>
          </div>
          {points.length ? (
            <>
              <TrendChart points={points} />
              <div className="trends-axis">
                <span>{points[0].label}</span>
                <span>→</span>
                <span>{points[points.length - 1].label}</span>
              </div>
            </>
          ) : (
            <p className="trends-empty">暂无走势数据</p>
          )}
        </section>

        <section className="panel trends-panel" aria-label="成绩构成">
          <div className="trends-panel-head">
            <div>
              <h2>成绩构成</h2>
              <span className="trends-panel-sub">{windowLabel} · 按洞</span>
            </div>
          </div>
          {spreadTotal > 0 ? (
            spread.map((bucket) => (
              <div key={bucket.key} className="trends-bar">
                <span className="trends-bar-label">{bucket.label}</span>
                <span className="trends-bar-track">
                  <span className="trends-bar-fill" style={{ width: `${bucket.pct}%`, background: `var(${bucket.varName})` }} />
                </span>
                <span className="trends-bar-pct">{bucket.pct}%</span>
              </div>
            ))
          ) : (
            <p className="trends-empty">暂无成绩构成数据</p>
          )}
          {topIssue ? (
            <p className="trends-callout">
              最吃杆:<strong>{issueLabel(topIssue)}</strong>
            </p>
          ) : null}
        </section>
      </div>

      <section className="panel trends-panel" aria-label="最近球局">
        <div className="trends-panel-head">
          <div>
            <h2>最近球局</h2>
            <span className="trends-panel-sub">点进去看逐洞 / 逐杆</span>
          </div>
        </div>
        {rows.length ? (
          rows.map((round) => (
            <button
              key={round.id}
              type="button"
              className="trends-round-row"
              onClick={() => onOpenRoundDetail?.(round.id)}
              aria-label={`打开 ${round.courseName} ${dateLabel(round.date)} 的逐洞详情`}
            >
              <span className="trends-round-date">{dateLabel(round.date)}</span>
              <span className="trends-round-course">{round.courseName}</span>
              <span className="trends-round-score">{round.score ?? '—'}</span>
              <span className={`trends-pchip ${toParChipClass(round.toPar)}`}>{formatToPar(round.toPar)}</span>
            </button>
          ))
        ) : (
          <p className="trends-empty">还没有球局数据</p>
        )}
      </section>
    </section>
  )
}
