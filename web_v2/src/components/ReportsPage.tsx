import { useMemo, useState } from 'react'
import type { HistoryStatsResponse, ReviewReportResponse } from '../types'
import { SourceRefs } from './SourceRefs'
import { StatsQualityChips } from './StatsQualityChips'

interface ReportsPageProps {
  stats: HistoryStatsResponse
  reportState: { status: 'idle' } | { status: 'loading' } | { status: 'error'; message: string } | { status: 'ready'; data: ReviewReportResponse }
  onLoadTrend: (period: string) => void
  onGenerateTrend: (period: string) => void
  onLoadRound: (roundId: string) => void
  onGenerateRound: (roundId: string) => void
  onSelectRef?: (sourceRef: string) => void
}

interface Option {
  id: string
  label: string
}

export function ReportsPage({
  stats,
  reportState,
  onLoadTrend,
  onGenerateTrend,
  onLoadRound,
  onGenerateRound,
  onSelectRef,
}: ReportsPageProps) {
  const trendOptions = useMemo(() => buildTrendOptions(stats), [stats])
  const roundOptions = useMemo(() => buildRoundOptions(stats), [stats])
  const [trendPeriod, setTrendPeriod] = useState(trendOptions[0]?.id ?? 'recent_10')
  const [roundId, setRoundId] = useState(roundOptions[0]?.id ?? '')

  return (
    <section className="reports-workspace">
      <div className="section-head stats-head">
        <div>
          <p className="eyebrow">Fact-bound review</p>
          <h1>Reports</h1>
          <p>Stored and generated round or trend reviews, tied to source facts and missing data.</p>
        </div>
        <StatsQualityChips data={stats} labels={['reports']} />
      </div>

      <div className="reports-layout">
        <section className="report-controls" aria-label="Report controls">
          <div className="field-row">
            <label htmlFor="trend-period">Trend period</label>
            <select id="trend-period" value={trendPeriod} onChange={(event) => setTrendPeriod(event.target.value)}>
              {trendOptions.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          <div className="button-row">
            <button type="button" onClick={() => onLoadTrend(trendPeriod)}>
              Load trend report
            </button>
            <button type="button" onClick={() => onGenerateTrend(trendPeriod)}>
              Generate trend report
            </button>
          </div>

          <div className="field-row">
            <label htmlFor="round-id">Round</label>
            <select id="round-id" value={roundId} onChange={(event) => setRoundId(event.target.value)}>
              {roundOptions.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          <div className="button-row">
            <button type="button" disabled={!roundId} onClick={() => onLoadRound(roundId)}>
              Load round report
            </button>
            <button type="button" disabled={!roundId} onClick={() => onGenerateRound(roundId)}>
              Generate round report
            </button>
          </div>
        </section>

        <ReportDetail state={reportState} onSelectRef={onSelectRef} />
      </div>
    </section>
  )
}

function ReportDetail({ state, onSelectRef }: { state: ReportsPageProps['reportState']; onSelectRef?: (sourceRef: string) => void }) {
  if (state.status === 'loading') {
    return (
      <section className="report-detail" aria-label="Report detail">
        <h2>Loading report</h2>
      </section>
    )
  }

  if (state.status === 'error') {
    return (
      <section className="report-detail" aria-label="Report detail">
        <h2>Report unavailable</h2>
        <p>{state.message}</p>
      </section>
    )
  }

  if (state.status === 'idle') {
    return (
      <section className="report-detail" aria-label="Report detail">
        <h2>No report loaded</h2>
        <p>Select a trend or round report to inspect the fact-bound review.</p>
      </section>
    )
  }

  const report = state.data
  return (
    <section className="report-detail" aria-label="Report detail">
      <div className="report-title-row">
        <div>
          <p className="eyebrow">{report.kind}</p>
          <h2>{report.provider}</h2>
        </div>
        <span className={`confidence-pill ${report.confidence}`}>{report.confidence} confidence</span>
      </div>
      <section className="report-identity" aria-label="Report identity">
        <span className="fact-chip muted">subject</span>
        <span className="fact-chip">{report.subjectId}</span>
        <span className="fact-chip muted">model</span>
        <span className="fact-chip">{report.model}</span>
        <SourceRefs refs={report.sourceRefs} onSelectRef={onSelectRef} />
      </section>
      <p className="report-narrative">{report.narrative}</p>

      <div className="report-evidence-grid">
        <section aria-label="Report facts">
          <h3>Facts</h3>
          {report.factsUsed.map((fact, index) => (
            <div className="report-row" key={`${String(fact.label)}-${index}`}>
              <div className="report-row-main">
                <strong>{String(fact.label ?? 'fact')}</strong>
                <span>{String(fact.source ?? 'source')}</span>
                <FactValue value={fact.value} />
                <ReportMetadata row={fact} confidenceLabel="fact confidence" />
              </div>
              <SourceRefs refs={refsForFact(fact)} onSelectRef={onSelectRef} />
            </div>
          ))}
        </section>
        <section aria-label="Report missing data">
          <h3>Missing Data</h3>
          {report.missingData.length ? (
            report.missingData.map((item, index) => (
              <div className="report-row" key={`${String(item.label)}-${index}`}>
                <div className="report-row-main">
                  <strong>{String(item.label ?? 'missing')}</strong>
                  <span>{String(item.state ?? item.reason ?? 'needs review')}</span>
                  <ReportMetadata row={item} confidenceLabel="missing confidence" />
                </div>
                <SourceRefs refs={refsForFact(item)} onSelectRef={onSelectRef} />
              </div>
            ))
          ) : (
            <p>None</p>
          )}
        </section>
      </div>
    </section>
  )
}

function ReportMetadata({ row, confidenceLabel }: { row: Record<string, unknown>; confidenceLabel: string }) {
  const coverage = metadataCoverage(row.coverage)
  const confidence = typeof row.confidence === 'string' ? row.confidence : null
  if (!coverage && !confidence) return null

  return (
    <div className="report-metadata">
      {coverage ? <span className="fact-chip muted">{coverage}</span> : null}
      {confidence ? <span className="fact-chip muted">{`${confidence} ${confidenceLabel}`}</span> : null}
    </div>
  )
}

function metadataCoverage(value: unknown): string | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const row = value as Record<string, unknown>
  const ready = typeof row.ready === 'number' ? row.ready : null
  const total = typeof row.total === 'number' ? row.total : null
  const pct = typeof row.pct === 'number' ? row.pct : null
  if (ready === null || total === null) return null
  return `coverage ${ready}/${total}${pct === null ? '' : ` ${pct}%`}`
}

function FactValue({ value }: { value: unknown }) {
  if (value === undefined || value === null) return null
  if (Array.isArray(value)) return <FactArray rows={value} />
  if (typeof value === 'object') return <FactObject value={value as Record<string, unknown>} />
  return <div className="fact-value">{formatFactPrimitive(value)}</div>
}

function FactArray({ rows }: { rows: unknown[] }) {
  const displayRows = rows.slice(0, 4)
  return (
    <div className="fact-array">
      {displayRows.map((row, index) => {
        if (row && typeof row === 'object' && !Array.isArray(row)) {
          return <FactObject key={factObjectKey(row as Record<string, unknown>, index)} value={row as Record<string, unknown>} compact />
        }
        return (
          <span className="fact-chip" key={`${String(row)}-${index}`}>
            {formatFactPrimitive(row)}
          </span>
        )
      })}
      {rows.length > displayRows.length ? <span className="fact-chip muted">+{rows.length - displayRows.length} more</span> : null}
    </div>
  )
}

function FactObject({ value, compact = false }: { value: Record<string, unknown>; compact?: boolean }) {
  const entries = Object.entries(value).filter(([, item]) => isRenderableFactPrimitive(item))
  if (!entries.length) return null
  return (
    <div className={compact ? 'fact-object compact' : 'fact-object'}>
      {entries.map(([key, item]) => (
        <span className="fact-chip" key={key}>
          {formatFactPair(key, item)}
        </span>
      ))}
    </div>
  )
}

function isRenderableFactPrimitive(value: unknown): boolean {
  return value === null || ['string', 'number', 'boolean'].includes(typeof value)
}

function formatFactPair(key: string, value: unknown): string {
  const rendered = formatFactPrimitive(value, key)
  if (key === 'course') return rendered
  return `${key} ${rendered}`
}

function formatFactPrimitive(value: unknown, key = ''): string {
  if (value === null) return 'none'
  if (typeof value === 'number') {
    if (key === 'toPar' && value > 0) return `+${value}`
    return String(value)
  }
  if (typeof value === 'boolean') return value ? 'yes' : 'no'
  return String(value)
}

function factObjectKey(value: Record<string, unknown>, index: number): string {
  const ref = value.holeRef ?? value.shotRef ?? value.roundRef ?? value.id
  return `${String(ref ?? 'row')}-${index}`
}

function buildTrendOptions(stats: HistoryStatsResponse): Option[] {
  const options: Option[] = [{ id: 'recent_10', label: 'Recent 10' }]
  for (const row of asRecordArray(stats.time.byQuarter)) {
    const key = String(row.key ?? '')
    if (key) options.push({ id: `quarter:${key}`, label: `Q ${key}` })
  }
  for (const row of asRecordArray(stats.time.byYear)) {
    const key = String(row.key ?? row.year ?? '')
    if (key) options.push({ id: `year:${key}`, label: `Year ${key}` })
  }
  return options
}

function buildRoundOptions(stats: HistoryStatsResponse): Option[] {
  const drillDown = stats.drillDown
  const refs = Array.isArray(drillDown.roundRefs)
    ? drillDown.roundRefs
    : Array.isArray(drillDown.roundIds)
      ? drillDown.roundIds
      : []
  return refs.map((ref) => ({ id: String(ref), label: String(ref) }))
}

function asRecordArray(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object') : []
}

function refsForFact(fact: Record<string, unknown>): string[] {
  return collectRefs(fact)
}

function collectRefs(value: unknown): string[] {
  const refs: string[] = []
  const seen = new Set<string>()

  function add(ref: unknown) {
    const normalized = String(ref ?? '').trim()
    if (!normalized || seen.has(normalized)) return
    seen.add(normalized)
    refs.push(normalized)
  }

  function walk(current: unknown, keyHint = '') {
    if (Array.isArray(current)) {
      if (isRefKey(keyHint)) {
        current.forEach(add)
        return
      }
      current.forEach((item) => walk(item))
      return
    }

    if (typeof current === 'string' && isRefKey(keyHint)) {
      add(current)
      return
    }

    if (current === null || typeof current !== 'object') return

    Object.entries(current).forEach(([key, item]) => {
      if (isRefKey(key)) {
        if (Array.isArray(item)) item.forEach(add)
        else add(item)
      } else {
        walk(item, key)
      }
    })
  }

  walk(value)
  return refs
}

function isRefKey(key: string) {
  return /^(refs|sourceRefs|roundRefs|holeRefs|shotRefs|roundIds|roundRef|holeRef|shotRef)$/i.test(key)
}
