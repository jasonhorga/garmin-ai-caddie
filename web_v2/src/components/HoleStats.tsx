import type { HistoryStatsResponse } from '../types'
import { SourceRefs } from './SourceRefs'
import { asString, formatNumber, formatSigned, semanticClass } from './statsValues'

interface HoleStatsProps {
  data: HistoryStatsResponse
  onSelectRef?: (sourceRef: string) => void
}

export function HoleStats({ data, onSelectRef }: HoleStatsProps) {
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
        {data.holes.length === 0 ? (
          <article className="stats-empty">
            <h2>No hole stats yet</h2>
            <p>Hole-level scorecards are required before repeated patterns can be shown.</p>
          </article>
        ) : null}
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
              {asString(hole.geometryCoverage) ? (
                <span className={`semantic-chip ${semanticClass('quality', hole.geometryCoverage)}`}>geometry {asString(hole.geometryCoverage)}</span>
              ) : null}
            </div>
            <p className="stats-refs">
              <SourceRefs refs={hole.holeRefs ?? hole.refs} onSelectRef={onSelectRef} />
            </p>
          </article>
        ))}
      </div>
    </section>
  )
}
