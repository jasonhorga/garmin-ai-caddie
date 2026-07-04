import type { HistoryStatsResponse, MobileStatsResponse, StatsWindow } from '../types'
import { phaseZh, missDirectionZh } from '../zhLabels'
import { asNumber, asRows, asString } from './statsValues'

interface StatsDashboardProps {
  // The 统计 dashboard renders from the compact window-aware mobile stats (fast first paint);
  // allStats is the full window=all stats (for the "vs 全部" KPI deltas) only when it has already
  // loaded — null on a cold landing, in which case the trend deltas are simply hidden.
  stats: MobileStatsResponse
  allStats: HistoryStatsResponse | MobileStatsResponse | null
  window: StatsWindow
  onWindowChange: (w: StatsWindow) => void
}

// Backend windows are all|12m|last10 (server_v2/main.py Query pattern) — the mockup's
// 近5场/近20场/本季 buckets don't exist server-side, so we surface the three REAL windows.
const WINDOW_OPTIONS: Array<{ key: StatsWindow; label: string }> = [
  { key: 'last10', label: '近10场' },
  { key: '12m', label: '近12个月' },
  { key: 'all', label: '全部' },
]

const WINDOW_LABEL: Record<StatsWindow, string> = {
  last10: '近10场',
  '12m': '近12个月',
  all: '全部',
}

type AnyStats = MobileStatsResponse | HistoryStatsResponse

function asRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {}
}

function summaryOf(stats: AnyStats): Record<string, unknown> {
  return asRecord(stats.summary)
}

function scoringOf(stats: AnyStats): Record<string, unknown> {
  return asRecord(stats.scoring)
}

// One-decimal, trailing-zero-trimmed (14.0 → "14", 86.4 → "86.4").
function fmt1(value: number): string {
  return String(Number(value.toFixed(1)))
}

function fmtPct(value: number): string {
  return `${Math.round(value)}%`
}

interface KpiSpec {
  key: string
  label: string
  // Rendered value string, or null → the tile shows "—" (no trend).
  value: string | null
  // Signed delta vs the all-window baseline (already oriented so >0 = improvement), or null → no arrow.
  goodDelta: number | null
  // Absolute delta text for the arrow row, e.g. "0.8" or "5%".
  deltaText: string | null
  // Which way the raw metric moved: ▲ up / ▼ down. Colour encodes good/bad; glyph encodes direction.
  rawUp: boolean
}

// A KPI value + the "vs 全部" arrow. good = improvement (green); bad = regression (orange).
function KpiTile({ spec }: { spec: KpiSpec }) {
  const good = spec.goodDelta !== null && spec.goodDelta > 0
  const showArrow = spec.goodDelta !== null && spec.goodDelta !== 0 && spec.deltaText !== null
  return (
    <article className="statsx-tile" aria-label={spec.label}>
      <div className="statsx-tile-k">{spec.label}</div>
      <div className="statsx-tile-v">{spec.value ?? '—'}</div>
      {showArrow ? (
        <div className={`statsx-tile-t ${good ? 'good' : 'bad'}`}>
          {spec.rawUp ? '▲' : '▼'} {spec.deltaText} vs 全部
        </div>
      ) : (
        <div className="statsx-tile-t muted">&nbsp;</div>
      )}
    </article>
  )
}

// Build one KPI. rawDelta = windowed − baseline. lowerBetter flips the good/bad orientation.
function buildKpi(
  key: string,
  label: string,
  windowed: number | null,
  baseline: number | null,
  {
    lowerBetter = false,
    percent = false,
    showDeltas,
  }: { lowerBetter?: boolean; percent?: boolean; showDeltas: boolean },
): KpiSpec {
  const value = windowed === null ? null : percent ? fmtPct(windowed) : fmt1(windowed)
  let goodDelta: number | null = null
  let deltaText: string | null = null
  let rawUp = false
  if (showDeltas && windowed !== null && baseline !== null) {
    const rawDelta = Number((windowed - baseline).toFixed(1))
    if (rawDelta !== 0) {
      rawUp = rawDelta > 0
      goodDelta = lowerBetter ? -rawDelta : rawDelta
      deltaText = percent ? `${Math.abs(Math.round(rawDelta))}%` : fmt1(Math.abs(rawDelta))
    }
  }
  return { key, label, value, goodDelta, deltaText, rawUp }
}

