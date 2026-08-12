import { useState } from 'react'
import type { MobileStatsResponse, StatsWindow } from '../types'
import { asNumber, asRows, asString } from './statsValues'

type Granularity = 'round' | 'month' | 'quarter' | 'year'

interface TimeTrendsProps {
  stats: MobileStatsResponse
  allStats?: MobileStatsResponse | null
  window: StatsWindow
  onWindowChange: (window: StatsWindow) => void
  onOpenRound: (roundId: string) => void
  onOpenPeriod: (period: string) => void
}

const WINDOWS: Array<[StatsWindow, string]> = [
  ['last10', '近 10 场'],
  ['last20', '近 20 场'],
  ['12m', '近 12 月'],
  ['all', '全部'],
]
const GRAINS: Array<[Granularity, string]> = [['round', '逐场'], ['month', '月'], ['quarter', '季'], ['year', '年']]

function allowedGrains(window: StatsWindow): Granularity[] {
  if (window === 'last10' || window === 'last20') return ['round']
  if (window === '12m') return ['round', 'month', 'quarter']
  return ['month', 'quarter', 'year']
}

function defaultGrain(window: StatsWindow): Granularity {
  if (window === '12m') return 'month'
  if (window === 'all') return 'year'
  return 'round'
}

function fmt(value: unknown, digits = 1): string {
  const number = asNumber(value)
  return number === null ? '—' : Number(number.toFixed(digits)).toString()
}

interface ChartPoint {
  key: string
  label: string
  value: number
  roundId?: string
}

function chartSeries(stats: MobileStatsResponse, granularity: Granularity): ChartPoint[] {
  if (granularity === 'round') {
    return (stats.trend?.points ?? []).flatMap((point) =>
      point.score === null ? [] : [{ key: point.roundId ?? point.date, label: point.date.slice(0, 10), value: point.score, roundId: point.roundId ?? undefined }],
    )
  }
  const time = stats.time as Record<string, unknown>
  const key = granularity === 'month' ? 'byMonth' : granularity === 'quarter' ? 'byQuarter' : 'byYear'
  return asRows(time[key]).flatMap((row) => {
    const period = asString(row.key)
    const value = asNumber(row.average18)
    return period && value !== null && period !== 'unknown' ? [{ key: period, label: period, value }] : []
  }).reverse()
}

function TrendSvg({ points, onOpenRound, onOpenPeriod }: { points: ChartPoint[]; onOpenRound: (id: string) => void; onOpenPeriod: (key: string) => void }) {
  const width = 760
  const height = 220
  const pad = 24
  const values = points.map((point) => point.value)
  const low = Math.min(...values)
  const high = Math.max(...values)
  const span = high - low || 1
  const x = (index: number) => points.length === 1 ? width / 2 : pad + index * (width - pad * 2) / (points.length - 1)
  // SVG's y-axis grows downward. Keep the familiar numeric-chart convention:
  // a higher (worse) golf score sits above a lower (better) score, matching the
  // native Charts rendering and preventing an improvement from reading as a rise.
  const y = (value: number) => pad + (high - value) / span * (height - pad * 2)
  const line = points.map((point, index) => `${x(index)},${y(point.value)}`).join(' ')
  const open = (point: ChartPoint) => point.roundId ? onOpenRound(point.roundId) : onOpenPeriod(point.key)
  return (
    <svg className="results-trend-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="成绩时间趋势图">
      {[.25, .5, .75].map((ratio) => <line key={ratio} x1="0" x2={width} y1={height * ratio} y2={height * ratio} />)}
      <polyline points={line} />
      {points.map((point, index) => (
        <circle
          key={point.key}
          cx={x(index)} cy={y(point.value)} r="6"
          role="button" tabIndex={0}
          aria-label={`${point.label}，${point.value} 杆，打开对应球局`}
          onClick={() => open(point)}
          onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') open(point) }}
        />
      ))}
    </svg>
  )
}

function utcCalendarCells(year: number): Array<string | null> {
  const days: Array<string | null> = []
  const cursor = new Date(Date.UTC(year, 0, 1))
  // The grid flows down seven weekday rows and then starts a new week column.
  // Pad the first week so January 1 lands on its real weekday instead of always
  // appearing on the first row.
  for (let weekday = 0; weekday < cursor.getUTCDay(); weekday += 1) days.push(null)
  while (cursor.getUTCFullYear() === year) {
    days.push(cursor.toISOString().slice(0, 10))
    cursor.setUTCDate(cursor.getUTCDate() + 1)
  }
  return days
}

