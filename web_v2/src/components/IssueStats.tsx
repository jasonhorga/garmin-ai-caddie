import type { HistoryStatsResponse } from '../types'
import { AggregateEvidence } from './AggregateEvidence'
import { SourceRefs } from './SourceRefs'
import { asNumber, asRows, asString, formatNumber, formatSigned, semanticClass } from './statsValues'

interface IssueStatsProps {
  data: HistoryStatsResponse
  onSelectRef?: (sourceRef: string) => void
}

function TrendContextFacts({ row }: { row: Record<string, unknown> }) {
  const baselineCount = asNumber(row.baselineCount)
  const recentCount = asNumber(row.recentCount)
  const baselineRate = asNumber(row.baselineRatePerRound)
  const recentRate = asNumber(row.recentRatePerRound)
  const actualImpact = asNumber(row.actualToParImpact)
  const actualCoverage = asRecord(row.actualImpactCoverage)
  const actualReady = asNumber(actualCoverage.ready)
  const actualTotal = asNumber(actualCoverage.total)

  return (
    <>
      {baselineCount !== null ? <span>baseline {formatNumber(baselineCount)}</span> : null}
      {recentCount !== null ? <span>recent {formatNumber(recentCount)}</span> : null}
      {baselineRate !== null || recentRate !== null ? (
        <span>
          rate {formatNumber(baselineRate)} -&gt; {formatNumber(recentRate)}/round
        </span>
      ) : null}
      {actualImpact !== null ? <span>{formatSigned(actualImpact)} actual to-par</span> : null}
      {actualReady !== null && actualTotal !== null ? <span>actual {formatNumber(actualReady)}/{formatNumber(actualTotal)}</span> : null}
      <AggregateEvidence row={row} showReason={false} />
    </>
  )
}

