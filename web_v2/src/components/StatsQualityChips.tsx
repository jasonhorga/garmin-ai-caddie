import type { HistoryStatsResponse } from '../types'
import { asString, formatNumber, semanticClass } from './statsValues'

interface StatsQualityChipsProps {
  data: HistoryStatsResponse
  labels: string[]
}

export function StatsQualityChips({ data, labels }: StatsQualityChipsProps) {
  const findings = data.dataQuality.filter((finding) => {
    const label = asString(finding.label)
    return label !== null && labels.includes(label)
  })

  if (findings.length === 0) return null

  return (
    <div className="stats-quality-chips" aria-label="Relevant data quality">
      {findings.map((finding, index) => {
        const label = asString(finding.label) ?? 'quality'
        const state = asString(finding.state) ?? 'unknown'
        return (
          <span key={`${label}-${index}`} className={`semantic-chip ${semanticClass('quality', state)}`}>
            {label} {state} {qualityRatio(finding)}
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
