import type { HistoryOverviewResponse, HistoryStatsSummaryResponse, MobileStatsResponse, RoundCard } from '../types'
import type { ProductPage } from '../navigation'
import { cleanCourseName, shortRoundDate } from '../units'
import { asNumber, asRows } from './statsValues'

interface ResultsLandingProps {
  overview: HistoryOverviewResponse
  summary: HistoryStatsSummaryResponse | null
  recentStats: MobileStatsResponse | null
  onNavigate: (page: ProductPage) => void
  onOpenRound: (roundRef: string) => void
}

function fmt(value: unknown, digits = 1): string {
  const number = asNumber(value)
  return number === null ? '—' : Number(number.toFixed(digits)).toString()
}

function toPar(value: number | null): string {
  if (value === null) return ''
  if (value === 0) return 'E'
  return value > 0 ? `+${value}` : String(value)
}

function RecentRound({ round, onOpen }: { round: RoundCard; onOpen: () => void }) {
  return (
    <button type="button" className="results-round-row" onClick={onOpen}>
      <span>
        <strong>{cleanCourseName(round.courseName)}</strong>
        <small>{shortRoundDate(round.date)} · {round.holesCompleted ?? '—'} 洞</small>
      </span>
      <b>{round.score ?? '—'}</b>
      <em className={(round.toPar ?? 0) > 0 ? 'bad' : 'good'}>{toPar(round.toPar)}</em>
    </button>
  )
}

export function ResultsLanding({ overview, summary, recentStats, onNavigate, onOpenRound }: ResultsLandingProps) {
  const s = summary?.summary ?? overview.metrics
  const courses = asRows(recentStats?.courses)
  const clubs = asRows(recentStats?.clubs)
  const time = recentStats?.time as Record<string, unknown> | undefined
  const scoring = recentStats?.scoring as Record<string, unknown> | undefined
  const periods = asRows(time?.byYear)
  const phases = asRows(scoring?.phaseStats)
  const tee = phases.find((row) => row.phase === 'Tee')
  const approach = phases.find((row) => row.phase === 'Approach')
  const teeHit = asNumber(tee?.fairwaysHit)
  const teeRecorded = asNumber(tee?.fairwaysRecorded ?? tee?.sampleCount)
  const gir = asNumber(approach?.gir)
  const girRecorded = asNumber(approach?.girRecorded ?? approach?.sampleCount)
  const recentRounds = overview.recentRounds.slice(0, 3)

  return (
    <section className="results-landing" aria-label="成绩主页">
      <header className="results-title">
        <p className="eyebrow">球局 · 统计</p>
        <h1>成绩</h1>
        <p>先看近期与生涯状态，再下钻到每一场、每个周期和每个环节。</p>
      </header>

      <section className="panel results-career" aria-label="生涯概览">
        <div className="results-career-head">
          <span><b>{fmt(s.totalRounds, 0)}</b><small>场球</small></span>
          <p>{fmt(s.eighteenHoleRounds, 0)} 场完整 18 洞 · {fmt(s.courseCount, 0)} 个球场</p>
        </div>
        <div className="results-kpis">
          <span><b>{fmt(s.average18)}</b><small>18 洞均杆</small></span>
          <span><b>{fmt(s.bestScore, 0)}</b><small>历史最佳</small></span>
          <span><b>{fmt(s.handicapEstimate)}</b><small>差点估算</small></span>
        </div>
      </section>

      <button type="button" className="panel results-recent" onClick={() => onNavigate('history')}>
        <span><strong>最近状态</strong><small>近 10 场 {fmt(s.recent10Average)} · 近 20 场 {fmt(s.recent20Average)}</small></span>
        <b>看时间趋势 →</b>
      </button>

      <section className="panel results-recent-rounds" aria-label="最近球局">
        <header><h2>最近球局</h2><button type="button" onClick={() => onNavigate('rounds')}>全部 {fmt(s.totalRounds, 0)} 场 →</button></header>
        {recentRounds.length ? recentRounds.map((round) => (
          <RecentRound key={round.id} round={round} onOpen={() => onOpenRound(round.id)} />
        )) : <p>暂无可显示的球局。</p>}
      </section>

      <section className="panel results-destinations" aria-label="成绩下钻">
        <button type="button" onClick={() => onNavigate('rounds')}><span><strong>全部球局</strong><small>搜索 · 年份 · 球场 · 逐杆数据</small></span><b>{fmt(s.totalRounds, 0)} 场 ›</b></button>
        <button type="button" onClick={() => onNavigate('history')}><span><strong>时间趋势</strong><small>近 10 / 20 场 · 年 · 季 · 月 · 频率</small></span><b>{periods[0]?.key ? `${periods[0].key} · ${fmt(periods[0].roundCount, 0)} 场` : '查看 ›'}</b></button>
        <button type="button" onClick={() => onNavigate('holes')}><span><strong>表现分析</strong><small>开球 · 攻果岭 · 推杆 · 罚杆</small></span><b>{teeHit !== null && teeRecorded ? `${teeHit}/${teeRecorded}` : '查看'} · {gir !== null && girRecorded ? `${gir}/${girRecorded}` : '—'} ›</b></button>
        <button type="button" onClick={() => onNavigate('courses')}><span><strong>球场</strong><small>球场表现 · 九洞组合 · 球洞规律</small></span><b>{courses.length} 个 ›</b></button>
        <button type="button" onClick={() => onNavigate('result-clubs')}><span><strong>球杆</strong><small>历史击球 · 中位距离 · p10–p90 · 样本数</small></span><b>{clubs.length} 支 ›</b></button>
      </section>
    </section>
  )
}
