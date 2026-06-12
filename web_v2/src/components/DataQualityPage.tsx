import { coverageZh, qualityLabelZh } from '../zhLabels'
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
    ['行数', finding.rowCount],
    ['审计', finding.auditCount],
    ['部分', finding.partial],
  ].filter((entry): entry is [string, number] => asNumber(entry[1]) !== null)
  const nestedFacts = [
    ['球局报告', asRecord(finding.roundReports)],
    ['趋势报告', asRecord(finding.trendReports)],
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
          <span className="quality-detail-chip">缺失引用 {formatNumber(missingRefs.length)}</span>
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
    <section className="stats-page" aria-label="数据健康">
      <div className="section-head stats-head">
        <div>
          <p className="eyebrow">证据覆盖</p>
          <h1>数据健康</h1>
          <p>影响置信度与分析的覆盖缺口。</p>
        </div>
      </div>
      <div className="stats-list">
        {data.dataQuality.length === 0 ? (
          <article className="stats-empty">
            <h2>暂无数据健康发现</h2>
            <p>载入历史、击球、几何、天气或报告数据后，这里会列出覆盖缺口。</p>
          </article>
        ) : null}
        {data.dataQuality.map((finding) => (
          <article key={asString(finding.label) ?? 'quality'} className="stats-item">
            <div className="stats-item-main">
              <h2>{qualityLabelZh(asString(finding.label) ?? '未知来源')}</h2>
              <p>
                <SourceRefs refs={finding.sourceRefs ?? finding.refs} maxVisible={8} onSelectRef={onSelectRef} />
              </p>
            </div>
            <div className="stats-item-facts">
              <span className={`semantic-chip ${semanticClass('quality', finding.state)}`}>{coverageZh(asString(finding.state) ?? 'unknown')}</span>
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
