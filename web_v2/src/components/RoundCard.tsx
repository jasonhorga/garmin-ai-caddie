import type { RoundCard as RoundCardType } from '../types'
import { DataQualityChips } from './DataQualityChips'
import { ScoreStrip } from './ScoreStrip'

function formatToPar(value: number | null) {
  if (value === null) return '-'
  if (value > 0) return `+${value}`
  return String(value)
}

interface RoundCardProps {
  round: RoundCardType
}

export function RoundCard({ round }: RoundCardProps) {
  return (
    <article className="round-card">
      <div className="round-card-head">
        <div>
          <h3>{round.courseName}</h3>
          <p>
            {round.date ?? 'Unknown date'} - {round.holesCompleted ?? '-'}H
          </p>
        </div>
        <div className="round-score">
          <strong>{round.score ?? '-'}</strong>
          <span>{formatToPar(round.toPar)}</span>
        </div>
      </div>
      <ScoreStrip cells={round.scoreStrip} />
      <DataQualityChips badges={round.badges} />
    </article>
  )
}
