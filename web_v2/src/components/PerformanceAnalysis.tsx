import type { MobileStatsResponse, StatsWindow } from '../types'
import { asNumber, asRows, asString } from './statsValues'

interface PerformanceAnalysisProps {
  stats: MobileStatsResponse
  window: StatsWindow
  onWindowChange: (window: StatsWindow) => void
  onOpenScoreBand?: (band: '70s' | '80s' | '90s' | '100+') => void
  onNavigateCourses?: () => void
  onNavigateClubs?: () => void
}

const WINDOWS: Array<[StatsWindow, string]> = [
  ['last10', '近 10 场'],
  ['last20', '近 20 场'],
  ['12m', '近 12 月'],
  ['all', '全部'],
]

function asRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
}

function fraction(hit: number | null, total: number | null): string {
  return hit !== null && total !== null && total > 0 ? `${hit}/${total}` : '未知'
}

function pct(hit: number | null, total: number | null): string {
  return hit !== null && total !== null && total > 0 ? `${Math.round(hit / total * 100)}%` : '—'
}

function fmt(value: number | null): string {
  return value === null ? '—' : Number(value.toFixed(1)).toString()
}

export function PerformanceAnalysis({
  stats,
  window,
  onWindowChange,
  onOpenScoreBand,
  onNavigateCourses,
  onNavigateClubs,
}: PerformanceAnalysisProps) {
  const scoring = asRecord(stats.scoring)
  const phases = asRows(scoring.phaseStats)
  const tee = phases.find((row) => asString(row.phase) === 'Tee')
  const approach = phases.find((row) => asString(row.phase) === 'Approach')
  const teeHit = asNumber(tee?.fairwaysHit)
  const teeRecorded = asNumber(tee?.fairwaysRecorded)
  const gir = asNumber(approach?.gir)
  const girRecorded = asNumber(approach?.girRecorded)
  const putting = asRecord(scoring.putting)
  const putts = asNumber(putting.totalPutts)
  const puttingRounds = asNumber(putting.roundsWithPutts)
  const windowRounds = asNumber(asRecord(stats.summary).totalRounds)
  const puttsPerRound = asNumber(putting.averagePuttsPerRound)
  const outcomes = asRecord(scoring.outcomes)
  const outcomeRows = [
    ['小鸟及以下', (asNumber(outcomes.eagleOrBetter) ?? 0) + (asNumber(outcomes.birdie) ?? 0), 'birdie'],
    ['标准杆', asNumber(outcomes.par) ?? 0, 'par'],
    ['柏忌', asNumber(outcomes.bogey) ?? 0, 'bogey'],
    ['双柏忌+', asNumber(outcomes.doubleOrWorse) ?? 0, 'double'],
  ] as const
  const outcomeTotal = outcomeRows.reduce((sum, row) => sum + row[1], 0)
  const byPar = asRows(scoring.byPar).filter((row) => [3, 4, 5].includes(asNumber(row.par) ?? 0))
  const teeLeft = asNumber(tee?.fairwayMissLeft)
  const teeRight = asNumber(tee?.fairwayMissRight)
  const scoreBands = asRows(scoring.scoreBands)

  return (
    <section className="performance-page" aria-label="表现分析">
      <header className="results-title">
        <p className="eyebrow">真实记录 · 明确分母</p>
        <h1>表现分析</h1>
        <p>未知不算未命中；没有可靠罚杆覆盖时不估算、不补造原因。</p>
      </header>

      <div className="statsx-toolbar">
        <span className="statsx-toolbar-label">统计范围</span>
        <div className="trends-seg" role="group" aria-label="统计范围">
          {WINDOWS.map(([key, label]) => (
            <button key={key} type="button" aria-pressed={key === window} className={key === window ? 'active' : undefined} onClick={() => onWindowChange(key)}>{label}</button>
          ))}
        </div>
      </div>

      <section className="performance-phases" aria-label="四个环节">
        <article className="panel"><span>开球</span><b>{pct(teeHit, teeRecorded)}</b><small>球道 {fraction(teeHit, teeRecorded)}</small>{teeLeft !== null && teeRight !== null ? <em>偏左 {teeLeft} · 偏右 {teeRight}</em> : null}</article>
        <article className="panel"><span>攻果岭</span><b>{pct(gir, girRecorded)}</b><small>GIR {fraction(gir, girRecorded)}</small><em>只统计有 GIR 记录的洞</em></article>
        <article className="panel"><span>推杆</span><b>{fmt(puttsPerRound)}</b><small>场均 · {fraction(puttingRounds, windowRounds)} 场有记录</small><em>{putts !== null ? `累计 ${putts} 推` : '暂无推杆总数'}</em></article>
        <article className="panel"><span>罚杆</span><b>—</b><small>当前历史统计未提供可靠分母</small><em>未知不按 0 次处理</em></article>
      </section>

      <div className="performance-grid">
        <section className="panel" aria-label="成绩构成">
          <h2>成绩构成 · 按洞</h2>
          {outcomeTotal ? outcomeRows.map(([label, count, cls]) => (
            <div className="performance-outcome" key={label}>
              <span>{label}</span><i><b className={cls} style={{ width: `${count / outcomeTotal * 100}%` }} /></i><strong>{count}/{outcomeTotal} · {Math.round(count / outcomeTotal * 100)}%</strong>
            </div>
          )) : <p>暂无按洞成绩记录。</p>}
        </section>

        <section className="panel" aria-label="按标准杆类型">
          <h2>Par 3 / 4 / 5</h2>
          {byPar.length ? byPar.map((row) => (
            <div className="performance-par" key={String(row.par)}>
              <strong>Par {asNumber(row.par)}</strong>
              <span>{asNumber(row.holeCount) ?? 0} 洞</span>
              <span>平均 {fmt(asNumber(row.averageToPar))} 对标准杆</span>
              <span>保帕 {fraction(asNumber(row.parOrBetter), asNumber(row.holeCount))} · {asNumber(row.parOrBetterPct) !== null ? `${fmt(asNumber(row.parOrBetterPct))}%` : '—'}</span>
            </div>
          )) : <p>暂无按 Par 类型统计。</p>}
        </section>
      </div>

      <section className="panel performance-bands" aria-label="成绩区间">
        <h2>成绩区间 · 点击查看球局</h2>
        <div>
          {scoreBands.map((row) => {
            const label = asString(row.label)
            if (!label || !['70s', '80s', '90s', '100+'].includes(label)) return null
            return (
              <button key={label} type="button" onClick={() => onOpenScoreBand?.(label as '70s' | '80s' | '90s' | '100+')}>
                <strong>{label === '100+' ? '100 杆以上' : label.replace('s', '–' + (Number(label.slice(0, 2)) + 9))}</strong>
                <span>{asNumber(row.count) ?? 0} 场 ›</span>
              </button>
            )
          })}
        </div>
      </section>

      <section className="panel performance-links" aria-label="表现下钻">
        <button type="button" onClick={onNavigateCourses}><span><strong>球场表现</strong><small>打过的球场 · 九洞组合 · 球洞规律</small></span><b>查看 ›</b></button>
        <button type="button" onClick={onNavigateClubs}><span><strong>球杆表现</strong><small>历史击球距离 · 离散区间 · 样本数</small></span><b>查看 ›</b></button>
      </section>
    </section>
  )
}
