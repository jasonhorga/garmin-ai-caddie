import type { HistoryStatsResponse } from '../types'
import { SourceRefs } from './SourceRefs'
import { StatsQualityChips } from './StatsQualityChips'
import { asNumber, asRows, asString, formatNumber, formatSigned, semanticClass } from './statsValues'

interface CourseStatsProps {
  data: HistoryStatsResponse
  onSelectRef?: (sourceRef: string) => void
}

export function CourseStats({ data, onSelectRef }: CourseStatsProps) {
  const courses = data.courses
  const courseDistribution = asRows(data.courseDistribution)

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
        {courseDistribution.length === 0 ? (
          <article className="stats-empty">
            <h3>No course distribution yet</h3>
            <p>Distribution rows appear after round history has course keys.</p>
          </article>
        ) : (
          <div className="course-distribution-map">
            {courseDistribution.map((course) => {
              const location = formatLocation(course.location)
              return (
                <div key={asString(course.courseKey) ?? asString(course.courseName) ?? 'course'} className="course-distribution-row">
                  <span className="course-map-pin" aria-hidden="true" />
                  <div>
                    <strong>{asString(course.courseName) ?? asString(course.courseKey) ?? 'Unknown course'}</strong>
                    <span>{formatNumber(course.pct)}%</span>
                    <span>{formatNumber(course.roundCount)} rounds</span>
                    {location ? <em>{location}</em> : <em className="semantic-chip quality-missing">location missing</em>}
                  </div>
                  <SourceRefs refs={course.roundRefs ?? course.sourceRefs ?? course.roundIds} onSelectRef={onSelectRef} />
                </div>
              )
            })}
          </div>
        )}
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
          const direction = asString(recentForm.direction)
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
                {direction ? (
                  <span className={`semantic-chip ${semanticClass('trend', direction)}`}>
                    {direction} {formatSigned(recentForm.deltaAverage18)}
                  </span>
                ) : null}
                {asString(course.geometryCoverage) ? (
                  <span className={`semantic-chip ${semanticClass('quality', course.geometryCoverage)}`}>geometry {asString(course.geometryCoverage)}</span>
                ) : null}
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

function formatLocation(value: unknown): string | null {
  const location = asRecord(value)
  const latitude = asNumber(location.latitude)
  const longitude = asNumber(location.longitude)
  if (latitude === null || longitude === null) return null
  return `${latitude.toFixed(4)}, ${longitude.toFixed(4)}`
}
