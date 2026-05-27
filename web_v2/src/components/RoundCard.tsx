import type { RoundCard as RoundCardType } from '../types'
import { DataQualityChips } from './DataQualityChips'
import { ScoreStrip } from './ScoreStrip'
import { SourceRefs } from './SourceRefs'

function formatToPar(value: number | null) {
  if (value === null) return '-'
  if (value > 0) return `+${value}`
  return String(value)
}

function roundActionLabel(round: RoundCardType) {
  return `Open round ${round.courseName}, ${round.date ?? 'Unknown date'}, score ${round.score ?? '-'}, ref ${round.id}`
}

interface RoundCardProps {
  round: RoundCardType
  onSelectRef?: (sourceRef: string) => void
}

export function RoundCard({ round, onSelectRef }: RoundCardProps) {
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
      {onSelectRef ? (
        <button type="button" className="round-card-action" onClick={() => onSelectRef(round.id)} aria-label={roundActionLabel(round)}>
          Open
        </button>
      ) : null}
      <ScoreStrip cells={round.scoreStrip} />
      <div className="round-card-source">
        <span>Source</span>
        <SourceRefs refs={[round.id]} maxVisible={1} onSelectRef={onSelectRef} />
      </div>
      <DataQualityChips badges={round.badges} />
    </article>
  )
}