export function IssueStats({ data, onSelectRef }: IssueStatsProps) {
  const issueTrends = asRows(data.diagnosis?.issueTrends)
  const auditDiagnosis = asRecord(data.diagnosis?.decisionAuditTrends)
  const auditCounts = asRows(auditDiagnosis.classificationCounts)
  const auditDrivers = asRows(auditDiagnosis.recentCostDrivers)
  const auditCriteria = asRows(auditDiagnosis.criteriaBreakdown)
  const optionOutcomes = asRows(auditDiagnosis.optionOutcomes)

  return (
    <section className="stats-page" aria-label="Issue statistics">
      <div className="section-head stats-head">
        <div>
          <p className="eyebrow">Scoring Loss</p>
          <h1>Issue Stats</h1>
          <p>Detected issue counts with drill-down references.</p>
        </div>
      </div>
      {issueTrends.length > 0 ? (
        <div className="diagnosis-panel" aria-label="Issue trend diagnosis">
          <div className="section-head compact-head">
            <div>
              <p className="eyebrow">Trend Diagnosis</p>
              <h2>Recent Cost Drivers</h2>
            </div>
          </div>
          <div className="stats-list">
            {issueTrends.slice(0, 5).map((trend) => {
              const issue = asString(trend.issue) ?? 'unknown_issue'
              const estimated = asNumber(trend.estimatedStrokesLost)
              return (
                <article key={issue} className="stats-item diagnosis-item">
                  <div className="stats-item-main">
                    <h2>{issue}</h2>
                    <p>
                      <SourceRefs refs={trend.recentRefs ?? trend.sourceRefs} onSelectRef={onSelectRef} />
                    </p>
                  </div>
                  <div className="stats-item-facts">
                    {asString(trend.phase) ? <span>{asString(trend.phase)}</span> : null}
                    <TrendContextFacts row={trend} />
                    {asString(trend.direction) ? (
                      <span className={`semantic-chip ${semanticClass('trend', trend.direction)}`}>
                        {asString(trend.direction)}
                      </span>
                    ) : null}
                    <span>{estimated === null ? '- est. strokes' : `${estimated.toFixed(1)} est. strokes`}</span>
                  </div>
                  <strong className="stats-count">{formatSigned(trend.deltaCount)}</strong>
                </article>
              )
            })}
          </div>
        </div>
      ) : null}
      {auditCounts.length > 0 || auditDrivers.length > 0 ? (
        <div className="diagnosis-panel" aria-label="Caddie audit diagnosis">
          <div className="section-head compact-head">
            <div>
              <p className="eyebrow">Caddie Audit</p>
              <h2>Decision Loop</h2>
            </div>
          </div>
          <div className="stats-list">
            {auditCounts.slice(0, 4).map((row) => {
              const classification = asString(row.classification) ?? 'unknown'
              const pct = asNumber(row.pct)
              return (
                <article key={`audit-count-${classification}`} className="stats-item diagnosis-item">
                  <div className="stats-item-main">
                    <h2>{classification}</h2>
                    <p>
                      <SourceRefs refs={row.sourceRefs ?? row.refs} onSelectRef={onSelectRef} />
                    </p>
                  </div>
                  <div className="stats-item-facts">
                    <span className={`semantic-chip ${semanticClass('confidence', row.confidence)}`}>
                      {asString(row.confidence) ?? 'unknown'} confidence
                    </span>
                    <span>{pct === null ? '-%' : `${pct.toFixed(1)}%`}</span>
                  </div>
                  <strong className="stats-count">{formatNumber(row.count)}</strong>
                </article>
              )
            })}
            {auditDrivers.slice(0, 4).map((row) => {
              const classification = asString(row.classification) ?? 'unknown'
              const estimated = asNumber(row.estimatedStrokesLost)
              return (
                <article key={`audit-driver-${classification}`} className="stats-item diagnosis-item">
                  <div className="stats-item-main">
                    <h2>{classification}</h2>
                    <p>
                      <SourceRefs refs={row.recentRefs ?? row.sourceRefs} onSelectRef={onSelectRef} />
                    </p>
                  </div>
                  <div className="stats-item-facts">
                    {asString(row.phase) ? <span>{asString(row.phase)}</span> : null}
                    <TrendContextFacts row={row} />
                    {asString(row.direction) ? (
                      <span className={`semantic-chip ${semanticClass('trend', row.direction)}`}>
                        {asString(row.direction)}
                      </span>
                    ) : null}
                    <span>{estimated === null ? '- est. strokes' : `${estimated.toFixed(1)} est. strokes`}</span>
                  </div>
                  <strong className="stats-count">{formatSigned(row.deltaCount)}</strong>
                </article>
              )
            })}
            {auditCriteria.slice(0, 5).map((row) => {
              const label = asString(row.label) ?? 'criterion'
              const status = asString(row.status) ?? 'unknown'
              const pct = asNumber(row.pct)
              return (
                <article key={`audit-criterion-${label}-${status}`} className="stats-item diagnosis-item">
                  <div className="stats-item-main">
                    <h2>{label}</h2>
                    <p>
                      <SourceRefs refs={row.sourceRefs ?? row.refs} onSelectRef={onSelectRef} />
                    </p>
                  </div>
                  <div className="stats-item-facts">
                    <span className={`semantic-chip ${semanticClass('status', status)}`}>{status}</span>
                    <span>{pct === null ? '-%' : `${pct.toFixed(1)}% audits`}</span>
                    <AggregateEvidence row={row} showReason={false} showConfidence={false} />
                  </div>
                  <strong className="stats-count">{formatNumber(row.count)}</strong>
                </article>
              )
            })}
            {optionOutcomes.slice(0, 5).map((row) => {
              const selected = asString(row.selectedOptionId) ?? 'unknown'
              const actual = asString(row.actualOptionId) ?? 'unknown'
              const classification = asString(row.classification) ?? 'unknown'
              const pct = asNumber(row.pct)
              return (
                <article key={`audit-option-${selected}-${actual}-${classification}`} className="stats-item diagnosis-item">
                  <div className="stats-item-main">
                    <h2>
                      {selected} -&gt; {actual}
                    </h2>
                    <p>
                      <SourceRefs refs={row.sourceRefs ?? row.refs} onSelectRef={onSelectRef} />
                    </p>
                  </div>
                  <div className="stats-item-facts">
                    <span className={`semantic-chip ${semanticClass('confidence', row.confidence)}`}>
                      {asString(row.confidence) ?? 'unknown'} confidence
                    </span>
                    <span>{classification}</span>
                    <span>{pct === null ? '-%' : `${pct.toFixed(1)}% audits`}</span>
                  </div>
                  <strong className="stats-count">{formatNumber(row.count)}</strong>
                </article>
              )
            })}
          </div>
        </div>
      ) : null}
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
              <AggregateEvidence row={issue} showConfidence={false} />
            </div>
            <strong className="stats-count">{formatNumber(issue.count)}</strong>
          </article>
        ))}
      </div>
    </section>
  )
}

function asRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {}
}
