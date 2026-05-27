import type { HistoryStatsResponse } from '../types'
import { AggregateEvidence } from './AggregateEvidence'
import { SourceRefs } from './SourceRefs'
import { asString, formatNumber, semanticClass } from './statsValues'

interface DataQualityPageProps {
  data: HistoryStatsResponse
  onSelectRef?: (sourceRef: string) => void
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
                <SourceRefs refs={finding.sourceRefs ?? finding.refs} onSelectRef={onSelectRef} />
              </p>
            </div>
            <div className="stats-item-facts">
              <span className={`semantic-chip ${semanticClass('quality', finding.state)}`}>{asString(finding.state) ?? 'unknown'}</span>
              <span>
                {formatNumber(finding.ready)}/{formatNumber(finding.total)}
              </span>
              <AggregateEvidence row={finding} />
            </div>
          </article>
        ))}
      </div>
    </section>
  )
}
