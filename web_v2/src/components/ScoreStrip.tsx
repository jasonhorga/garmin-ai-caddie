import type { CSSProperties } from 'react'
import type { ScoreStripCell } from '../types'

interface ScoreStripProps {
  cells: ScoreStripCell[]
}

export function ScoreStrip({ cells }: ScoreStripProps) {
  return (
    <div className="score-strip" style={{ '--score-cells': Math.max(cells.length, 1) } as CSSProperties}>
      {cells.map((cell) => (
        <span
          key={cell.hole}
          className={`score-cell score-${cell.className}`}
          aria-label={`第${cell.hole}洞: ${cell.className}, 标准杆 ${cell.par ?? '-'}, 成绩 ${cell.score ?? '-'}`}
          title={`第${cell.hole}洞 - 标准杆 ${cell.par ?? '-'} - 成绩 ${cell.score ?? '-'}`}
        >
          {cell.score ?? '-'}
        </span>
      ))}
    </div>
  )
}
