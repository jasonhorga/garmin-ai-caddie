import type { ScoreClass } from '../types'

export interface ScorecardGridCell {
  hole: number
  par: number | null
  score: number | null
  toPar: number | null
  putts: number | null
  penalties?: number | null
  className?: ScoreClass
  holeRef?: string
}

function toParText(value: number | null): string {
  if (value === null) return '-'
  if (value > 0) return `+${value}`
  return String(value)
}

function scoreClass(cell: ScorecardGridCell): ScoreClass {
  if (cell.className) return cell.className
  if (cell.toPar === null) return 'missing'
  if (cell.toPar <= -2) return 'eagle'
  if (cell.toPar === -1) return 'birdie'
  if (cell.toPar === 0) return 'par'
  if (cell.toPar === 1) return 'bogey'
  return 'double'
}

interface ScorecardGridProps {
  scorecard: ScorecardGridCell[]
  onSelectRef?: (sourceRef: string) => void
}

/** Read-only scorecard shared by the authenticated review and anonymous share page. */
export function ScorecardGrid({ scorecard, onSelectRef }: ScorecardGridProps): React.ReactElement | null {
  if (scorecard.length === 0) return null
  const front = scorecard.filter((cell) => cell.hole <= 9)
  const back = scorecard.filter((cell) => cell.hole > 9)
  const renderNine = (label: '前九' | '后九', cells: ScorecardGridCell[]) => {
    if (cells.length === 0) return null
    return (
      <div className="round-detail-nine" aria-label={`${label}记分卡`}>
        <span className="round-detail-nine-label">{label}</span>
        <div className="round-detail-nine-grid">
          {cells.map((cell) => {
            const content = (
              <>
                <span>H{cell.hole}</span>
                <b className="round-detail-score-mark">{cell.score ?? '-'}</b>
                <small>
                  Par {cell.par ?? '-'} · {toParText(cell.toPar)}
                </small>
                <em>
                  {cell.putts === null ? '推杆 —' : `${cell.putts}推`}
                  {cell.penalties == null ? '' : ` · 罚${cell.penalties}`}
                </em>
              </>
            )
            const className = `round-detail-cell score-${scoreClass(cell)}`
            return onSelectRef && cell.holeRef ? (
              <button
                key={cell.holeRef}
                type="button"
                className={className}
                onClick={() => onSelectRef(cell.holeRef as string)}
                aria-label={`第${cell.hole}洞详情`}
              >
                {content}
              </button>
            ) : (
              <div key={cell.holeRef ?? cell.hole} className={className}>
                {content}
              </div>
            )
          })}
        </div>
      </div>
    )
  }
  return (
    <section className="round-detail-section" aria-label="记分卡">
      <div className="section-head">
        <div>
          <h3>记分卡</h3>
          <p>逐洞成绩、推杆数、罚杆数</p>
        </div>
      </div>
      <div className="round-detail-scorecard">
        {renderNine('前九', front)}
        {renderNine('后九', back)}
      </div>
    </section>
  )
}
