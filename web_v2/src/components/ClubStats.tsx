import type { HistoryStatsResponse } from '../types'
import { AggregateEvidence } from './AggregateEvidence'
import { SourceRefs } from './SourceRefs'
import { StatsQualityChips } from './StatsQualityChips'
import { asNumber, asString, formatNumber, formatSigned, semanticClass } from './statsValues'

interface ClubStatsProps {
  data: HistoryStatsResponse
  onSelectRef?: (sourceRef: string) => void
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : null
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
        <StatsQualityChips data={data} labels={['shots', 'shot_rows']} />
      </div>
      <div className="stats-list">
        {data.clubs.length === 0 ? (
          <article className="stats-empty">
            <h2>No club samples yet</h2>
            <p>Shot data or manual club input is required before the club model is useful.</p>
          </article>
        ) : null}
        {data.clubs.map((club) => {
          const trend = asRecord(club.distanceTrend)
          const sampleQuality = asRecord(club.sampleQuality) ?? {}
          const consistency = asString(club.consistency)
          const trendDirection = asString(trend?.direction)
          const rawSampleCount = club.rawSampleCount ?? sampleQuality.rawSampleCount
          const validSampleCount = club.validSampleCount ?? sampleQuality.validSampleCount ?? club.sampleCount
          const invalidSampleCount = club.invalidSampleCount ?? sampleQuality.invalidSampleCount
          const outlierCount = club.outlierCount ?? sampleQuality.outlierCount
          const sampleConfidence = asString(sampleQuality.confidence)
          return (
            <article key={asString(club.club) ?? 'club'} className="stats-item">
              <div className="stats-item-main">
                <h2>{asString(club.club) ?? 'Unknown club'}</h2>
                <p>{formatNumber(club.sampleCount)} samples</p>
              </div>
              <div className="stats-item-facts">
                <span>median {formatNumber(club.median)}</span>
                <span>p10 {formatNumber(club.p10)}</span>
                <span>p90 {formatNumber(club.p90)}</span>
                <span>dispersion {formatNumber(club.dispersionRange)}</span>
                <span>max {formatNumber(club.max)}</span>
                {asNumber(rawSampleCount) !== null ? (
                  <span>valid {formatNumber(validSampleCount)}/{formatNumber(rawSampleCount)}</span>
                ) : null}
                {(asNumber(invalidSampleCount) ?? 0) > 0 ? (
                  <span className="semantic-chip quality-partial">invalid {formatNumber(invalidSampleCount)}</span>
                ) : null}
                {(asNumber(outlierCount) ?? 0) > 0 ? (
                  <span className="semantic-chip quality-partial">outlier {formatNumber(outlierCount)}</span>
                ) : null}
                {sampleConfidence ? (
                  <span className={`semantic-chip ${semanticClass('confidence', sampleConfidence)}`}>
                    sample {sampleConfidence}
                  </span>
                ) : null}
                {consistency ? (
                  <span className={`semantic-chip ${semanticClass('consistency', consistency)}`}>
                    {consistency} consistency
                  </span>
                ) : null}
                {trendDirection ? (
                  <span className={`semantic-chip ${semanticClass('trend', trendDirection)}`}>
                    trend {formatSigned(trend?.deltaMedian)} {trendDirection}
                  </span>
                ) : null}
                <span className={`semantic-chip ${semanticClass('confidence', club.confidence)}`}>
                  {asString(club.confidence) ?? 'unknown'} confidence
                </span>
                <AggregateEvidence row={club} showConfidence={false} />
              </div>
              <p className="stats-refs">
                <SourceRefs refs={club.validShotRefs ?? club.shotRefs ?? club.roundRefs ?? club.roundIds} onSelectRef={onSelectRef} />
                <SourceRefs refs={club.invalidShotRefs} onSelectRef={onSelectRef} />
                <SourceRefs refs={club.outlierShotRefs} onSelectRef={onSelectRef} />
              </p>
            </article>
          )
        })}
      </div>
    </section>
  )
}
