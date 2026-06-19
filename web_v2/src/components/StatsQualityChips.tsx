import type { HistoryStatsResponse } from '../types'
import { useDiagnostics } from '../diagnosticsContext'
import { coverageZh, qualityLabelZh } from '../zhLabels'
import { asString, formatNumber, semanticClass } from './statsValues'

interface StatsQualityChipsProps {
  data: HistoryStatsResponse
  labels: string[]
}

export function StatsQualityChips({ data, labels }: StatsQualityChipsProps) {
  const diagnostics = useDiagnostics()
  // Data-coverage chips (geometry N/total …) are ETL diagnostics — owner only.
  if (!diagnostics) return null
  const findings = data.dataQuality.filter((finding) => {
    const label = asString(finding.label)
    return label !== null && labels.includes(label)
  })

  if (findings.length === 0) return null

  return (
    <div className="stats-quality-chips" aria-label="数据覆盖情况">
      {findings.map((finding, index) => {
        const label = asString(finding.label) ?? 'quality'
        const state = asString(finding.state) ?? 'unknown'
        return (
          <span key={`${label}-${index}`} className={`semantic-chip ${semanticClass('quality', state)}`}>
            {qualityLabelZh(label)} {coverageZh(state)} {qualityRatio(finding)}
          </span>
        )
      })}
    </div>
  )
}

function qualityRatio(finding: Record<string, unknown>): string {
  const value = asString(finding.value)
  if (value) return value

  return `${formatNumber(finding.ready)}/${formatNumber(finding.total)}`
}
