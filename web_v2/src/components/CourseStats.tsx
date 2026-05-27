import type { HistoryStatsResponse } from '../types'
import { AggregateEvidence } from './AggregateEvidence'
import { CourseDistributionMap } from './CourseDistributionMap'
import { SourceRefs } from './SourceRefs'
import { StatsQualityChips } from './StatsQualityChips'
import { asString, formatNumber, formatSigned, semanticClass } from './statsValues'

interface CourseStatsProps {
  data: HistoryStatsResponse
  onSelectRef?: (sourceRef: string) => void
}

export function CourseStats({ data, onSelectRef }: CourseStatsProps) {
  const courses = data.courses

  return (
    <section className="stats-page" aria-label="Course statistics">
      <div className="section-head stats-head">
        <div>
          <p className="eyebrow">Course History</p>
          <h1>Course Stats</h1>
          <p>Course-specific scoring, form, and source rounds.</p>
        </div>
        <StatsQualityChips data={data} labels={['geometry']} />
      </div>
      <section className="panel compact-panel" aria-label="Course distribution">
        <div className="section-head">
          <div>
            <h2>Course Distribution</h2>
            <p>Round mix by course with location evidence and drill-down refs.</p>
          </div>
        </div>
        <CourseDistributionMap rows={data.courseDistribution} onSelectRef={onSelectRef} />
      </section>
      <div className="stats-list">
        {courses.length === 0 ? (
          <article className="stats-empty">
            <h2>No course stats yet</h2>
            <p>Sync Garmin rounds or switch to fixture mode to populate course distribution.</p>
          </article>
        ) : null}
        {courses.map((course) => {
          const recentForm = asRecord(course.recentForm)
          const teeDirection = asRecord(course.teeDirection)
          const approachMiss = asRecord(course.approachMiss)
          const direction = asString(recentForm.direction)
          const dominantMiss = asString(teeDirection.dominantMiss)
          const dominantApproachMiss = asString(approachMiss.dominantMiss)
          return (
            <article key={asString(course.courseKey) ?? asString(course.courseName) ?? 'course'} className="stats-item">
              <div className="stats-item-main">
                <h2>{asString(course.courseName) ?? 'Unknown course'}</h2>
                <p>{asString(course.courseKey) ?? 'unknown'}</p>
              </div>
              <div className="stats-item-facts" aria-label={`${asString(course.courseName) ?? 'course'} facts`}>
                <span>{formatNumber(course.roundCount)} rounds</span>
                <span>avg {formatNumber(course.average18)}</span>
                <span>best {formatNumber(course.bestScore)}</span>
                <span>worst {formatNumber(course.worstScore)}</span>
                {recentForm.recentAverage18 !== undefined ? <span>recent {formatNumber(recentForm.recentAverage18)}</span> : null}
                {teeDirection.hitPct !== undefined ? <span>FIR {formatNumber(teeDirection.hitPct)}%</span> : null}
                {dominantMiss && dominantMiss !== 'unknown' ? (
                  <span className={`semantic-chip ${semanticClass('tee', dominantMiss)}`}>
                    tee {dominantMiss} {formatNumber(teeDirection[`${dominantMiss}Pct`])}%
                  </span>
                ) : null}
                {approachMiss.girPct !== undefined ? <span>GIR {formatNumber(approachMiss.girPct)}%</span> : null}
                {dominantApproachMiss && dominantApproachMiss !== 'unknown' ? (
                  <span className={`semantic-chip ${semanticClass('approach', dominantApproachMiss)}`}>
                    approach {dominantApproachMiss} {formatNumber(approachMiss[`${dominantApproachMiss}Pct`])}%
                  </span>
                ) : null}
                {direction ? (
                  <span className={`semantic-chip ${semanticClass('trend', direction)}`}>
                    {direction} {formatSigned(recentForm.deltaAverage18)}
                  </span>
                ) : null}
                {asString(course.geometryCoverage) ? (
                  <span className={`semantic-chip ${semanticClass('quality', course.geometryCoverage)}`}>geometry {asString(course.geometryCoverage)}</span>
                ) : null}
                <AggregateEvidence row={course} />
              </div>
              <p className="stats-refs">
                <SourceRefs refs={course.roundRefs ?? course.roundIds} onSelectRef={onSelectRef} />
              </p>
            </article>
          )
        })}
      </div>
    </section>
  )
}

function asRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {}
}
