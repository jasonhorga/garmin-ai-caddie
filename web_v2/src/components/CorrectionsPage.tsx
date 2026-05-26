import { useState, type FormEvent } from 'react'
import type {
  AnnotationCreateRequest,
  AnnotationCreateResponse,
  AnnotationKind,
  AnnotationListResponse,
  AnnotationRecord,
  AnnotationTargetType,
} from '../types'

type CorrectionFormKind =
  | 'club_correction'
  | 'lie_correction'
  | 'penalty_correction'
  | 'putt_correction'
  | 'score_correction'
  | 'issue_tag'
  | 'weather_context_note'
  | 'strategy_note'
  | 'caddie_feedback'
  | 'note'

interface CorrectionsPageProps {
  data: AnnotationListResponse
  onCreateAnnotation: (request: AnnotationCreateRequest) => Promise<AnnotationCreateResponse>
}

const correctionKinds: Array<{ value: CorrectionFormKind; label: string }> = [
  { value: 'club_correction', label: 'Club correction' },
  { value: 'lie_correction', label: 'Lie correction' },
  { value: 'penalty_correction', label: 'Penalty correction' },
  { value: 'putt_correction', label: 'Putt correction' },
  { value: 'score_correction', label: 'Score correction' },
  { value: 'issue_tag', label: 'Issue tag' },
  { value: 'weather_context_note', label: 'Weather note' },
  { value: 'strategy_note', label: 'Strategy note' },
  { value: 'caddie_feedback', label: 'Caddie feedback' },
  { value: 'note', label: 'Note' },
]

const targetTypes: AnnotationTargetType[] = ['round', 'hole', 'shot', 'decision']

function labelKind(kind: AnnotationKind) {
  const labels: Record<AnnotationKind, string> = {
    round_note: 'Round note',
    hole_note: 'Hole note',
    shot_note: 'Shot note',
    issue_tag: 'Issue tag',
    club_correction: 'Club correction',
    lie_correction: 'Lie correction',
    penalty_correction: 'Penalty correction',
    putt_correction: 'Putt correction',
    score_correction: 'Score correction',
    weather_context_note: 'Weather note',
    strategy_note: 'Strategy note',
    caddie_feedback: 'Caddie feedback',
  }
  return labels[kind]
}

function noteKindForTarget(targetType: AnnotationTargetType): AnnotationKind {
  if (targetType === 'round') return 'round_note'
  if (targetType === 'hole') return 'hole_note'
  if (targetType === 'shot') return 'shot_note'
  return 'strategy_note'
}

function compactPayloadValue(value: unknown) {
  if (typeof value === 'string') return value.trim() ? value : null
  if (typeof value === 'number') return String(value)
  return null
}

function numericPayloadValue(value: string) {
  const trimmed = value.trim()
  if (!trimmed) return null
  const parsed = Number(trimmed)
  return Number.isNaN(parsed) ? trimmed : parsed
}

function payloadSummary(record: AnnotationRecord) {
  const { payload } = record
  if (record.kind === 'club_correction') {
    const from = compactPayloadValue(payload.from)
    const to = compactPayloadValue(payload.to)
    if (from && to) return `${from} -> ${to}`
  }
  if (record.kind === 'putt_correction') {
    const from = compactPayloadValue(payload.from)
    const to = compactPayloadValue(payload.to)
    if (from && to) return `${from} -> ${to} putts`
  }
  if (record.kind === 'score_correction') {
    const from = compactPayloadValue(payload.from)
    const to = compactPayloadValue(payload.to)
    if (from && to) return `${from} -> ${to} strokes`
  }
  if (record.kind === 'lie_correction') {
    const from = compactPayloadValue(payload.from)
    const to = compactPayloadValue(payload.to)
    if (from && to) return `${from} -> ${to}`
  }
  if (record.kind === 'penalty_correction') {
    const strokes = compactPayloadValue(payload.strokes)
    const reason = compactPayloadValue(payload.reason)
    if (strokes && reason) return `${strokes} stroke: ${reason}`
    if (strokes) return `${strokes} penalty stroke`
  }
  if (record.kind === 'issue_tag') {
    const tag = compactPayloadValue(payload.tag)
    if (tag) return tag
  }
  if (record.kind === 'caddie_feedback') {
    const rating = compactPayloadValue(payload.rating)
    if (rating) return rating
  }
  if (record.kind.endsWith('_note')) {
    const text = compactPayloadValue(payload.text)
    if (text) return text
  }
  return JSON.stringify(payload)
}

function payloadDetail(record: AnnotationRecord) {
  const note = compactPayloadValue(record.payload.note)
  if (note) return note
  if (!record.kind.endsWith('_note')) {
    const text = compactPayloadValue(record.payload.text)
    if (text) return text
  }
  return null
}

function formatCreatedAt(createdAt: string) {
  const date = new Date(createdAt)
  if (Number.isNaN(date.getTime())) return createdAt
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}

