import { useState, type FormEvent } from 'react'
import type {
  AnnotationCreateRequest,
  AnnotationCreateResponse,
  AnnotationKind,
  AnnotationListResponse,
  AnnotationRecord,
  AnnotationTargetType,
} from '../types'
import { annotationKindZh, targetTypeZh } from '../zhLabels'

type CorrectionFormKind =
  | 'club_correction'
  | 'lie_correction'
  | 'penalty_correction'
  | 'putt_correction'
  | 'score_correction'
  | 'issue_tag'
  | 'issue_tag_removed'
  | 'weather_context_note'
  | 'strategy_note'
  | 'caddie_feedback'
  | 'note'

interface CorrectionsPageProps {
  data: AnnotationListResponse
  initialTarget?: CorrectionTarget
  onCreateAnnotation: (request: AnnotationCreateRequest) => Promise<AnnotationCreateResponse>
}

export interface CorrectionTarget {
  targetType: AnnotationTargetType
  targetId: string
}

const correctionKinds: Array<{ value: CorrectionFormKind; label: string }> = [
  { value: 'club_correction', label: '球杆订正' },
  { value: 'lie_correction', label: '球位订正' },
  { value: 'penalty_correction', label: '罚杆订正' },
  { value: 'putt_correction', label: '推杆订正' },
  { value: 'score_correction', label: '成绩订正' },
  { value: 'issue_tag', label: '问题标签' },
  { value: 'issue_tag_removed', label: '移除问题标签' },
  { value: 'weather_context_note', label: '天气备注' },
  { value: 'strategy_note', label: '策略备注' },
  { value: 'caddie_feedback', label: '球童反馈' },
  { value: 'note', label: '备注' },
]

const targetTypes: AnnotationTargetType[] = ['round', 'hole', 'shot', 'decision']
const correctionKindSet = new Set<AnnotationKind>([
  'club_correction',
  'lie_correction',
  'penalty_correction',
  'putt_correction',
  'score_correction',
])
const statsOverlayKindSet = new Set<AnnotationKind>([
  ...correctionKindSet,
  'issue_tag',
  'issue_tag_removed',
])

// Kind labels live in zhLabels.annotationKindZh so the round-detail and
// drilldown annotation rows share the same vocabulary.
const labelKind = annotationKindZh

// record.source vocabulary ('manual' today); unknown sources fall through raw.
const ANNOTATION_SOURCE_ZH: Record<string, string> = { manual: '手动' }

