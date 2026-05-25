import type { HistoryStatsResponse } from '../types'
import { asString, formatNumber, formatRefs, formatSigned } from './statsValues'

interface HoleStatsProps {
  data: HistoryStatsResponse
}

export function HoleStats({ data }: HoleStatsProps) {
  return (
    <section className="stats-page" aria-label="Hole statistics">
      <div className="section-head stats-head">
        <div>
          <p className="eyebrow">Hole Patterns</p>
          <h1>Hole Stats</h1>
          <p>Repeated hole outcomes and source scorecard refs.</p>
        </div>
      </div>
      <div className="stats-list">
        {data.holes.map((hole) => (
          <article key={`${asString(hole.courseKey) ?? 'course'}-${formatNumber(hole.hole)}`} className="stats-item">
            <div className="stats-item-main">
              <h2>Hole {formatNumber(hole.hole)}</h2>
              <p>{asString(hole.courseKey) ?? 'unknown'}</p>
            </div>
            <div className="stats-item-facts">
              <span>{formatNumber(hole.sampleCount)} samples</span>
              <span>{formatSigned(hole.averageToPar)} avg</span>
              <span>{formatSigned(hole.worstToPar)} worst</span>
            </div>
            <p className="stats-refs">{formatRefs(hole.refs)}</p>
          </article>
        ))}
      </div>
    </section>
  )
}
