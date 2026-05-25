import type { HistoryStatsResponse } from '../types'
import { asString, formatNumber, formatRefs } from './statsValues'

interface IssueStatsProps {
  data: HistoryStatsResponse
}

export function IssueStats({ data }: IssueStatsProps) {
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
              <p>{formatRefs(issue.refs)}</p>
            </div>
            <strong className="stats-count">{formatNumber(issue.count)}</strong>
          </article>
        ))}
      </div>
    </section>
  )
}
