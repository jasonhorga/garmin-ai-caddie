import type { DataQualityBadge } from '../types'

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
        <span key={`${badge.label}-${badge.value}`} className={`quality-chip quality-${badge.state}`} title={badge.reason}>
          <span>{badge.label}</span>
          <b>{badge.value}</b>
        </span>
      ))}
    </div>
  )
}
