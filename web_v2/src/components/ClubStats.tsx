import type { HistoryStatsResponse } from '../types'
import { SourceRefs } from './SourceRefs'
import { asString, formatNumber } from './statsValues'

interface ClubStatsProps {
  data: HistoryStatsResponse
  onSelectRef?: (sourceRef: string) => void
}

export function ClubStats({ data, onSelectRef }: ClubStatsProps) {
  return (
    <section className="stats-page" aria-label="Club statistics">
      <div className="section-head stats-head">
        <div>
          <p className="eyebrow">Club Model</p>
          <h1>Club Stats</h1>
          <p>Personal distance samples, dispersion range, and confidence.</p>
        </div>
      </div>
      <div className="stats-list">
        {data.clubs.map((club) => (
          <article key={asString(club.club) ?? 'club'} className="stats-item">
            <div className="stats-item-main">
              <h2>{asString(club.club) ?? 'Unknown club'}</h2>
              <p>{formatNumber(club.sampleCount)} samples</p>
            </div>
            <div className="stats-item-facts">
              <span>median {formatNumber(club.median)}</span>
              <span>p10 {formatNumber(club.p10)}</span>
              <span>p90 {formatNumber(club.p90)}</span>
              <span>max {formatNumber(club.max)}</span>
              <span>{asString(club.confidence) ?? 'unknown'} confidence</span>
            </div>
            <p className="stats-refs">
              <SourceRefs refs={club.shotRefs ?? club.roundRefs ?? club.roundIds} onSelectRef={onSelectRef} />
            </p>
          </article>
        ))}
      </div>
    </section>
  )
}
