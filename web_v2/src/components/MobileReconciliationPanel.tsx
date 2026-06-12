import { useState, type FormEvent } from 'react'
import { confidenceZh } from '../zhLabels'
import type { MobileReconciliationApplyResponse, MobileReconciliationResponse, MobileReconciliationSuggestion } from '../types'

export type MobileReconciliationPanelState =
  | { status: 'idle' }
  | { status: 'loading'; roundId: string }
  | { status: 'ready'; data: MobileReconciliationResponse }
  | { status: 'error'; roundId: string; message: string }

export type MobileReconciliationApplyState =
  | { status: 'idle' }
  | { status: 'applying' }
  | { status: 'ready'; data: MobileReconciliationApplyResponse }
  | { status: 'error'; message: string }

interface MobileReconciliationPanelProps {
  state: MobileReconciliationPanelState
  applyState: MobileReconciliationApplyState
  onLoad: (roundId: string) => void
  onApply: (roundId: string, suggestionIds: string[]) => void | Promise<void>
  defaultRoundId?: string
}

function formatCount(value: number, unitLabel: string) {
  return `${value} ${unitLabel}`
}

function compactValue(value: unknown) {
  if (typeof value === 'string') return value
  if (typeof value === 'number') return String(value)
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  return null
}

function rowValue(row: Record<string, unknown>) {
  return (
    compactValue(row.localValue) ??
    compactValue(row.garminValue) ??
    compactValue(row.ref) ??
    compactValue(row.decisionId) ??
    compactValue(row.actualOptionId) ??
    compactValue(row.kind) ??
    ''
  )
}

function rowLabel(row: Record<string, unknown>, fallback: string) {
  return compactValue(row.eventId) ?? compactValue(row.ref) ?? compactValue(row.decisionId) ?? compactValue(row.kind) ?? fallback
}

function suggestionSummary(suggestion: MobileReconciliationSuggestion) {
  const from = compactValue(suggestion.payload.from)
  const to = compactValue(suggestion.payload.to)
  if (from && to) return `${from} → ${to}`
  const text = compactValue(suggestion.payload.text) ?? compactValue(suggestion.payload.note)
  const mediaType = compactValue(suggestion.payload.mediaType)
  const mediaId = compactValue(suggestion.payload.mediaId)
  if (mediaType && mediaId) return text ? `${mediaType} ${mediaId}: ${text}` : `${mediaType} ${mediaId}`
  if (text) return text
  const strokes = compactValue(suggestion.payload.strokes)
  if (strokes) return `罚 ${strokes} 杆`
  const sourceEventId = compactValue(suggestion.payload.sourceEventId)
  return sourceEventId ? `事件 ${sourceEventId}` : suggestion.kind
}

