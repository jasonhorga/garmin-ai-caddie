import type { DataQualityBadge } from '../types'
import { coverageZh } from '../zhLabels'

interface DataQualityChipsProps {
  badges: DataQualityBadge[]
}

export function DataQualityChips({ badges }: DataQualityChipsProps) {
  if (badges.length === 0) {
    return null
  }

  return (
    <div className="quality-row">
      {badges.map((badge) => (
        <span
          key={`${badge.label}-${badge.value}`}
          className={`quality-chip quality-${badge.state}`}
          title={badge.reason}
          aria-label={`${badge.label}: ${coverageZh(badge.value)}, ${badge.state} - ${badge.reason}`}
        >
          <span>{badge.label}</span>
          <b>{coverageZh(badge.value)}</b>
        </span>
      ))}
    </div>
  )
}
