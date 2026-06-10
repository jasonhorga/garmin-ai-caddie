import type { HistoryStatsResponse } from '../types'
import { AggregateEvidence } from './AggregateEvidence'
import { SourceRefs } from './SourceRefs'
import { StatsQualityChips } from './StatsQualityChips'
import { asNumber, asRows, asString, formatNumber, formatSigned, semanticClass } from './statsValues'

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
          <h2>Hole Stats</h2>
          <p>Repeated hole outcomes and source scorecard refs.</p>
        </div>
        <StatsQualityChips data={data} labels={['geometry']} />
      </div>
      <div className="stats-list">
        {data.holes.length === 0 ? (
          <article className="stats-empty">
            <h2>No hole stats yet</h2>
            <p>Hole-level scorecards are required before repeated patterns can be shown.</p>
          </article>
        ) : null}
        {data.holes.map((hole) => {
          const distribution = asRows(hole.scoreDistribution).filter((row) => (asNumber(row.count) ?? 0) > 0)
          const repeatedIssues = asRows(hole.repeatedIssues)
          return (
            <article key={`${asString(hole.courseKey) ?? 'course'}-${formatNumber(hole.hole)}`} className="stats-item hole-stats-item">
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
              {distribution.length || repeatedIssues.length ? (
                <div className="hole-breakdown">
                  {distribution.length ? (
                    <div className="hole-distribution" aria-label={`Hole ${formatNumber(hole.hole)} score distribution`}>
                      {distribution.map((row) => (
                        <span key={asString(row.key) ?? asString(row.label) ?? 'bucket'} className={`hole-distribution-bucket score-${asString(row.className) ?? 'missing'}`}>
                          <strong>{asString(row.label) ?? 'Outcome'}</strong>
                          <b>{formatNumber(row.count)}</b>
                          <em>{formatNumber(row.pct)}%</em>
                          <AggregateEvidence row={row} />
                          <SourceRefs refs={row.holeRefs ?? row.refs ?? row.sourceRefs} onSelectRef={onSelectRef} />
                        </span>
                      ))}
                    </div>
                  ) : null}
                  {repeatedIssues.length ? (
                    <div className="hole-issues" aria-label={`Hole ${formatNumber(hole.hole)} repeated issues`}>
                      {repeatedIssues.slice(0, 3).map((issue) => (
                        <div key={`${asString(issue.issue) ?? 'issue'}-${asString(issue.source) ?? 'source'}`} className="hole-issue-row">
                          <span>
                            <strong>{asString(issue.issue) ?? 'Unknown issue'}</strong>
                            {asString(issue.phase) ? <b>{asString(issue.phase)}</b> : null}
                            <em>{formatNumber(issue.count)}</em>
                          </span>
                          <SourceRefs refs={issue.sourceRefs ?? issue.refs} onSelectRef={onSelectRef} />
                        </div>
                      ))}
                    </div>
                  ) : null}
                </div>
              ) : null}
            </article>
          )
        })}
      </div>
    </section>
  )
}