export function MobileReconciliationPanel({
  state,
  applyState,
  onLoad,
  onApply,
  defaultRoundId = '900001',
}: MobileReconciliationPanelProps) {
  const [roundId, setRoundId] = useState(defaultRoundId)
  const [roundIdDirty, setRoundIdDirty] = useState(false)
  const [deselectedKeys, setDeselectedKeys] = useState<string[]>([])
  const readyData = state.status === 'ready' ? state.data : null
  const isApplying = applyState.status === 'applying'
  const displayRoundId = readyData && !roundIdDirty ? readyData.roundId : roundId
  const selectedIds = readyData
    ? readyData.annotationSuggestions
        .map((suggestion) => suggestion.id)
        .filter((id) => !deselectedKeys.includes(`${readyData.roundId}:${id}`))
    : []

  function handleLoad(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const trimmed = displayRoundId.trim()
    if (!trimmed) return
    setRoundIdDirty(false)
    onLoad(trimmed)
  }

  function toggleSuggestion(id: string) {
    if (!readyData) return
    const key = `${readyData.roundId}:${id}`
    setDeselectedKeys((current) => (current.includes(key) ? current.filter((item) => item !== key) : [...current, key]))
  }

  function handleApply() {
    if (!readyData || selectedIds.length === 0 || isApplying) return
    void onApply(readyData.roundId, selectedIds)
  }

  return (
    <section className="mobile-reconciliation-panel" aria-label="移动离线对账">
      <div className="section-head stats-head">
        <div>
          <p className="eyebrow">离线输入</p>
          <h2>离线对账</h2>
          <p>将 iOS 与手表的事件日志和已同步的 Garmin 事实核对，并把选中的修正作为可审计批注应用。</p>
        </div>
      </div>

      <form className="mobile-reconcile-form" aria-label="离线对账查询" onSubmit={handleLoad}>
        <label htmlFor="mobile-reconcile-round-id">球局编号</label>
        <input
          id="mobile-reconcile-round-id"
          value={displayRoundId}
          onChange={(event) => {
            setRoundIdDirty(true)
            setRoundId(event.target.value)
          }}
          spellCheck={false}
        />
        <button type="submit" disabled={!displayRoundId.trim() || state.status === 'loading'}>
          {state.status === 'loading' ? '核对中' : '核对离线事件'}
        </button>
      </form>

      {state.status === 'idle' ? (
        <article className="stats-empty">
          <h2>尚未载入对账</h2>
          <p>等 iOS 或手表的事件同步回来后，选择一场球局。</p>
        </article>
      ) : null}

      {state.status === 'loading' ? (
        <article className="stats-empty">
          <h2>对账载入中</h2>
          <p>{state.roundId}</p>
        </article>
      ) : null}

      {state.status === 'error' ? (
        <article className="stats-empty">
          <h2>对账不可用</h2>
          <p>{state.message}</p>
        </article>
      ) : null}

      {readyData ? (
        <div className="mobile-reconcile-body">
          <div className="mobile-reconcile-summary" aria-label="对账摘要">
            <span>{formatCount(readyData.summary.eventCount, '个事件')}</span>
            <span>{formatCount(readyData.summary.matchedCount, '项匹配')}</span>
            <span>{formatCount(readyData.summary.localOnlyCount, '条仅本地事件')}</span>
            <span>{formatCount(readyData.summary.garminOnlyCount, '条仅 Garmin 事实')}</span>
            <span>{formatCount(readyData.summary.conflictCount, '处冲突')}</span>
            <span>{formatCount(readyData.summary.annotationSuggestionCount, '条建议')}</span>
          </div>

          <div className="mobile-reconcile-suggestions" aria-label="对账建议">
            {readyData.annotationSuggestions.length === 0 ? (
              <article className="stats-empty">
                <h2>暂无对账建议</h2>
                <p>本地事件与已同步的 Garmin 事实一致，或证据不足以提出修正。</p>
              </article>
            ) : null}

            {readyData.annotationSuggestions.map((suggestion) => (
              <article key={suggestion.id} className="mobile-reconcile-suggestion">
                <label>
                  <input
                    type="checkbox"
                    checked={selectedIds.includes(suggestion.id)}
                    onChange={() => toggleSuggestion(suggestion.id)}
                    aria-label={`选择建议 ${suggestion.id}`}
                  />
                  <span>{suggestion.kind}</span>
                </label>
                <div>
                  <strong>{suggestion.targetId}</strong>
                  <p>{suggestion.reason}</p>
                  <p>{suggestionSummary(suggestion)}</p>
                </div>
                <span className={`semantic-chip confidence-${suggestion.confidence}`}>{confidenceZh(suggestion.confidence)}</span>
              </article>
            ))}
          </div>

          <div className="mobile-reconcile-evidence-grid">
            <EvidenceRows title="仅本地移动事件" rows={readyData.localOnly} />
            <EvidenceRows title="对账冲突" rows={readyData.conflicts} />
            <EvidenceRows title="仅 Garmin 事实" rows={readyData.garminOnly} />
            <EvidenceRows title="候选决策审计" rows={readyData.candidateDecisionAudits} />
          </div>

          <div className="mobile-reconcile-actions">
            <button type="button" onClick={handleApply} disabled={!readyData.annotationSuggestions.length || selectedIds.length === 0 || isApplying}>
              {isApplying ? '应用中' : '应用所选建议'}
            </button>
            {applyState.status === 'ready' ? (
              <span>
                {applyStatusText(applyState.data)}
              </span>
            ) : null}
            {applyState.status === 'error' ? <span>{applyState.message}</span> : null}
          </div>

          {applyState.status === 'ready' ? (
            <div className="mobile-reconcile-apply-details" aria-label="对账应用明细">
              {applyState.data.skippedSuggestionIds.length ? <span>已跳过:{applyState.data.skippedSuggestionIds.join(', ')}</span> : null}
              {applyState.data.missingSuggestionIds.length ? <span>未找到:{applyState.data.missingSuggestionIds.join(', ')}</span> : null}
            </div>
          ) : null}

          {applyState.status === 'ready' && applyState.data.annotations.length ? (
            <div className="mobile-reconcile-applied" aria-label="已应用批注">
              {applyState.data.annotations.map((annotation) => (
                <article key={annotation.id}>
                  <strong>{annotation.kind}</strong>
                  <span>{annotation.targetId}</span>
                </article>
              ))}
            </div>
          ) : null}

          {applyState.status === 'ready' && (applyState.data.decisionAudits ?? []).length ? (
            <div className="mobile-reconcile-applied" aria-label="已存档决策审计">
              {(applyState.data.decisionAudits ?? []).map((audit) => (
                <article key={compactValue(audit.id) ?? compactValue(audit.decisionId) ?? 'audit'}>
                  <strong>{compactValue(audit.classification) ?? 'audit'}</strong>
                  <span>{compactValue(audit.decisionId) ?? '-'}</span>
                </article>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  )
}

function applyStatusText(data: MobileReconciliationApplyResponse) {
  const parts = [`已应用 ${data.appliedCount} 条建议`]
  if (data.decisionAuditCount ?? 0) parts.push(`存档 ${data.decisionAuditCount ?? 0} 条审计`)
  if (data.skippedCount) parts.push(`跳过 ${data.skippedCount} 条`)
  return parts.join('，')
}

function EvidenceRows({ title, rows }: { title: string; rows: Array<Record<string, unknown>> }) {
  return (
    <section className="mobile-reconcile-evidence" aria-label={title}>
      <h3>{title}</h3>
      {rows.length ? (
        rows.map((row, index) => (
          <div className="report-row" key={`${title}-${rowLabel(row, String(index))}-${index}`}>
            <strong>{rowLabel(row, String(index))}</strong>
            <span>{rowValue(row)}</span>
          </div>
        ))
      ) : (
        <p>无</p>
      )}
    </section>
  )
}
