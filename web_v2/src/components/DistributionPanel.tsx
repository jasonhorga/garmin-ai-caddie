import type { ScoreDistribution } from '../types'

interface DistributionPanelProps {
  distribution: ScoreDistribution
}

function barWidth(count: number, maxCount: number) {
  if (count === 0) {
    return '0%'
  }

  return `${Math.max(6, (count / maxCount) * 100)}%`
}

export function DistributionPanel({ distribution }: DistributionPanelProps) {
  const maxFamily = Math.max(...distribution.families.map((family) => family.count), 1)
  const maxBucket = Math.max(...distribution.histogram.map((bucket) => bucket.count), 1)

  return (
    <section className="panel distribution-panel" aria-label="Score distribution">
      <div className="section-head">
        <div>
          <h2>Score Distribution</h2>
          <p>
            {distribution.total} eighteen-hole rounds - avg {distribution.average ?? '-'}
          </p>
        </div>
      </div>
      <div className="distribution-grid">
        <div className="pyramid">
          {distribution.families.map((family) => (
            <div key={family.label} className="pyramid-row">
              <span>{family.label}</span>
              <div className="pyramid-track">
                <i className={`score-${family.className}`} style={{ width: barWidth(family.count, maxFamily) }} />
              </div>
              <b>{family.count}</b>
            </div>
          ))}
        </div>
        <div className="histogram">
          {distribution.histogram.map((bucket) => (
            <div key={bucket.label} className="histogram-row">
              <span>{bucket.label}</span>
              <i style={{ width: barWidth(bucket.count, maxBucket) }} />
              <b>{bucket.count}</b>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
