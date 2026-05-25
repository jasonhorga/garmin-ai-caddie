import type { HistoryStatsResponse } from '../types'
import { asString, formatNumber, formatRefs } from './statsValues'

interface DataQualityPageProps {
  data: HistoryStatsResponse
}

export function DataQualityPage({ data }: DataQualityPageProps) {
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
        {data.dataQuality.map((finding) => (
          <article key={asString(finding.label) ?? 'quality'} className="stats-item">
            <div className="stats-item-main">
              <h2>{asString(finding.label) ?? 'Unknown source'}</h2>
              <p>{formatRefs(finding.refs)}</p>
            </div>
            <div className="stats-item-facts">
              <span>{asString(finding.state) ?? 'unknown'}</span>
              <span>
                {formatNumber(finding.ready)}/{formatNumber(finding.total)}
              </span>
            </div>
          </article>
        ))}
      </div>
    </section>
  )
}
