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
          aria-label={`Hole ${cell.hole}: ${cell.className}, par ${cell.par ?? '-'}, score ${cell.score ?? '-'}`}
          title={`Hole ${cell.hole} - par ${cell.par ?? '-'} - score ${cell.score ?? '-'}`}
        >
          {cell.score ?? '-'}
        </span>
      ))}
    </div>
  )
}
