import type { HistoryStatsResponse } from '../types'
import { SourceRefs } from './SourceRefs'
import { StatsQualityChips } from './StatsQualityChips'
import { asString, formatNumber, semanticClass } from './statsValues'

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
      <div className="stats-list">
        {courses.length === 0 ? (
          <article className="stats-empty">
            <h2>No course stats yet</h2>
            <p>Sync Garmin rounds or switch to fixture mode to populate course distribution.</p>
          </article>
        ) : null}
        {courses.map((course) => (
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
              {asString(course.geometryCoverage) ? (
                <span className={`semantic-chip ${semanticClass('quality', course.geometryCoverage)}`}>geometry {asString(course.geometryCoverage)}</span>
              ) : null}
            </div>
            <p className="stats-refs">
              <SourceRefs refs={course.roundRefs ?? course.roundIds} onSelectRef={onSelectRef} />
            </p>
          </article>
        ))}
      </div>
    </section>
  )
}
