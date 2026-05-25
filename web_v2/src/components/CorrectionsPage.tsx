import { useState, type FormEvent } from 'react'
import type {
  AnnotationCreateRequest,
  AnnotationCreateResponse,
  AnnotationKind,
  AnnotationListResponse,
  AnnotationRecord,
  AnnotationTargetType,
} from '../types'

type CorrectionFormKind = 'club_correction' | 'putt_correction' | 'issue_tag' | 'note'

interface CorrectionsPageProps {
  data: AnnotationListResponse
  onCreateAnnotation: (request: AnnotationCreateRequest) => Promise<AnnotationCreateResponse>
}

const correctionKinds: Array<{ value: CorrectionFormKind; label: string }> = [
  { value: 'club_correction', label: 'Club correction' },
  { value: 'putt_correction', label: 'Putt correction' },
  { value: 'issue_tag', label: 'Issue tag' },
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
  if (record.kind === 'issue_tag') {
    const tag = compactPayloadValue(payload.tag)
    if (tag) return tag
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
  const [recordedPutts, setRecordedPutts] = useState('')
  const [correctedPutts, setCorrectedPutts] = useState('')
  const [issueTag, setIssueTag] = useState('')
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
    } else if (correctionKind === 'putt_correction') {
      kind = 'putt_correction'
      const from = numericPayloadValue(recordedPutts)
      const to = numericPayloadValue(correctedPutts)
      if (from !== null) payload.from = from
      if (to !== null) payload.to = to
      if (trimmedNote) payload.note = trimmedNote
    } else if (correctionKind === 'issue_tag') {
      kind = 'issue_tag'
      if (issueTag.trim()) payload.tag = issueTag.trim()
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
      setRecordedPutts('')
      setCorrectedPutts('')
      setIssueTag('')
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

            {correctionKind === 'issue_tag' ? (
              <label>
                <span>Issue tag</span>
                <input value={issueTag} onChange={(event) => setIssueTag(event.target.value)} />
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
