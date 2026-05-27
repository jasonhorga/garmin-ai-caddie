import type { CSSProperties } from 'react'
import type { AnnotationRecord, AnnotationTargetType, HistoryRoundDetailResponse, ReviewReportResponse } from '../types'
import { SourceRefs } from './SourceRefs'

export type HistoryRoundDetailPanelState =
  | { status: 'idle' }
  | { status: 'loading'; roundRef: string }
  | { status: 'error'; roundRef: string; message: string }
  | { status: 'ready'; data: HistoryRoundDetailResponse }

interface HistoryRoundDetailPanelProps {
  state: HistoryRoundDetailPanelState
  reportState?: { status: 'idle' } | { status: 'loading' } | { status: 'error'; message: string } | { status: 'ready'; data: ReviewReportResponse }
  onSelectRef?: (sourceRef: string) => void
  onRetryRound?: (roundRef: string) => void
  onCreateAnnotationForRound?: (target: { targetType: AnnotationTargetType; targetId: string }) => void
  onLoadRoundReport?: (roundRef: string) => void
  onGenerateRoundReport?: (roundRef: string) => void
}

function valueText(value: unknown): string {
  if (value === null || value === undefined) return '-'
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return JSON.stringify(value)
}

function compactValue(value: unknown): string | null {
  if (typeof value === 'string') return value.trim() ? value : null
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return null
}

function toParText(value: unknown): string {
  if (typeof value !== 'number') return '-'
  if (value > 0) return `+${value}`
  return String(value)
}

function annotationSummary(record: AnnotationRecord): string {
  const from = compactValue(record.payload.from)
  const to = compactValue(record.payload.to)
  if (from && to) return `${from} -> ${to}`
  const text = compactValue(record.payload.text) ?? compactValue(record.payload.note)
  if (text) return text
  return valueText(record.payload)
}

function RoundFacts({ data }: { data: HistoryRoundDetailResponse }) {
  const round = data.round ?? {}
  const coverage = typeof round.coverage === 'object' && round.coverage !== null ? round.coverage as Record<string, unknown> : {}
  const facts: Array<[string, unknown]> = [
    ['Score', round.score],
    ['To par', toParText(round.toPar)],
    ['Holes', round.holesScored ?? round.holesCompleted],
    ['Shots', round.shotCount],
    ['Scorecard', coverage.scorecard],
    ['Shot data', coverage.shots],
    ['Putts', coverage.putts],
    ['Confidence', round.confidence],
  ]

  return (
    <section className="round-detail-facts" aria-label="Round detail facts">
      {facts.map(([label, value]) => (
        <div key={label}>
          <span>{label}</span>
          <b>{valueText(value)}</b>
        </div>
      ))}
    </section>
  )
}

function ScorecardGrid({ data, onSelectRef }: { data: HistoryRoundDetailResponse; onSelectRef?: (sourceRef: string) => void }) {
  if (data.scorecard.length === 0) return null
  return (
    <section className="round-detail-section" aria-label="Scorecard">
      <div className="section-head">
        <div>
          <h3>Scorecard</h3>
          <p>Hole-by-hole score, putts, GIR, fairway, and source refs.</p>
        </div>
      </div>
      <div className="round-detail-scorecard" style={{ '--round-detail-holes': Math.max(data.scorecard.length, 1) } as CSSProperties}>
        {data.scorecard.map((cell) => {
          const content = (
            <>
              <span>H{cell.hole}</span>
              <b>{cell.score ?? '-'}</b>
              <small>
                p{cell.par ?? '-'} / {toParText(cell.toPar)}
              </small>
              <em>{cell.putts === null ? 'putts -' : `${cell.putts} putts`}</em>
            </>
          )
          return onSelectRef ? (
            <button
              key={cell.holeRef}
              type="button"
              className={`round-detail-cell score-${cell.className}`}
              onClick={() => onSelectRef(cell.holeRef)}
              aria-label={`Open hole ${cell.hole} detail ${cell.holeRef}`}
            >
              {content}
            </button>
          ) : (
            <div key={cell.holeRef} className={`round-detail-cell score-${cell.className}`}>
              {content}
            </div>
          )
        })}
      </div>
    </section>
  )
}

