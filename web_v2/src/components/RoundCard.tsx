import type { RoundCard as RoundCardType } from '../types'
import { useDiagnostics } from '../diagnosticsContext'
import { cleanCourseName, shortRoundDate } from '../units'
import { DataQualityChips } from './DataQualityChips'
import { ScoreStrip } from './ScoreStrip'
import { SourceRefs } from './SourceRefs'

function formatToPar(value: number | null) {
  if (value === null) return '-'
  if (value > 0) return `+${value}`
  return String(value)
}

function toParTone(value: number | null): string {
  if (value === null || value === 0) return 'score-even'
  return value < 0 ? 'score-under' : 'score-over'
}

function roundActionLabel(round: RoundCardType) {
  return `打开球局 ${cleanCourseName(round.courseName)}，${shortRoundDate(round.date)}，成绩 ${round.score ?? '-'}`
}

interface RoundCardProps {
  round: RoundCardType
  onSelectRef?: (sourceRef: string) => void
  onOpenRoundDetail?: (roundRef: string) => void
}

export function RoundCard({ round, onSelectRef, onOpenRoundDetail }: RoundCardProps) {
  const diagnostics = useDiagnostics()
  const canOpen = Boolean(onSelectRef || onOpenRoundDetail)
  return (
    <article className="round-card">
      <div className="round-card-head">
        <div className="round-card-identity">
          <h3>{cleanCourseName(round.courseName)}</h3>
          <p>
            {shortRoundDate(round.date)} · {round.holesCompleted ?? '-'} 洞
          </p>
          {round.source === 'manual' ? (
            <span className="quality-chip round-source-chip" aria-label="AI Caddie 记录的球局">
              AI Caddie
            </span>
          ) : null}
        </div>
        <div className="round-card-outcome">
          <div className="round-score" aria-label={`总杆 ${round.score ?? '-'}，对标准杆 ${formatToPar(round.toPar)}`}>
            <span className="round-score-label">总杆</span>
            <strong>{round.score ?? '-'}</strong>
            <span className={toParTone(round.toPar)}>{formatToPar(round.toPar)}</span>
          </div>
          {canOpen ? (
            <button
              type="button"
              className="round-card-action"
              onClick={() => (onOpenRoundDetail ?? onSelectRef)?.(round.id)}
              aria-label={roundActionLabel(round)}
            >
              查看逐洞 <span aria-hidden="true">→</span>
            </button>
          ) : null}
        </div>
      </div>
      <ScoreStrip cells={round.scoreStrip} />
      {diagnostics ? (
        <div className="round-card-source">
          <span>来源</span>
          <SourceRefs refs={[round.id]} maxVisible={1} onSelectRef={onSelectRef} />
        </div>
      ) : null}
      {diagnostics ? <DataQualityChips badges={round.badges} /> : null}
    </article>
  )
}
