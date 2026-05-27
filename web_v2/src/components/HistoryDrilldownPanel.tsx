import type { AnnotationRecord, HistoryDrilldownResponse } from '../types'
import { SourceRefs } from './SourceRefs'

export type HistoryDrilldownPanelState =
  | { status: 'idle' }
  | { status: 'loading'; sourceRef: string }
  | { status: 'error'; sourceRef: string; message: string }
  | { status: 'ready'; data: HistoryDrilldownResponse }

interface HistoryDrilldownPanelProps {
  state: HistoryDrilldownPanelState
  onSelectRef?: (sourceRef: string) => void
}

function valueText(value: unknown): string {
  if (value === null || value === undefined) return '-'
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return JSON.stringify(value)
}

function entries(record: Record<string, unknown> | null): Array<[string, unknown]> {
  if (!record) return []
  return Object.entries(record).filter(([, value]) => value !== null && value !== undefined)
}

function compactPayloadValue(value: unknown): string | null {
  if (typeof value === 'string') return value.trim() ? value : null
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return null
}

function annotationSummary(record: AnnotationRecord): string {
  const { payload } = record
  const from = compactPayloadValue(payload.from)
  const to = compactPayloadValue(payload.to)
  if (from && to) return `${from} -> ${to}`

  const tag = compactPayloadValue(payload.tag)
  if (tag) return tag

  const text = compactPayloadValue(payload.text) ?? compactPayloadValue(payload.note)
  if (text) return text

  const reason = compactPayloadValue(payload.reason)
  const strokes = compactPayloadValue(payload.strokes)
  if (reason && strokes) return `${strokes}: ${reason}`
  if (reason) return reason

  const rating = compactPayloadValue(payload.rating)
  if (rating) return rating

  return valueText(payload)
}

function DetailRows({ title, record }: { title: string; record: Record<string, unknown> | null }) {
  const rows = entries(record)
  if (rows.length === 0) return null

  return (
    <section className="drilldown-block" aria-label={title}>
      <h3>{title}</h3>
      <div className="drilldown-rows">
        {rows.map(([key, value]) => (
          <div key={key} className="drilldown-row">
            <span>{key}</span>
            <b>{valueText(value)}</b>
          </div>
        ))}
      </div>
    </section>
  )
}

function MissingDataRows({ rows }: { rows: Array<Record<string, unknown>> }) {
  if (rows.length === 0) return null

  return (
    <section className="drilldown-block" aria-label="Missing data">
      <h3>Missing Data</h3>
      <div className="drilldown-rows">
        {rows.map((row, index) => (
          <div key={`${valueText(row.label)}-${index}`} className="drilldown-row">
            <span>{valueText(row.label)}</span>
            <b>{valueText(row.state ?? row.reason ?? row.value)}</b>
          </div>
        ))}
      </div>
    </section>
  )
}

function AnnotationRows({ title, rows }: { title: string; rows: AnnotationRecord[] }) {
  if (rows.length === 0) return null

  return (
    <section className="drilldown-block" aria-label={title}>
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

function RelatedRefs({
  relatedRefs,
  onSelectRef,
}: {
  relatedRefs: HistoryDrilldownResponse['relatedRefs']
  onSelectRef?: (sourceRef: string) => void
}) {
  const groups = [
    ['Rounds', relatedRefs.roundRefs],
    ['Holes', relatedRefs.holeRefs],
    ['Shots', relatedRefs.shotRefs],
  ] as const
  if (!groups.some(([, refs]) => refs.length > 0)) return null

  return (
    <section className="drilldown-block" aria-label="Related sources">
      <h3>Related Sources</h3>
      <div className="drilldown-rows">
        {groups.map(([label, refs]) => (
          <div key={label} className="drilldown-row">
            <span>{label}</span>
            <b>
              <SourceRefs refs={refs} onSelectRef={onSelectRef} />
            </b>
          </div>
        ))}
      </div>
    </section>
  )
}

export function HistoryDrilldownPanel({ state, onSelectRef }: HistoryDrilldownPanelProps) {
  if (state.status === 'idle') return null

  if (state.status === 'loading') {
    return (
      <section className="panel drilldown-panel" aria-live="polite">
        <h2>Source Detail</h2>
        <p>Loading {state.sourceRef}</p>
      </section>
    )
  }

  if (state.status === 'error') {
    return (
      <section className="panel drilldown-panel" aria-live="polite">
        <h2>Source Detail</h2>
        <p>{state.sourceRef}</p>
        <p>{state.message}</p>
      </section>
    )
  }

  const data = state.data
  return (
    <section className="panel drilldown-panel" aria-live="polite">
      <div className="drilldown-title-row">
        <div>
          <p className="eyebrow">Evidence Drill-Down</p>
          <h2>{data.found ? 'Source Detail' : 'Source Unavailable'}</h2>
          <p>{data.title}</p>
        </div>
        <div className="drilldown-meta">
          <span>{data.ref}</span>
          <span>{data.refType}</span>
          <span>{data.found ? 'found' : 'not found'}</span>
        </div>
      </div>

      <div className="drilldown-grid">
        <DetailRows title="Round" record={data.round} />
        <DetailRows title="Hole" record={data.hole} />
        <DetailRows title="Shot" record={data.shot} />
        <DetailRows title="Source Fields" record={data.sourceFields} />
      </div>

      <RelatedRefs relatedRefs={data.relatedRefs} onSelectRef={onSelectRef} />
      <AnnotationRows title="Manual Annotations" rows={data.annotations ?? []} />
      <AnnotationRows title="Applied Corrections" rows={data.corrections ?? []} />
      <MissingDataRows rows={data.missingData} />
    </section>
  )
}