function PhaseSummary({ rows }: { rows: Array<Record<string, unknown>> }) {
  if (rows.length === 0) return null
  return (
    <section className="round-detail-section" aria-label="Phase summary">
      <h3>Phase Summary</h3>
      <div className="round-phase-grid">
        {rows.map((row) => (
          <article key={valueText(row.phase)} className="round-phase-card">
            <span>{valueText(row.phase)}</span>
            <b>{valueText(row.primary)}</b>
            <small>{valueText(row.state)}</small>
          </article>
        ))}
      </div>
    </section>
  )
}

function HoleDetails({ rows, onSelectRef }: { rows: Array<Record<string, unknown>>; onSelectRef?: (sourceRef: string) => void }) {
  if (rows.length === 0) return null
  return (
    <section className="round-detail-section" aria-label="Hole details">
      <h3>Hole Details</h3>
      <div className="round-hole-table">
        {rows.map((row) => (
          <div key={valueText(row.holeRef)} className="round-hole-row">
            <div>
              <span>H{valueText(row.hole)}</span>
              <b>{valueText(row.score)} / {toParText(row.toPar)}</b>
            </div>
            <div>
              <span>Putts</span>
              <b>{valueText(row.putts)}</b>
            </div>
            <div>
              <span>GIR</span>
              <b>{valueText(row.gir)}</b>
            </div>
            <div>
              <span>Fairway</span>
              <b>{valueText(row.fairway)}</b>
            </div>
            <div className="round-hole-sources">
              <span>Shots</span>
              <SourceRefs refs={row.shotRefs} maxVisible={3} onSelectRef={onSelectRef} />
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

function RelatedSources({ data, onSelectRef }: { data: HistoryRoundDetailResponse; onSelectRef?: (sourceRef: string) => void }) {
  const groups = [
    ['Rounds', data.relatedRefs.roundRefs],
    ['Holes', data.relatedRefs.holeRefs],
    ['Shots', data.relatedRefs.shotRefs],
    ['Raw', data.relatedRefs.sourceRefs ?? []],
  ] as const
  if (!groups.some(([, refs]) => refs.length > 0)) return null
  return (
    <section className="round-detail-section" aria-label="Related round sources">
      <h3>Related Sources</h3>
      <div className="drilldown-rows">
        {groups.map(([label, refs]) => (
          <div key={label} className="drilldown-row">
            <span>{label}</span>
            <b>
              <SourceRefs refs={refs} maxVisible={5} onSelectRef={onSelectRef} />
            </b>
          </div>
        ))}
      </div>
    </section>
  )
}

function MissingDataRows({ rows }: { rows: Array<Record<string, unknown>> }) {
  if (rows.length === 0) return null
  return (
    <section className="round-detail-section" aria-label="Round detail missing data">
      <h3>Missing Data</h3>
      <div className="drilldown-rows">
        {rows.map((row, index) => (
          <div key={`${valueText(row.label)}-${index}`} className="drilldown-row">
            <span>{valueText(row.label)}</span>
            <b>{valueText(row.state ?? row.reason)}</b>
          </div>
        ))}
      </div>
    </section>
  )
}

function AnnotationRows({ title, rows }: { title: string; rows: AnnotationRecord[] }) {
  if (rows.length === 0) return null
  return (
    <section className="round-detail-section" aria-label={title}>
      <h3>{title}</h3>
      <div className="drilldown-rows">
        {rows.map((row) => (
          <div key={row.id} className="drilldown-row">
            <span>{row.kind}</span>
            <b>{annotationSummary(row)}</b>
          </div>
        ))}
      </div>
    </section>
  )
}

function RoundAiReview({
  roundRef,
  reportState,
  onLoadRoundReport,
  onGenerateRoundReport,
  onSelectRef,
}: {
  roundRef: string
  reportState?: HistoryRoundDetailPanelProps['reportState']
  onLoadRoundReport?: (roundRef: string) => void
  onGenerateRoundReport?: (roundRef: string) => void
  onSelectRef?: (sourceRef: string) => void
}) {
  if (!onLoadRoundReport && !onGenerateRoundReport && (!reportState || reportState.status === 'idle')) return null
  const loadedReport =
    reportState?.status === 'ready' &&
    reportState.data.kind === 'round' &&
    reportState.data.subjectId === roundRef
      ? reportState.data
      : null

  return (
    <section className="round-detail-section round-ai-review" aria-label="Round AI review">
      <div className="section-head">
        <div>
          <h3>AI Review</h3>
          <p>Fact-bound round narrative with source refs and missing-data limits.</p>
        </div>
        <div className="button-row">
          {onLoadRoundReport ? (
            <button type="button" onClick={() => onLoadRoundReport(roundRef)}>
              Load AI Review
            </button>
          ) : null}
          {onGenerateRoundReport ? (
            <button type="button" onClick={() => onGenerateRoundReport(roundRef)}>
              Generate AI Review
            </button>
          ) : null}
        </div>
      </div>
      {reportState?.status === 'loading' ? <p>Loading AI review</p> : null}
      {reportState?.status === 'error' ? <p>{reportState.message}</p> : null}
      {loadedReport ? (
        <div className="round-ai-review-body">
          <div className="round-ai-review-meta">
            <span>{loadedReport.provider}</span>
            <span>{loadedReport.model}</span>
            <span>{loadedReport.confidence} confidence</span>
          </div>
          <p>{loadedReport.narrative}</p>
          <SourceRefs refs={loadedReport.sourceRefs} onSelectRef={onSelectRef} />
        </div>
      ) : null}
    </section>
  )
}

export function HistoryRoundDetailPanel({
  state,
  reportState,
  onSelectRef,
  onRetryRound,
  onCreateAnnotationForRound,
  onLoadRoundReport,
  onGenerateRoundReport,
}: HistoryRoundDetailPanelProps) {
  if (state.status === 'idle') return null

  if (state.status === 'loading') {
    return (
      <section className="panel round-detail-panel" aria-live="polite">
        <h2>Round Review</h2>
        <p>Loading {state.roundRef}</p>
      </section>
    )
  }

  if (state.status === 'error') {
    return (
      <section className="panel round-detail-panel" aria-live="polite">
        <h2>Round Review</h2>
        <p>{state.roundRef}</p>
        <p>{state.message}</p>
        {onRetryRound ? (
          <button type="button" className="drilldown-action-button" onClick={() => onRetryRound(state.roundRef)}>
            Retry round review
          </button>
        ) : null}
      </section>
    )
  }

  const data = state.data
  const canAnnotate = data.found && Boolean(data.roundRef.trim()) && Boolean(onCreateAnnotationForRound)
  return (
    <section className="panel round-detail-panel" aria-live="polite">
      <div className="drilldown-title-row">
        <div>
          <p className="eyebrow">Round Scorecard</p>
          <h2>{data.found ? 'Round Review' : 'Round Unavailable'}</h2>
          <p>{data.title}</p>
        </div>
        <div className="drilldown-meta">
          <span>{data.roundRef}</span>
          <span>{data.found ? 'found' : 'not found'}</span>
          {canAnnotate ? (
            <button
              type="button"
              className="drilldown-action-button"
              onClick={() => onCreateAnnotationForRound?.({ targetType: 'round', targetId: data.roundRef })}
              aria-label={`Add correction for round ${data.roundRef}`}
            >
              Add Correction
            </button>
          ) : null}
        </div>
      </div>

      {data.found ? <RoundFacts data={data} /> : null}
      <ScorecardGrid data={data} onSelectRef={onSelectRef} />
      {data.found ? (
        <RoundAiReview
          roundRef={data.roundRef}
          reportState={reportState}
          onLoadRoundReport={onLoadRoundReport}
          onGenerateRoundReport={onGenerateRoundReport}
          onSelectRef={onSelectRef}
        />
      ) : null}
      <PhaseSummary rows={data.phaseSummary} />
      <HoleDetails rows={data.holeDetails} onSelectRef={onSelectRef} />
      <RelatedSources data={data} onSelectRef={onSelectRef} />
      <AnnotationRows title="Round Annotations" rows={data.annotations ?? []} />
      <AnnotationRows title="Applied Corrections" rows={data.corrections ?? []} />
      <MissingDataRows rows={data.missingData} />
    </section>
  )
}