function annotationSourceZh(raw: string): string {
  return ANNOTATION_SOURCE_ZH[raw] ?? raw
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

function isFiniteNumberLike(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function missingPayloadMessage(kind: CorrectionFormKind, payload: Record<string, unknown>): string | null {
  if (kind === 'club_correction') {
    return payload.from && payload.to ? null : '球杆订正需要同时填写原记录与订正后的球杆。'
  }
  if (kind === 'lie_correction') {
    return payload.from && payload.to ? null : '球位订正需要同时填写原记录与订正后的球位。'
  }
  if (kind === 'penalty_correction') {
    return isFiniteNumberLike(payload.strokes) && payload.strokes >= 1 ? null : '罚杆订正需要 1 杆及以上的罚杆数。'
  }
  if (kind === 'putt_correction') {
    return isFiniteNumberLike(payload.from) && isFiniteNumberLike(payload.to) ? null : '推杆订正需要数字形式的原记录与订正后推杆数。'
  }
  if (kind === 'score_correction') {
    return isFiniteNumberLike(payload.from) && isFiniteNumberLike(payload.to) ? null : '成绩订正需要数字形式的原记录与订正后成绩。'
  }
  if (kind === 'issue_tag' || kind === 'issue_tag_removed') {
    return payload.tag ? null : '问题标签操作需要填写标签。'
  }
  if (kind === 'weather_context_note' || kind === 'strategy_note' || kind === 'note') {
    return payload.text ? null : '备注需先填写内容再保存。'
  }
  return Object.keys(payload).length ? null : '保存前请填写订正详情。'
}

function payloadSummary(record: AnnotationRecord) {
  const { payload } = record
  if (record.kind === 'club_correction') {
    const from = compactPayloadValue(payload.from)
    const to = compactPayloadValue(payload.to)
    if (from && to) return `${from} → ${to}`
  }
  if (record.kind === 'putt_correction') {
    const from = compactPayloadValue(payload.from)
    const to = compactPayloadValue(payload.to)
    if (from && to) return `推杆 ${from} → ${to}`
  }
  if (record.kind === 'score_correction') {
    const from = compactPayloadValue(payload.from)
    const to = compactPayloadValue(payload.to)
    if (from && to) return `成绩 ${from} → ${to}`
  }
  if (record.kind === 'lie_correction') {
    const from = compactPayloadValue(payload.from)
    const to = compactPayloadValue(payload.to)
    if (from && to) return `${from} → ${to}`
  }
  if (record.kind === 'penalty_correction') {
    const strokes = compactPayloadValue(payload.strokes)
    const reason = compactPayloadValue(payload.reason)
    if (strokes && reason) return `罚 ${strokes} 杆:${reason}`
    if (strokes) return `罚 ${strokes} 杆`
  }
  if (record.kind === 'issue_tag' || record.kind === 'issue_tag_removed') {
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

function countBy<T extends string>(values: T[]): Array<{ label: T; count: number }> {
  const counts = new Map<T, number>()
  for (const value of values) counts.set(value, (counts.get(value) ?? 0) + 1)
  return Array.from(counts.entries())
    .map(([label, count]) => ({ label, count }))
    .sort((left, right) => right.count - left.count || left.label.localeCompare(right.label))
}

function CorrectionImpactPanel({ annotations }: { annotations: AnnotationRecord[] }) {
  const correctionCount = annotations.filter((record) => correctionKindSet.has(record.kind)).length
  const statsOverlayCount = annotations.filter((record) => statsOverlayKindSet.has(record.kind)).length
  const targetRows = countBy(annotations.map((record) => record.targetType))
  const kindRows = countBy(annotations.map((record) => record.kind)).slice(0, 5)

  return (
    <section className="panel correction-impact" aria-label="订正影响">
      <div className="section-head">
        <div>
          <h2>订正影响</h2>
          <p>人工记录仅作为派生统计的覆盖层;Garmin 原始快照保持不变。</p>
        </div>
      </div>
      <div className="correction-impact-metrics">
        <div>
          <span>批注总数</span>
          <b>{annotations.length}</b>
        </div>
        <div>
          <span>统计覆盖</span>
          <b>{statsOverlayCount}</b>
        </div>
        <div>
          <span>订正</span>
          <b>{correctionCount}</b>
        </div>
      </div>
      <div className="correction-impact-rules" aria-label="订正规则">
        <span>只追加审计日志</span>
        <span>原始事实不可变</span>
        <span>历史统计使用显式覆盖</span>
      </div>
      {targetRows.length || kindRows.length ? (
        <div className="correction-impact-breakdown">
          {targetRows.length ? (
            <div aria-label="订正目标分布">
              <h3>目标</h3>
              {targetRows.map((row) => (
                <span key={row.label}>
                  {targetTypeZh(row.label)} {row.count}
                </span>
              ))}
            </div>
          ) : null}
          {kindRows.length ? (
            <div aria-label="订正类型分布">
              <h3>类型</h3>
              {kindRows.map((row) => (
                <span key={row.label}>
                  {labelKind(row.label)} {row.count}
                </span>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  )
}

export function CorrectionsPage({ data, initialTarget, onCreateAnnotation }: CorrectionsPageProps) {
  const [targetType, setTargetType] = useState<AnnotationTargetType>(initialTarget?.targetType ?? 'shot')
  const [targetId, setTargetId] = useState(initialTarget?.targetId ?? '')
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
    } else if (correctionKind === 'issue_tag' || correctionKind === 'issue_tag_removed') {
      kind = correctionKind
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
    setMessage(null)
    const request = buildRequest()
    const validationMessage = targetId.trim() ? missingPayloadMessage(correctionKind, request.payload) : '请填写目标编号。'
    if (validationMessage) {
      setMessage(validationMessage)
      return
    }

    setIsSaving(true)
    try {
      const response = await onCreateAnnotation(request)
      setMessage(`已保存 ${labelKind(response.annotation.kind)}`)
      setTargetType(initialTarget?.targetType ?? targetType)
      setTargetId(initialTarget?.targetId ?? '')
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
      setMessage(error instanceof Error ? error.message : '批注保存失败')
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <section className="stats-page corrections-page" aria-label="订正工作区">
      <div className="section-head stats-head">
        <div>
          <p className="eyebrow">人工复核</p>
          <h1>订正</h1>
          <p>查看人工批注历史,在不改动 Garmin 原始快照的前提下添加订正。</p>
        </div>
        <span className="mode-pill">{data.total} 条记录</span>
      </div>

      <section className="corrections-grid">
        <div className="corrections-stack">
          <CorrectionImpactPanel annotations={data.annotations} />
          <form className="panel annotation-form" aria-label="新增批注" onSubmit={handleSubmit}>
            <div className="section-head">
              <div>
                <h2>新增订正</h2>
                <p>为派生历史统计保存定向人工批注。</p>
              </div>
              {initialTarget ? <span className="mode-pill">来源绑定</span> : null}
            </div>

            <div className="annotation-form-grid">
              <label>
                <span>目标类型</span>
                <select value={targetType} onChange={(event) => setTargetType(event.target.value as AnnotationTargetType)}>
                  {targetTypes.map((type) => (
                    <option key={type} value={type}>
                      {targetTypeZh(type)}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                <span>目标编号</span>
                <input value={targetId} onChange={(event) => setTargetId(event.target.value)} required />
              </label>

              <label>
                <span>订正类型</span>
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
                  <span>原记录球杆</span>
                  <input value={recordedClub} onChange={(event) => setRecordedClub(event.target.value)} />
                </label>
                <label>
                  <span>订正后球杆</span>
                  <input value={correctedClub} onChange={(event) => setCorrectedClub(event.target.value)} />
                </label>
              </>
            ) : null}

            {correctionKind === 'lie_correction' ? (
              <>
                <label>
                  <span>原记录球位</span>
                  <input value={recordedLie} onChange={(event) => setRecordedLie(event.target.value)} />
                </label>
                <label>
                  <span>订正后球位</span>
                  <input value={correctedLie} onChange={(event) => setCorrectedLie(event.target.value)} />
                </label>
              </>
            ) : null}

            {correctionKind === 'penalty_correction' ? (
              <>
                <label>
                  <span>罚杆数</span>
                  <input inputMode="numeric" value={penaltyStrokes} onChange={(event) => setPenaltyStrokes(event.target.value)} />
                </label>
                <label>
                  <span>罚杆原因</span>
                  <input value={penaltyReason} onChange={(event) => setPenaltyReason(event.target.value)} />
                </label>
              </>
            ) : null}

            {correctionKind === 'putt_correction' ? (
              <>
                <label>
                  <span>原记录推杆</span>
                  <input inputMode="numeric" value={recordedPutts} onChange={(event) => setRecordedPutts(event.target.value)} />
                </label>
                <label>
                  <span>订正后推杆</span>
                  <input inputMode="numeric" value={correctedPutts} onChange={(event) => setCorrectedPutts(event.target.value)} />
                </label>
              </>
            ) : null}

            {correctionKind === 'score_correction' ? (
              <>
                <label>
                  <span>原记录成绩</span>
                  <input inputMode="numeric" value={recordedScore} onChange={(event) => setRecordedScore(event.target.value)} />
                </label>
                <label>
                  <span>订正后成绩</span>
                  <input inputMode="numeric" value={correctedScore} onChange={(event) => setCorrectedScore(event.target.value)} />
                </label>
              </>
            ) : null}

            {correctionKind === 'issue_tag' || correctionKind === 'issue_tag_removed' ? (
              <label>
                <span>问题标签</span>
                <input value={issueTag} onChange={(event) => setIssueTag(event.target.value)} />
              </label>
            ) : null}

            {correctionKind === 'caddie_feedback' ? (
              <label>
                <span>反馈评价</span>
                <select value={feedbackRating} onChange={(event) => setFeedbackRating(event.target.value)}>
                  <option value="helpful">有帮助</option>
                  <option value="too_aggressive">太激进</option>
                  <option value="too_conservative">太保守</option>
                  <option value="missing_context">缺少上下文</option>
                </select>
              </label>
            ) : null}

            <label className="annotation-form-wide">
              <span>备注</span>
              <textarea value={note} onChange={(event) => setNote(event.target.value)} rows={4} />
            </label>
          </div>

            <div className="annotation-actions">
              <button type="submit" disabled={isSaving}>
                保存批注
              </button>
              {message ? <p role="status">{message}</p> : null}
            </div>
          </form>
        </div>

        <section className="panel annotation-history" aria-label="批注历史">
          <div className="section-head">
            <div>
              <h2>批注历史</h2>
              <p>批注 API 返回的最新人工记录。</p>
            </div>
          </div>
          <div className="annotation-list">
            {data.annotations.length === 0 ? (
              <p className="round-empty">暂无人工批注</p>
            ) : (
              data.annotations.map((record) => (
                <article key={record.id} className="annotation-card">
                  <div className="annotation-card-head">
                    <div>
                      <h3>{labelKind(record.kind)}</h3>
                      <p>
                        {targetTypeZh(record.targetType)}
                        <span>{record.targetId}</span>
                      </p>
                    </div>
                    <span className="mode-pill">{annotationSourceZh(record.source)}</span>
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
