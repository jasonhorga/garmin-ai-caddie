import type { HistoryStatsResponse } from '../types'
import { SourceRefs } from './SourceRefs'
import { asString, formatNumber, semanticClass } from './statsValues'

interface IssueStatsProps {
  data: HistoryStatsResponse
  onSelectRef?: (sourceRef: string) => void
}

export function IssueStats({ data, onSelectRef }: IssueStatsProps) {
  return (
    <section className="stats-page" aria-label="Issue statistics">
      <div className="section-head stats-head">
        <div>
          <p className="eyebrow">Scoring Loss</p>
          <h1>Issue Stats</h1>
          <p>Detected issue counts with drill-down references.</p>
        </div>
      </div>
      <div className="stats-list">
        {data.issues.length === 0 ? (
          <article className="stats-empty">
            <h2>No recurring issues yet</h2>
            <p>Deterministic, AI-suggested, and manual issue tags will appear here after analysis.</p>
          </article>
        ) : null}
        {data.issues.map((issue) => (
          <article key={asString(issue.issue) ?? 'issue'} className="stats-item">
            <div className="stats-item-main">
              <h2>{asString(issue.issue) ?? 'Unknown issue'}</h2>
              <p>
                <SourceRefs refs={issue.sourceRefs ?? issue.refs} onSelectRef={onSelectRef} />
              </p>
            </div>
            <div className="stats-item-facts">
              {asString(issue.phase) ? <span>{asString(issue.phase)}</span> : null}
              {asString(issue.source) ? <span>{asString(issue.source)}</span> : null}
              <span className={`semantic-chip ${semanticClass('confidence', issue.confidence)}`}>
                {asString(issue.confidence) ?? 'unknown'} confidence
              </span>
            </div>
            <strong className="stats-count">{formatNumber(issue.count)}</strong>
          </article>
        ))}
      </div>
    </section>
  )
}
