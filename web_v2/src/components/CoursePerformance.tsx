import type { MobileCourseOptionsResponse, MobileStatsResponse, StatsWindow } from '../types'
import { cleanCourseName } from '../units'
import { asNumber, asRows, asString } from './statsValues'

interface CoursePerformanceProps {
  stats: MobileStatsResponse
  courseOptions?: MobileCourseOptionsResponse | null
  window: StatsWindow
  onWindowChange: (window: StatsWindow) => void
  onOpenRound: (roundId: string) => void
  onPrepCourse?: (globalId: number, name?: string) => void
}

const WINDOWS: Array<[StatsWindow, string]> = [
  ['last10', '近 10 场'],
  ['last20', '近 20 场'],
  ['12m', '近 12 月'],
  ['all', '全部'],
]

function fmt(value: unknown, digits = 1): string {
  const number = asNumber(value)
  return number === null ? '—' : Number(number.toFixed(digits)).toString()
}

export function CoursePerformance({ stats, courseOptions = null, window, onWindowChange, onOpenRound, onPrepCourse }: CoursePerformanceProps) {
  const courses = asRows(stats.courses)
  const globalIds = new Map((courseOptions?.courses ?? []).flatMap((course) =>
    course.courseKey ? [[course.courseKey, course.globalId] as const] : [],
  ))

  return (
    <section className="course-performance" aria-label="球场表现">
      <header className="results-title">
        <p className="eyebrow">历史成绩 · 真实球局</p>
        <h1>球场表现</h1>
        <p>比较你在每个球场的场次、均杆和最佳成绩，再下钻到九洞组合或具体一场。</p>
      </header>
      <div className="statsx-toolbar">
        <span className="statsx-toolbar-label">统计范围</span>
        <div className="trends-seg" role="group" aria-label="统计范围">
          {WINDOWS.map(([key, label]) => <button key={key} type="button" aria-pressed={key === window} className={key === window ? 'active' : undefined} onClick={() => onWindowChange(key)}>{label}</button>)}
        </div>
      </div>
      <section className="panel course-performance-list">
        {courses.length ? courses.map((course, index) => {
          const key = asString(course.courseKey) ?? String(index)
          const name = cleanCourseName(asString(course.courseName) ?? key)
          const recentRoundId = asString(course.recentRoundId)
          const globalId = globalIds.get(key)
          const nines = asRows(course.nineBreakdown)
          const rounds = asRows(course.rounds)
          return (
            <details key={key}>
              <summary>
                <span><strong>{name}</strong><small>{fmt(course.roundCount, 0)} 场 · 均杆 {fmt(course.average18)} · 最佳 {fmt(course.bestScore, 0)}</small></span>
                <b>查看 ›</b>
              </summary>
              <div className="course-performance-detail">
                {nines.length ? <div className="course-performance-nines"><h2>九洞组合</h2>{nines.map((nine, nineIndex) => <p key={asString(nine.label) ?? nineIndex}><strong>{cleanCourseName(asString(nine.label) ?? '九洞')}</strong><span>{fmt(nine.roundCount, 0)} 场 · 均杆 {fmt(nine.average)} · 最佳 {fmt(nine.bestScore, 0)}</span></p>)}</div> : null}
                {rounds.length ? <div className="course-performance-rounds"><h2>球局证据</h2>{rounds.slice(0, 20).map((round, roundIndex) => { const roundId = asString(round.roundId); return <button key={roundId ?? roundIndex} type="button" disabled={!roundId} onClick={() => roundId && onOpenRound(roundId)}><span>{asString(round.date)?.slice(0, 10) ?? '日期未知'} · {fmt(round.holesCompleted, 0)} 洞</span><b>{fmt(round.score, 0)} · {fmt(round.toPar, 0)} ›</b></button> })}</div> : recentRoundId ? <button type="button" className="course-performance-recent" onClick={() => onOpenRound(recentRoundId)}>打开最近一场 ›</button> : null}
                {globalId !== undefined && onPrepCourse ? <button type="button" className="course-performance-prep" aria-label={`去备战 ${name}`} onClick={() => onPrepCourse(globalId, name)}>去备战 ›</button> : null}
              </div>
            </details>
          )
        }) : <p>当前范围没有可比较的球场记录。</p>}
      </section>
    </section>
  )
}
