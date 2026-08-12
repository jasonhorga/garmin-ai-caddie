import type { MobileStatsResponse, StatsWindow } from '../types'
import { asNumber, asRows, asString } from './statsValues'

interface ClubPerformanceProps {
  stats: MobileStatsResponse
  window: StatsWindow
  onWindowChange: (window: StatsWindow) => void
}

const WINDOWS: Array<[StatsWindow, string]> = [
  ['last10', '近 10 场'],
  ['last20', '近 20 场'],
  ['12m', '近 12 月'],
  ['all', '全部'],
]

function yards(metres: number | null): string {
  return metres === null ? '—' : `${Math.round(metres * 1.0936133)} 码`
}

export function ClubPerformance({ stats, window, onWindowChange }: ClubPerformanceProps) {
  const clubs = asRows(stats.clubs)
  return (
    <section className="club-performance" aria-label="球杆表现">
      <header className="results-title">
        <p className="eyebrow">历史击球 · 不修改球包</p>
        <h1>球杆表现</h1>
        <p>这里回答每支杆实际打了多远、波动多大；球包配置和自定义杆距仍在一级「球包」。</p>
      </header>
      <div className="statsx-toolbar">
        <span className="statsx-toolbar-label">统计范围</span>
        <div className="trends-seg" role="group" aria-label="统计范围">
          {WINDOWS.map(([key, label]) => <button key={key} type="button" aria-pressed={key === window} className={key === window ? 'active' : undefined} onClick={() => onWindowChange(key)}>{label}</button>)}
        </div>
      </div>
      <section className="panel">
        <div className="club-performance-head"><span>球杆</span><span>常用距离</span><span>p10–p90</span><span>样本</span></div>
        {clubs.length ? clubs.map((club, index) => (
          <article key={asString(club.club) ?? index}>
            <strong>{asString(club.club) ?? '未知球杆'}</strong>
            <b>{yards(asNumber(club.median))}</b>
            <span>{yards(asNumber(club.p10))} – {yards(asNumber(club.p90))}</span>
            <em>{asNumber(club.sampleCount) ?? 0}</em>
          </article>
        )) : <p>当前范围没有有效球杆距离样本。</p>}
      </section>
    </section>
  )
}
