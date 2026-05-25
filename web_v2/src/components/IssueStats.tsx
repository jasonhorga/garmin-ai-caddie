import type { HistoryStatsResponse } from '../types'
import { SourceRefs } from './SourceRefs'
import { asString, formatNumber } from './statsValues'

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
        {data.issues.map((issue) => (
          <article key={asString(issue.issue) ?? 'issue'} className="stats-item">
            <div className="stats-item-main">
              <h2>{asString(issue.issue) ?? 'Unknown issue'}</h2>
              <p>
                <SourceRefs refs={issue.sourceRefs ?? issue.refs} onSelectRef={onSelectRef} />
              </p>
            </div>
            <strong className="stats-count">{formatNumber(issue.count)}</strong>
          </article>
        ))}
      </div>
    </section>
  )
}