export function TimeTrends({ stats, allStats = null, window, onWindowChange, onOpenRound, onOpenPeriod }: TimeTrendsProps) {
  const [lastWindow, setLastWindow] = useState(window)
  const [granularity, setGranularity] = useState<Granularity>(() => defaultGrain(window))
  if (lastWindow !== window) {
    setLastWindow(window)
    setGranularity(defaultGrain(window))
  }

  const time = stats.time as Record<string, unknown>
  const summary = stats.summary
  const allowed = allowedGrains(window)
  const points = chartSeries(stats, granularity)
  const archiveTime = (allStats?.time ?? stats.time) as Record<string, unknown>
  const years = asRows(archiveTime.byYear).filter((row) => asString(row.key) !== 'unknown')
  const periodsKey = granularity === 'month' ? 'byMonth' : granularity === 'quarter' ? 'byQuarter' : granularity === 'year' ? 'byYear' : null
  const periodRows = periodsKey ? asRows(time[periodsKey]).filter((row) => asString(row.key) !== 'unknown') : []
  const dayRows = asRows(archiveTime.byDay)
  const dayCounts = new Map(dayRows.flatMap((row) => {
    const key = asString(row.key)
    return key ? [[key, asNumber(row.roundCount) ?? 0] as const] : []
  }))
  const calendarYear = Number(asString(years[0]?.key) ?? new Date().getUTCFullYear())
  const calendarDays = dayRows.filter((row) => asString(row.key)?.startsWith(`${calendarYear}-`))
  const calendarRoundCount = calendarDays.reduce((sum, row) => sum + (asNumber(row.roundCount) ?? 0), 0)
  const calendarMonthCount = new Set(calendarDays.flatMap((row) => {
    const key = asString(row.key)
    return key ? [key.slice(0, 7)] : []
  })).size
  const frequency = archiveTime.playFrequency && typeof archiveTime.playFrequency === 'object' ? archiveTime.playFrequency as Record<string, unknown> : {}
  const mostActive = frequency.mostActiveMonth && typeof frequency.mostActiveMonth === 'object' ? frequency.mostActiveMonth as Record<string, unknown> : {}

  return (
    <section className="results-trends" aria-label="时间趋势">
      <header className="results-title">
        <p className="eyebrow">范围与粒度分开</p>
        <h1>时间趋势</h1>
        <p>先决定哪些球局参加计算，再决定按逐场、月、季或年汇总；每个点都能回到对应球局。</p>
      </header>

      <section className="panel results-trend-controls">
        <label>统计范围 · 哪些球局参加计算</label>
        <div className="trends-seg" role="group" aria-label="统计范围">
          {WINDOWS.map(([key, label]) => <button key={key} type="button" aria-pressed={key === window} className={key === window ? 'active' : undefined} onClick={() => onWindowChange(key)}>{label}</button>)}
        </div>
        <label>汇总粒度 · 同一批球局怎样分组</label>
        <div className="trends-seg" role="group" aria-label="汇总粒度">
          {GRAINS.map(([key, label]) => <button key={key} type="button" disabled={!allowed.includes(key)} aria-pressed={key === granularity} className={key === granularity ? 'active' : undefined} onClick={() => setGranularity(key)}>{label}</button>)}
        </div>
        <small>{window === 'last10' || window === 'last20' ? '近场只按逐场查看。' : window === '12m' ? '近 12 月默认按月，也可看逐场或季度。' : '全部历史默认按年，也可按月或季度。'}</small>
      </section>

      <section className="panel results-trend-hero">
        <div><span>{fmt(summary.totalRounds, 0)} 场</span><b>{fmt(summary.average18)}</b><small>18 洞均杆</small></div>
        <div><b>{fmt(summary.bestScore, 0)}</b><small>最佳</small><b>{fmt(summary.median18)}</b><small>中位</small></div>
      </section>

      <section className="panel results-trend-plot">
        <header><h2>{granularity === 'round' ? '每一场怎样变化' : `按${granularity === 'month' ? '月' : granularity === 'quarter' ? '季' : '年'}均杆`}</h2><span>点击点位查看证据</span></header>
        {points.length >= 2 ? <TrendSvg points={points} onOpenRound={onOpenRound} onOpenPeriod={onOpenPeriod} /> : <p>当前范围不足两个有效数据点。</p>}
        {points.length ? <div className="results-trend-axis"><span>{points[0].label}</span><span>{points[points.length - 1].label}</span></div> : null}
      </section>

      {periodRows.length ? (
        <section className="panel results-periods" aria-label="周期汇总">
          <h2>周期汇总 · 点击查看球局</h2>
          {periodRows.slice(0, 24).map((row) => {
            const key = asString(row.key) ?? ''
            return <button key={key} type="button" onClick={() => onOpenPeriod(key)}><strong>{key}</strong><span>{fmt(row.roundCount, 0)} 场 · 均杆 {fmt(row.average18)} · 最佳 {fmt(row.bestScore, 0)}</span><b>›</b></button>
          })}
        </section>
      ) : null}

      <section className="panel results-years" aria-label="历年表现">
        <h2>历年表现</h2>
        {years.slice(0, 12).map((row) => {
          const key = asString(row.key) ?? ''
          return <button key={key} type="button" onClick={() => onOpenPeriod(key)}><strong>{key} 年</strong><span>{fmt(row.roundCount, 0)} 场 · 均杆 {fmt(row.average18)} · 最佳 {fmt(row.bestScore, 0)}</span><b>›</b></button>
        })}
      </section>

      <section className="panel results-calendar" aria-label="打球频率">
        <header><div><h2>打球频率 · {calendarYear}</h2><p>{calendarRoundCount} 场 · 活跃 {calendarMonthCount} 个月 · 活跃月均 {calendarMonthCount ? fmt(calendarRoundCount / calendarMonthCount) : '—'} 场</p></div><span>{asString(mostActive.key) ? `生涯最活跃月 ${asString(mostActive.key)} · ${fmt(mostActive.roundCount, 0)} 场` : ''}</span></header>
        <div className="results-calendar-grid">
          {utcCalendarCells(calendarYear).map((day, index) => {
            if (day === null) return <span className="results-calendar-pad" aria-hidden="true" key={`pad-${index}`} />
            const count = dayCounts.get(day) ?? 0
            return <button key={day} type="button" disabled={!count} className={count ? `level-${Math.min(count, 4)}` : undefined} title={`${day} · ${count} 场`} aria-label={`${day}，${count} 场${count ? '，打开球局' : ''}`} onClick={() => onOpenPeriod(day)} />
          })}
        </div>
        <div className="results-calendar-months"><span>1 月</span><span>4 月</span><span>7 月</span><span>10 月</span><span>12 月</span></div>
      </section>
    </section>
  )
}