export function CorrectionsPage({ data, onCreateAnnotation }: CorrectionsPageProps) {
  const [targetType, setTargetType] = useState<AnnotationTargetType>('shot')
  const [targetId, setTargetId] = useState('')
  const [correctionKind, setCorrectionKind] = useState<CorrectionFormKind>('club_correction')
  const [recordedClub, setRecordedClub] = useState('')
  const [correctedClub, setCorrectedClub] = useState('')
  const [recordedLie, setRecordedLie] = useState('')
  const [correctedLie, setCorrectedLie] = useState('')
  const [penaltyStrokes, setPenaltyStrokes] = useState('')
  const [penaltyReason, setPenaltyReason] = useState('')
  const [recordedPutts, setRecordedPutts] = useState('')
  const [correctedPutts, setCorrectedPutts] = useState('')
  const [recordedScore, setRecordedScore] = useState('')
  const [correctedScore, setCorrectedScore] = useState('')
  const [issueTag, setIssueTag] = useState('')
  const [feedbackRating, setFeedbackRating] = useState('helpful')
  const [note, setNote] = useState('')
  const [isSaving, setIsSaving] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  function buildRequest(): AnnotationCreateRequest {
    const payload: Record<string, unknown> = {}
    const trimmedNote = note.trim()
    let kind: AnnotationKind

    if (correctionKind === 'club_correction') {
      kind = 'club_correction'
      if (recordedClub.trim()) payload.from = recordedClub.trim()
      if (correctedClub.trim()) payload.to = correctedClub.trim()
      if (trimmedNote) payload.note = trimmedNote
    } else if (correctionKind === 'lie_correction') {
      kind = 'lie_correction'
      if (recordedLie.trim()) payload.from = recordedLie.trim()
      if (correctedLie.trim()) payload.to = correctedLie.trim()
      if (trimmedNote) payload.note = trimmedNote
    } else if (correctionKind === 'penalty_correction') {
      kind = 'penalty_correction'
      const strokes = numericPayloadValue(penaltyStrokes)
      if (strokes !== null) payload.strokes = strokes
      if (penaltyReason.trim()) payload.reason = penaltyReason.trim()
      if (trimmedNote) payload.note = trimmedNote
    } else if (correctionKind === 'putt_correction') {
      kind = 'putt_correction'
      const from = numericPayloadValue(recordedPutts)
      const to = numericPayloadValue(correctedPutts)
      if (from !== null) payload.from = from
      if (to !== null) payload.to = to
      if (trimmedNote) payload.note = trimmedNote
    } else if (correctionKind === 'score_correction') {
      kind = 'score_correction'
      const from = numericPayloadValue(recordedScore)
      const to = numericPayloadValue(correctedScore)
      if (from !== null) payload.from = from
      if (to !== null) payload.to = to
      if (trimmedNote) payload.note = trimmedNote
    } else if (correctionKind === 'issue_tag') {
      kind = 'issue_tag'
      if (issueTag.trim()) payload.tag = issueTag.trim()
      if (trimmedNote) payload.note = trimmedNote
    } else if (correctionKind === 'weather_context_note') {
      kind = 'weather_context_note'
      if (trimmedNote) payload.text = trimmedNote
    } else if (correctionKind === 'strategy_note') {
      kind = 'strategy_note'
      if (trimmedNote) payload.text = trimmedNote
    } else if (correctionKind === 'caddie_feedback') {
      kind = 'caddie_feedback'
      if (feedbackRating.trim()) payload.rating = feedbackRating.trim()
      if (trimmedNote) payload.note = trimmedNote
    } else {
      kind = noteKindForTarget(targetType)
      if (trimmedNote) payload.text = trimmedNote
    }

    return {
      targetType,
      targetId: targetId.trim(),
      kind,
      payload,
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setIsSaving(true)
    setMessage(null)
    try {
      const response = await onCreateAnnotation(buildRequest())
      setMessage(`Saved ${labelKind(response.annotation.kind)}`)
      setTargetId('')
      setRecordedClub('')
      setCorrectedClub('')
      setRecordedLie('')
      setCorrectedLie('')
      setPenaltyStrokes('')
      setPenaltyReason('')
      setRecordedPutts('')
      setCorrectedPutts('')
      setRecordedScore('')
      setCorrectedScore('')
      setIssueTag('')
      setFeedbackRating('helpful')
      setNote('')
    } catch (error: unknown) {
      setMessage(error instanceof Error ? error.message : 'Unable to save annotation')
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <section className="stats-page corrections-page" aria-label="Corrections workspace">
      <div className="section-head stats-head">
        <div>
          <p className="eyebrow">Manual Review</p>
          <h1>Corrections</h1>
          <p>Inspect manual annotation history and add corrections without changing Garmin source snapshots.</p>
        </div>
        <span className="mode-pill">{data.total} records</span>
      </div>

      <section className="corrections-grid">
        <form className="panel annotation-form" aria-label="Create annotation" onSubmit={handleSubmit}>
          <div className="section-head">
            <div>
              <h2>Add Correction</h2>
              <p>Save a targeted manual annotation for derived history stats.</p>
            </div>
          </div>

          <div className="annotation-form-grid">
            <label>
              <span>Target type</span>
              <select value={targetType} onChange={(event) => setTargetType(event.target.value as AnnotationTargetType)}>
                {targetTypes.map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </select>
            </label>

            <label>
              <span>Target ID</span>
              <input value={targetId} onChange={(event) => setTargetId(event.target.value)} required />
            </label>

            <label>
              <span>Correction type</span>
              <select
                value={correctionKind}
                onChange={(event) => setCorrectionKind(event.target.value as CorrectionFormKind)}
              >
                {correctionKinds.map((kind) => (
                  <option key={kind.value} value={kind.value}>
                    {kind.label}
                  </option>
                ))}
              </select>
            </label>

            {correctionKind === 'club_correction' ? (
              <>
                <label>
                  <span>Recorded club</span>
                  <input value={recordedClub} onChange={(event) => setRecordedClub(event.target.value)} />
                </label>
                <label>
                  <span>Corrected club</span>
                  <input value={correctedClub} onChange={(event) => setCorrectedClub(event.target.value)} />
                </label>
              </>
            ) : null}

            {correctionKind === 'lie_correction' ? (
              <>
                <label>
                  <span>Recorded lie</span>
                  <input value={recordedLie} onChange={(event) => setRecordedLie(event.target.value)} />
                </label>
                <label>
                  <span>Corrected lie</span>
                  <input value={correctedLie} onChange={(event) => setCorrectedLie(event.target.value)} />
                </label>
              </>
            ) : null}

            {correctionKind === 'penalty_correction' ? (
              <>
                <label>
                  <span>Penalty strokes</span>
                  <input inputMode="numeric" value={penaltyStrokes} onChange={(event) => setPenaltyStrokes(event.target.value)} />
                </label>
                <label>
                  <span>Penalty reason</span>
                  <input value={penaltyReason} onChange={(event) => setPenaltyReason(event.target.value)} />
                </label>
              </>
            ) : null}

            {correctionKind === 'putt_correction' ? (
              <>
                <label>
                  <span>Recorded putts</span>
                  <input inputMode="numeric" value={recordedPutts} onChange={(event) => setRecordedPutts(event.target.value)} />
                </label>
                <label>
                  <span>Corrected putts</span>
                  <input inputMode="numeric" value={correctedPutts} onChange={(event) => setCorrectedPutts(event.target.value)} />
                </label>
              </>
            ) : null}

            {correctionKind === 'score_correction' ? (
              <>
                <label>
                  <span>Recorded score</span>
                  <input inputMode="numeric" value={recordedScore} onChange={(event) => setRecordedScore(event.target.value)} />
                </label>
                <label>
                  <span>Corrected score</span>
                  <input inputMode="numeric" value={correctedScore} onChange={(event) => setCorrectedScore(event.target.value)} />
                </label>
              </>
            ) : null}

            {correctionKind === 'issue_tag' ? (
              <label>
                <span>Issue tag</span>
                <input value={issueTag} onChange={(event) => setIssueTag(event.target.value)} />
              </label>
            ) : null}

            {correctionKind === 'caddie_feedback' ? (
              <label>
                <span>Feedback rating</span>
                <select value={feedbackRating} onChange={(event) => setFeedbackRating(event.target.value)}>
                  <option value="helpful">Helpful</option>
                  <option value="too_aggressive">Too aggressive</option>
                  <option value="too_conservative">Too conservative</option>
                  <option value="missing_context">Missing context</option>
                </select>
              </label>
            ) : null}

            <label className="annotation-form-wide">
              <span>Note</span>
              <textarea value={note} onChange={(event) => setNote(event.target.value)} rows={4} />
            </label>
          </div>

          <div className="annotation-actions">
            <button type="submit" disabled={isSaving}>
              Save annotation
            </button>
            {message ? <p role="status">{message}</p> : null}
          </div>
        </form>

        <section className="panel annotation-history" aria-label="Annotation history">
          <div className="section-head">
            <div>
              <h2>Annotation History</h2>
              <p>Newest manual records returned by the annotation API.</p>
            </div>
          </div>
          <div className="annotation-list">
            {data.annotations.length === 0 ? (
              <p className="round-empty">No manual annotations yet</p>
            ) : (
              data.annotations.map((record) => (
                <article key={record.id} className="annotation-card">
                  <div className="annotation-card-head">
                    <div>
                      <h3>{labelKind(record.kind)}</h3>
                      <p>
                        {record.targetType}
                        <span>{record.targetId}</span>
                      </p>
                    </div>
                    <span className="mode-pill">{record.source}</span>
                  </div>
                  <strong>{payloadSummary(record)}</strong>
                  {payloadDetail(record) ? <p>{payloadDetail(record)}</p> : null}
                  <p>{formatCreatedAt(record.createdAt)}</p>
                </article>
              ))
            )}
          </div>
        </section>
      </section>
    </section>
  )
}
