import { useEffect, useState, type FormEvent } from 'react'
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

function formatCount(value: number, noun: string, plural = `${noun}s`) {
  return `${value} ${value === 1 ? noun : plural}`
}

function compactValue(value: unknown) {
  if (typeof value === 'string') return value
  if (typeof value === 'number') return String(value)
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  return null
}

function suggestionSummary(suggestion: MobileReconciliationSuggestion) {
  const from = compactValue(suggestion.payload.from)
  const to = compactValue(suggestion.payload.to)
  if (from && to) return `${from} -> ${to}`
  const strokes = compactValue(suggestion.payload.strokes)
  if (strokes) return `${strokes} penalty`
  const sourceEventId = compactValue(suggestion.payload.sourceEventId)
  return sourceEventId ? `event ${sourceEventId}` : suggestion.kind
}

export function MobileReconciliationPanel({
  state,
  applyState,
  onLoad,
  onApply,
  defaultRoundId = '900001',
}: MobileReconciliationPanelProps) {
  const [roundId, setRoundId] = useState(defaultRoundId)
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const readyData = state.status === 'ready' ? state.data : null
  const isApplying = applyState.status === 'applying'

  useEffect(() => {
    if (!readyData) return
    setRoundId(readyData.roundId)
    setSelectedIds(readyData.annotationSuggestions.map((suggestion) => suggestion.id))
  }, [readyData])

  function handleLoad(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const trimmed = roundId.trim()
    if (!trimmed) return
    onLoad(trimmed)
  }

  function toggleSuggestion(id: string) {
    setSelectedIds((current) => (current.includes(id) ? current.filter((item) => item !== id) : [...current, id]))
  }

  function handleApply() {
    if (!readyData || selectedIds.length === 0 || isApplying) return
    void onApply(readyData.roundId, selectedIds)
  }

  return (
    <section className="mobile-reconciliation-panel" aria-label="Mobile reconciliation">
      <div className="section-head stats-head">
        <div>
          <p className="eyebrow">Offline Input</p>
          <h2>Mobile Reconciliation</h2>
          <p>Review iOS and Watch event logs against synced Garmin facts, then apply selected corrections as auditable annotations.</p>
        </div>
      </div>

      <form className="mobile-reconcile-form" aria-label="Mobile reconciliation lookup" onSubmit={handleLoad}>
        <label htmlFor="mobile-reconcile-round-id">Round ID</label>
        <input
          id="mobile-reconcile-round-id"
          value={roundId}
          onChange={(event) => setRoundId(event.target.value)}
          spellCheck={false}
        />
        <button type="submit" disabled={!roundId.trim() || state.status === 'loading'}>
          {state.status === 'loading' ? 'Reviewing events' : 'Review offline events'}
        </button>
      </form>

      {state.status === 'idle' ? (
        <article className="stats-empty">
          <h2>No reconciliation loaded</h2>
          <p>Select a round after mobile events sync back from iOS or Watch.</p>
        </article>
      ) : null}

      {state.status === 'loading' ? (
        <article className="stats-empty">
          <h2>Loading reconciliation</h2>
          <p>{state.roundId}</p>
        </article>
      ) : null}

      {state.status === 'error' ? (
        <article className="stats-empty">
          <h2>Reconciliation unavailable</h2>
          <p>{state.message}</p>
        </article>
      ) : null}

      {readyData ? (
        <div className="mobile-reconcile-body">
          <div className="mobile-reconcile-summary" aria-label="Reconciliation summary">
            <span>{formatCount(readyData.summary.eventCount, 'event')}</span>
            <span>{formatCount(readyData.summary.matchedCount, 'match', 'matches')}</span>
            <span>{formatCount(readyData.summary.localOnlyCount, 'local-only event')}</span>
            <span>{formatCount(readyData.summary.garminOnlyCount, 'Garmin-only fact')}</span>
            <span>{formatCount(readyData.summary.conflictCount, 'conflict')}</span>
            <span>{formatCount(readyData.summary.annotationSuggestionCount, 'suggestion')}</span>
          </div>

          <div className="mobile-reconcile-suggestions" aria-label="Reconciliation suggestions">
            {readyData.annotationSuggestions.length === 0 ? (
              <article className="stats-empty">
                <h2>No reconciliation suggestions</h2>
                <p>Local events match the synced Garmin facts, or there is not enough evidence to propose a correction.</p>
              </article>
            ) : null}

            {readyData.annotationSuggestions.map((suggestion) => (
              <article key={suggestion.id} className="mobile-reconcile-suggestion">
                <label>
                  <input
                    type="checkbox"
                    checked={selectedIds.includes(suggestion.id)}
                    onChange={() => toggleSuggestion(suggestion.id)}
                    aria-label={`Select suggestion ${suggestion.id}`}
                  />
                  <span>{suggestion.kind}</span>
                </label>
                <div>
                  <strong>{suggestion.targetId}</strong>
                  <p>{suggestion.reason}</p>
                  <p>{suggestionSummary(suggestion)}</p>
                </div>
                <span className={`semantic-chip confidence-${suggestion.confidence}`}>{suggestion.confidence}</span>
              </article>
            ))}
          </div>

          <div className="mobile-reconcile-actions">
            <button type="button" onClick={handleApply} disabled={!readyData.annotationSuggestions.length || selectedIds.length === 0 || isApplying}>
              {isApplying ? 'Applying suggestions' : 'Apply selected suggestions'}
            </button>
            {applyState.status === 'ready' ? (
              <span>
                Applied {applyState.data.appliedCount} suggestions
                {applyState.data.skippedCount ? `, skipped ${applyState.data.skippedCount}` : ''}
              </span>
            ) : null}
            {applyState.status === 'error' ? <span>{applyState.message}</span> : null}
          </div>

          {applyState.status === 'ready' && applyState.data.annotations.length ? (
            <div className="mobile-reconcile-applied" aria-label="Applied annotations">
              {applyState.data.annotations.map((annotation) => (
                <article key={annotation.id}>
                  <strong>{annotation.kind}</strong>
                  <span>{annotation.targetId}</span>
                </article>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  )
}
