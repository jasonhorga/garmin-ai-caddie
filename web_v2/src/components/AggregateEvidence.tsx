import { useDiagnostics } from '../diagnosticsContext'
import { confidenceZh } from '../zhLabels'
import { asNumber, asRows, asString, formatNumber, semanticClass } from './statsValues'

interface AggregateEvidenceProps {
  row: Record<string, unknown>
  showConfidence?: boolean
  showReason?: boolean
}

function coverageText(value: unknown): string | null {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) return null
  const coverage = value as Record<string, unknown>
  const ready = asNumber(coverage.ready)
  const total = asNumber(coverage.total)
  const pct = asNumber(coverage.pct)
  if (ready === null || total === null) return null
  return `覆盖 ${formatNumber(ready)}/${formatNumber(total)}${pct === null ? '' : ` ${formatNumber(pct)}%`}`
}

export function AggregateEvidence({ row, showConfidence = true, showReason = true }: AggregateEvidenceProps) {
  const diagnostics = useDiagnostics()
  // Coverage / 信心 / 缺失 chips are ETL diagnostics — owner diagnostics mode only.
  if (!diagnostics) return null
  const coverage = coverageText(row.coverage)
  const confidence = asString(row.confidence)
  const reason = asString(row.reason) ?? asString(row.detail)
  const missingData = asRows(row.missingData)

  if (!coverage && (!showConfidence || !confidence) && (!showReason || !reason) && missingData.length === 0) return null

  return (
    <span className="aggregate-meta" aria-label="聚合证据">
      {coverage ? <span className="fact-chip muted">{coverage}</span> : null}
      {showConfidence && confidence ? (
        <span className={`fact-chip ${semanticClass('confidence', confidence)}`}>信心{confidenceZh(confidence)}</span>
      ) : null}
      {showReason && reason ? <span className="fact-chip muted">{reason}</span> : null}
      {missingData.length > 0 ? <span className="fact-chip muted">缺失 {formatNumber(missingData.length)}</span> : null}
    </span>
  )
}
