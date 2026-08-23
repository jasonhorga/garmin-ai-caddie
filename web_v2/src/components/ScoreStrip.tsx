import type { ScoreStripCell } from '../types'

interface ScoreStripProps {
  cells: ScoreStripCell[]
}

export function ScoreStrip({ cells }: ScoreStripProps) {
  const front = cells.filter((cell) => cell.hole <= 9)
  const back = cells.filter((cell) => cell.hole > 9)

  const renderNine = (label: '前九' | '后九', rows: ScoreStripCell[]) => {
    if (rows.length === 0) return null
    return (
      <div className="score-nine" aria-label={`${label}成绩`}>
        <span className="score-nine-label">{label}</span>
        <div className="score-nine-grid">
          {rows.map((cell) => (
            <span
              key={cell.hole}
              className={`score-cell score-${cell.className}`}
              aria-label={`第${cell.hole}洞: 标准杆 ${cell.par ?? '-'}, 成绩 ${cell.score ?? '-'}`}
              title={`第${cell.hole}洞 - 标准杆 ${cell.par ?? '-'} - 成绩 ${cell.score ?? '-'}`}
            >
              <span className="score-cell-hole">{cell.hole}</span>
              <span className="score-cell-mark">{cell.score ?? '-'}</span>
            </span>
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="score-strip">
      {renderNine('前九', front)}
      {renderNine('后九', back)}
    </div>
  )
}