// —— 各环节失杆(估算): grouped from diagnosis.issueTrends. NOT true strokes-gained ——
interface PhaseLoss {
  phase: string
  strokes: number
}

function phaseLosses(stats: AnyStats): PhaseLoss[] {
  const trends = asRows(asRecord(stats.diagnosis).issueTrends)
  const byPhase = new Map<string, number>()
  for (const row of trends) {
    const phase = asString(row.phase)
    const lost = asNumber(row.estimatedStrokesLost)
    if (!phase || lost === null || lost <= 0) continue
    byPhase.set(phase, (byPhase.get(phase) ?? 0) + lost)
  }
  return [...byPhase.entries()]
    .map(([phase, strokes]) => ({ phase, strokes: Number(strokes.toFixed(1)) }))
    .filter((row) => row.strokes > 0)
    .sort((a, b) => b.strokes - a.strokes)
}

// —— 差点趋势 line chart ——
interface TrendPoint {
  label: string
  value: number
}

function differentialPoints(stats: AnyStats): { points: TrendPoint[]; metric: 'differential' | 'score' } {
  const months = [...asRows(asRecord(stats.time).byMonth)]
    .filter((row) => asString(row.key) !== null && row.key !== 'unknown')
    .reverse()
  const diff = months.flatMap((row) => {
    const value = asNumber(row.averageDifferential)
    return value === null ? [] : [{ label: String(row.key), value }]
  })
  if (diff.length >= 2) return { points: diff, metric: 'differential' }
  const score = months.flatMap((row) => {
    const value = asNumber(row.average18)
    return value === null ? [] : [{ label: String(row.key), value }]
  })
  return { points: score, metric: 'score' }
}

function TrendChart({ points }: { points: TrendPoint[] }) {
  const width = 640
  const height = 190
  const pad = 16
  const values = points.map((point) => point.value)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || 1
  const x = (index: number) => (points.length === 1 ? width / 2 : pad + (index * (width - pad * 2)) / (points.length - 1))
  const y = (value: number) => height - pad - ((value - min) / span) * (height - pad * 2)
  const linePoints = points.map((point, index) => `${x(index).toFixed(1)},${y(point.value).toFixed(1)}`).join(' ')
  return (
    <svg className="statsx-chart" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" role="img" aria-label="差点趋势图">
      {[0.25, 0.5, 0.75].map((ratio) => (
        <line key={ratio} className="statsx-chart-grid" x1="0" y1={height * ratio} x2={width} y2={height * ratio} />
      ))}
      <polyline className="statsx-chart-line" fill="none" points={linePoints} />
      {points.map((point, index) => (
        <circle
          key={`${point.label}-${index}`}
          className="statsx-chart-dot"
          cx={x(index)}
          cy={y(point.value)}
          r={index === points.length - 1 ? 4 : 2.5}
        />
      ))}
    </svg>
  )
}

// —— 失误倾向 (攻果岭) dispersion quadrant ——
interface Dispersion {
  shortPct: number
  longPct: number
  leftPct: number
  rightPct: number
  dominant: string | null
}

function approachDispersion(stats: AnyStats): Dispersion | null {
  const approach = asRecord(scoringOf(stats).approachMiss)
  const recorded = asNumber(approach.recorded)
  if (recorded === null || recorded <= 0) return null
  const shortPct = asNumber(approach.shortPct)
  const longPct = asNumber(approach.longPct)
  const leftPct = asNumber(approach.leftPct)
  const rightPct = asNumber(approach.rightPct)
  if (shortPct === null && longPct === null && leftPct === null && rightPct === null) return null
  return {
    shortPct: shortPct ?? 0,
    longPct: longPct ?? 0,
    leftPct: leftPct ?? 0,
    rightPct: rightPct ?? 0,
    dominant: asString(approach.dominantMiss),
  }
}

