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
  return `打开球局 ${round.courseName}, ${round.date ?? '未知日期'}, score ${round.score ?? '-'}, ref ${round.id}`
}

interface RoundCardProps {
  round: RoundCardType
  onSelectRef?: (sourceRef: string) => void
  onOpenRoundDetail?: (roundRef: string) => void
}

export function RoundCard({ round, onSelectRef, onOpenRoundDetail }: RoundCardProps) {
  return (
    <article className="round-card">
      <div className="round-card-head">
        <div>
          <h3>{round.courseName}</h3>
          <p>
            {round.date ?? 'Unknown date'} - {round.holesCompleted ?? '-'}H
          </p>
          {round.source === 'manual' ? (
            <span className="quality-chip round-source-chip" aria-label="手动录入的球局">
              手动
            </span>
          ) : null}
        </div>
        <div className="round-score">
          <strong>{round.score ?? '-'}</strong>
          <span>{formatToPar(round.toPar)}</span>
        </div>
      </div>
      {onSelectRef || onOpenRoundDetail ? (
        <button
          type="button"
          className="round-card-action"
          onClick={() => (onOpenRoundDetail ?? onSelectRef)?.(round.id)}
          aria-label={roundActionLabel(round)}
        >
          打开
        </button>
      ) : null}
      <ScoreStrip cells={round.scoreStrip} />
      <div className="round-card-source">
        <span>来源</span>
        <SourceRefs refs={[round.id]} maxVisible={1} onSelectRef={onSelectRef} />
      </div>
      <DataQualityChips badges={round.badges} />
    </article>
  )
}
