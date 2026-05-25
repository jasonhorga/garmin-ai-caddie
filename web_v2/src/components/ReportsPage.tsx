import { useMemo, useState } from 'react'
import type { HistoryStatsResponse, ReviewReportResponse } from '../types'

interface ReportsPageProps {
  stats: HistoryStatsResponse
  reportState: { status: 'idle' } | { status: 'loading' } | { status: 'error'; message: string } | { status: 'ready'; data: ReviewReportResponse }
  onLoadTrend: (period: string) => void
  onGenerateTrend: (period: string) => void
  onLoadRound: (roundId: string) => void
  onGenerateRound: (roundId: string) => void
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
}: ReportsPageProps) {
  const trendOptions = useMemo(() => buildTrendOptions(stats), [stats])
  const roundOptions = useMemo(() => buildRoundOptions(stats), [stats])
  const [trendPeriod, setTrendPeriod] = useState(trendOptions[0]?.id ?? 'recent_10')
  const [roundId, setRoundId] = useState(roundOptions[0]?.id ?? '')

  return (
    <section className="reports-workspace">
      <div className="section-head">
        <div>
          <p className="eyebrow">Fact-bound review</p>
          <h1>Reports</h1>
          <p>Stored and generated round or trend reviews, tied to source facts and missing data.</p>
        </div>
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

        <ReportDetail state={reportState} />
      </div>
    </section>
  )
}

function ReportDetail({ state }: { state: ReportsPageProps['reportState'] }) {
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
      <p className="report-narrative">{report.narrative}</p>

      <div className="report-evidence-grid">
        <section aria-label="Report facts">
          <h3>Facts</h3>
          {report.factsUsed.map((fact, index) => (
            <div className="report-row" key={`${String(fact.label)}-${index}`}>
              <strong>{String(fact.label ?? 'fact')}</strong>
              <span>{String(fact.source ?? 'source')}</span>
            </div>
          ))}
        </section>
        <section aria-label="Report missing data">
          <h3>Missing Data</h3>
          {report.missingData.length ? (
            report.missingData.map((item, index) => (
              <div className="report-row" key={`${String(item.label)}-${index}`}>
                <strong>{String(item.label ?? 'missing')}</strong>
                <span>{String(item.state ?? item.reason ?? 'needs review')}</span>
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