function DispersionChart({ d }: { d: Dispersion }) {
  const w = 240
  const h = 190
  const cx = w / 2
  const cy = h / 2
  // Bias offset from the aggregate direction pcts: right vs left (x), short vs long (y, short = down).
  const bx = (d.rightPct - d.leftPct) / 100
  const by = (d.shortPct - d.longPct) / 100
  const px = Math.max(28, Math.min(w - 28, cx + bx * (w / 2 - 30)))
  const py = Math.max(28, Math.min(h - 28, cy + by * (h / 2 - 30)))
  // Cloud size grows with the total recorded miss spread (bounded).
  const spread = Math.min(1, (d.shortPct + d.longPct + d.leftPct + d.rightPct) / 100)
  const rx = 34 + spread * 26
  const ry = 26 + spread * 22
  return (
    <svg className="statsx-scatter" viewBox={`0 0 ${w} ${h}`} role="img" aria-label="攻果岭失误分布图">
      <rect x="18" y="10" width={w - 36} height={h - 20} rx="8" className="statsx-scatter-bg" />
      <line x1={cx} y1="10" x2={cx} y2={h - 10} className="statsx-scatter-axis" />
      <line x1="18" y1={cy} x2={w - 18} y2={cy} className="statsx-scatter-axis" />
      <text x={cx} y="24" className="statsx-scatter-tick" textAnchor="middle">长</text>
      <text x={cx} y={h - 14} className="statsx-scatter-tick" textAnchor="middle">短</text>
      <text x="26" y={cy + 4} className="statsx-scatter-tick">左</text>
      <text x={w - 30} y={cy + 4} className="statsx-scatter-tick">右</text>
      <ellipse cx={px} cy={py} rx={rx} ry={ry} className="statsx-scatter-cloud" />
      <circle cx={px} cy={py} r="4" className="statsx-scatter-dot" />
    </svg>
  )
}

function dispersionCaption(d: Dispersion): string {
  const parts: string[] = []
  if (d.rightPct !== d.leftPct) parts.push(d.rightPct > d.leftPct ? '偏右' : '偏左')
  if (d.shortPct !== d.longPct) parts.push(d.shortPct > d.longPct ? '偏短' : '偏长')
  if (parts.length) return `攻果岭失误多${parts.join('且')}。`
  if (d.dominant) return `攻果岭主要失误:${missDirectionZh(d.dominant)}。`
  return '攻果岭失误方向较均衡。'
}

// —— 成绩构成 (4-bucket) ——
interface ScoreBucket {
  key: string
  label: string
  symbol: string
  cls: string
  count: number
}

function scoreBuckets(stats: AnyStats): { buckets: ScoreBucket[]; total: number } {
  const outcomes = asRecord(scoringOf(stats).outcomes)
  const n = (key: string) => asNumber(outcomes[key]) ?? 0
  const buckets: ScoreBucket[] = [
    { key: 'birdieOrBetter', label: '小鸟及以下', symbol: '○', cls: 'birdie', count: n('eagleOrBetter') + n('birdie') },
    { key: 'par', label: '标准杆', symbol: '', cls: 'par', count: n('par') },
    { key: 'bogey', label: '柏忌', symbol: '□', cls: 'bogey', count: n('bogey') },
    { key: 'doubleOrWorse', label: '双柏忌+', symbol: '⊡', cls: 'double', count: n('doubleOrWorse') },
  ]
  const total = buckets.reduce((sum, bucket) => sum + bucket.count, 0)
  return { buckets, total }
}

