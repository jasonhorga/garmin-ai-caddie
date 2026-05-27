import type { HistoryStatsResponse } from '../types'
import { AggregateEvidence } from './AggregateEvidence'
import { SourceRefs } from './SourceRefs'
import { asNumber, asString, formatNumber, semanticClass } from './statsValues'

interface DataQualityPageProps {
  data: HistoryStatsResponse
  onSelectRef?: (sourceRef: string) => void
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : null
}

function asRefList(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String).filter(Boolean) : []
}

function QualityDetailRows({
  finding,
  onSelectRef,
}: {
  finding: Record<string, unknown>
  onSelectRef?: (sourceRef: string) => void
}) {
  const scalarFacts = [
    ['rows', finding.rowCount],
    ['audits', finding.auditCount],
    ['partial', finding.partial],
  ].filter((entry): entry is [string, number] => asNumber(entry[1]) !== null)
  const nestedFacts = [
    ['round reports', asRecord(finding.roundReports)],
    ['trend reports', asRecord(finding.trendReports)],
  ].filter((entry): entry is [string, Record<string, unknown>] => entry[1] !== null)
  const missingRefs = asRefList(finding.missingRefs)

  if (scalarFacts.length === 0 && nestedFacts.length === 0 && missingRefs.length === 0) return null

  return (
    <div className="quality-detail-list">
      {scalarFacts.map(([label, value]) => (
        <span key={label} className="quality-detail-chip">
          {label} {formatNumber(value)}
        </span>
      ))}
      {missingRefs.length ? (
        <div className="quality-detail-row">
          <span className="quality-detail-chip">missing refs {formatNumber(missingRefs.length)}</span>
          <SourceRefs refs={missingRefs} maxVisible={8} onSelectRef={onSelectRef} />
        </div>
      ) : null}
      {nestedFacts.map(([label, row]) => (
        <div key={label} className="quality-detail-row">
          <span className="quality-detail-chip">
            {label} {formatNumber(row.ready)}/{formatNumber(row.total)}
          </span>
          <SourceRefs refs={row.missingRefs} maxVisible={8} onSelectRef={onSelectRef} />
        </div>
      ))}
    </div>
  )
}

export function DataQualityPage({ data, onSelectRef }: DataQualityPageProps) {
  return (
    <section className="stats-page" aria-label="Data quality">
      <div className="section-head stats-head">
        <div>
          <p className="eyebrow">Evidence Coverage</p>
          <h1>Data Quality</h1>
          <p>Coverage gaps that affect confidence and analysis.</p>
        </div>
      </div>
      <div className="stats-list">
        {data.dataQuality.length === 0 ? (
          <article className="stats-empty">
            <h2>No data quality findings yet</h2>
            <p>Coverage findings will appear after history, shot, geometry, weather, or report data is loaded.</p>
          </article>
        ) : null}
        {data.dataQuality.map((finding) => (
          <article key={asString(finding.label) ?? 'quality'} className="stats-item">
            <div className="stats-item-main">
              <h2>{asString(finding.label) ?? 'Unknown source'}</h2>
              <p>
                <SourceRefs refs={finding.sourceRefs ?? finding.refs} maxVisible={8} onSelectRef={onSelectRef} />
              </p>
            </div>
            <div className="stats-item-facts">
              <span className={`semantic-chip ${semanticClass('quality', finding.state)}`}>{asString(finding.state) ?? 'unknown'}</span>
              <span>
                {formatNumber(finding.ready)}/{formatNumber(finding.total)}
              </span>
              <AggregateEvidence row={finding} />
            </div>
            <QualityDetailRows finding={finding} onSelectRef={onSelectRef} />
          </article>
        ))}
      </div>
    </section>
  )
}