export function StatsDashboard({ stats, allStats, window: statsWindow, onWindowChange }: StatsDashboardProps) {
  const summary = summaryOf(stats)
  const scoring = scoringOf(stats)
  const allSummary = allStats ? summaryOf(allStats) : null
  const allScoring = allStats ? scoringOf(allStats) : null
  // Comparing the all-window view to itself is meaningless — deltas only when a distinct baseline exists.
  const showDeltas = statsWindow !== 'all' && allStats !== null

  const teeDirection = asRecord(scoring.teeDirection)
  const approachMiss = asRecord(scoring.approachMiss)
  const putting = asRecord(scoring.putting)
  const allTee = allScoring ? asRecord(allScoring.teeDirection) : null
  const allApproach = allScoring ? asRecord(allScoring.approachMiss) : null
  const allPutting = allScoring ? asRecord(allScoring.putting) : null

  const handicapEstimate = asNumber(summary.handicapEstimate)
  const handicapTrend = asNumber(summary.handicapTrend)
  // Short windows (e.g. last10) often lack enough differential rounds for a windowed handicap —
  // fall back to the all-window estimate so the KPI shows a number, mirroring the shipped 趋势 view.
  const displayHandicap = handicapEstimate ?? (allSummary ? asNumber(allSummary.handicapEstimate) : null)

  const handicapTile: KpiSpec = {
    key: 'handicap',
    label: '差点指数',
    value: displayHandicap === null ? null : fmt1(displayHandicap),
    // handicapTrend is a built-in recent-vs-earlier trend (negative = improving), window-independent.
    goodDelta: handicapEstimate !== null && handicapTrend !== null && handicapTrend !== 0 ? -handicapTrend : null,
    deltaText: handicapEstimate !== null && handicapTrend !== null && handicapTrend !== 0 ? fmt1(Math.abs(handicapTrend)) : null,
    rawUp: (handicapTrend ?? 0) > 0,
  }
  // The handicap arrow reads "近月" rather than "vs 全部"; rendered as a special case below.
  const kpis: KpiSpec[] = [
    handicapTile,
    buildKpi('avg', '平均杆', asNumber(summary.average18), allSummary ? asNumber(allSummary.average18) : null, {
      lowerBetter: true,
      showDeltas,
    }),
    buildKpi('gir', '标准杆上果岭', asNumber(approachMiss.girPct), allApproach ? asNumber(allApproach.girPct) : null, {
      percent: true,
      showDeltas,
    }),
    buildKpi('fir', '开球上球道', asNumber(teeDirection.hitPct), allTee ? asNumber(allTee.hitPct) : null, {
      percent: true,
      showDeltas,
    }),
    buildKpi('putts', '平均推杆', asNumber(putting.averagePuttsPerRound), allPutting ? asNumber(allPutting.averagePuttsPerRound) : null, {
      lowerBetter: true,
      showDeltas,
    }),
  ]

  const losses = phaseLosses(stats)
  const lossTotal = Number(losses.reduce((sum, row) => sum + row.strokes, 0).toFixed(1))
  const lossMax = losses.reduce((max, row) => Math.max(max, row.strokes), 0)

  const { points: trendPoints, metric: trendMetric } = differentialPoints(stats)
  const dispersion = approachDispersion(stats)
  const courses = asRows(stats.courses).slice(0, 6)
  const { buckets, total: scoreTotal } = scoreBuckets(stats)
  const windowLabel = WINDOW_LABEL[statsWindow]

  return (
    <section className="statsx" aria-label="统计仪表盘">
      <div className="statsx-toolbar">
        <span className="statsx-toolbar-label">范围</span>
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

      <div className="statsx-kpis" aria-label="核心指标">
        {kpis.map((spec) =>
          spec.key === 'handicap' ? (
            <article className="statsx-tile" aria-label={spec.label} key={spec.key}>
              <div className="statsx-tile-k">{spec.label}</div>
              <div className="statsx-tile-v">{spec.value ?? '—'}</div>
              {spec.goodDelta !== null && spec.deltaText !== null ? (
                <div className={`statsx-tile-t ${spec.goodDelta > 0 ? 'good' : 'bad'}`}>
                  {spec.rawUp ? '▲' : '▼'} {spec.deltaText} 近月
                </div>
              ) : (
                <div className="statsx-tile-t muted">&nbsp;</div>
              )}
            </article>
          ) : (
            <KpiTile spec={spec} key={spec.key} />
          ),
        )}
      </div>

      <div className="statsx-grid">
        <section className="panel statsx-panel statsx-span5" aria-label="各环节失杆">
          <h2 className="statsx-h">
            各环节失杆<small>估算 · 相对基线</small>
          </h2>
          {losses.length ? (
            <>
              {losses.map((row) => (
                <div className="statsx-sgrow" key={row.phase}>
                  <span className="statsx-sgrow-label">{phaseZh(row.phase)}</span>
                  <span className="statsx-sgrow-track">
                    <span
                      className="statsx-sgrow-fill"
                      style={{ width: `${lossMax ? Math.round((row.strokes / lossMax) * 100) : 0}%` }}
                    />
                  </span>
                  <span className="statsx-sgrow-val">−{fmt1(row.strokes)}</span>
                </div>
              ))}
              <div className="statsx-sgrow statsx-sgrow--total">
                <span className="statsx-sgrow-label">总计</span>
                <span className="statsx-sgrow-track" />
                <span className="statsx-sgrow-val">−{fmt1(lossTotal)}</span>
              </div>
              <p className="statsx-note">
                来自问题引擎的近期失杆估算(相对你的基线窗口)。逐杆基准的真·击杆优势尚未计算。
              </p>
            </>
          ) : (
            <p className="statsx-empty">数据不足:暂无各环节失杆估算(需要更多带问题标注的球局)。</p>
          )}
        </section>

        <section className="panel statsx-panel statsx-span7" aria-label="差点趋势">
          <h2 className="statsx-h">
            差点趋势<small>{windowLabel} · {trendMetric === 'differential' ? '按月差分' : '按月均杆'}</small>
          </h2>
          {trendPoints.length >= 2 ? (
            <>
              <TrendChart points={trendPoints} />
              <div className="statsx-axis">
                <span>{trendPoints[0].label}</span>
                <span>→</span>
                <span>{trendPoints[trendPoints.length - 1].label}</span>
              </div>
            </>
          ) : (
            <p className="statsx-empty">数据不足:按月趋势至少需要两个月的数据。</p>
          )}
        </section>

        <section className="panel statsx-panel statsx-span4" aria-label="失误倾向">
          <h2 className="statsx-h">
            失误倾向<small>攻果岭</small>
          </h2>
          {dispersion ? (
            <>
              <DispersionChart d={dispersion} />
              <p className="statsx-note">{dispersionCaption(dispersion)}</p>
            </>
          ) : (
            <p className="statsx-empty">数据不足:暂无攻果岭失误方向数据。</p>
          )}
        </section>

        <section className="panel statsx-panel statsx-span4" aria-label="按球场">
          <h2 className="statsx-h">按球场</h2>
          {courses.length ? (
            <table className="statsx-table">
              <thead>
                <tr>
                  <th>球场</th>
                  <th className="statsx-num">场次</th>
                  <th className="statsx-num">均杆</th>
                  <th className="statsx-num">最好</th>
                </tr>
              </thead>
              <tbody>
                {courses.map((course, index) => {
                  const average18 = asNumber(course.average18)
                  const bestScore = asNumber(course.bestScore)
                  const roundCount = asNumber(course.roundCount)
                  return (
                    <tr key={asString(course.courseKey) ?? asString(course.courseName) ?? `course-${index}`}>
                      <td>{asString(course.courseName) ?? '未知球场'}</td>
                      <td className="statsx-num">{roundCount ?? '—'}</td>
                      <td className="statsx-num">{average18 === null ? '—' : fmt1(average18)}</td>
                      <td className="statsx-num">{bestScore ?? '—'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          ) : (
            <p className="statsx-empty">数据不足:暂无按球场数据。</p>
          )}
        </section>

        <section className="panel statsx-panel statsx-span4" aria-label="成绩构成">
          <h2 className="statsx-h">
            成绩构成<small>{windowLabel} · 每洞</small>
          </h2>
          {scoreTotal > 0 ? (
            <table className="statsx-table statsx-composition">
              <tbody>
                {buckets.map((bucket) => (
                  <tr key={bucket.key}>
                    <td>
                      {bucket.symbol ? (
                        <b className={`statsx-bucket-sym statsx-bucket--${bucket.cls}`} aria-hidden="true">
                          {bucket.symbol}
                        </b>
                      ) : null}
                      {/* Label lives in its own element so its text is EXACTLY the bucket name
                          (the ○/□/⊡ symbol is a separate sibling) — [aria-label] / exact-text e2e. */}
                      <span className={`statsx-bucket statsx-bucket--${bucket.cls}`}>{bucket.label}</span>
                    </td>
                    <td className="statsx-num">{Math.round((bucket.count / scoreTotal) * 100)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="statsx-empty">数据不足:暂无成绩构成数据。</p>
          )}
        </section>
      </div>
    </section>
  )
}
