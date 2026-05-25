import type { HistoryStatsResponse } from '../types'
import { asString, formatNumber, formatRefs } from './statsValues'

interface CourseStatsProps {
  data: HistoryStatsResponse
}

export function CourseStats({ data }: CourseStatsProps) {
  const courses = data.courses

  return (
    <section className="stats-page" aria-label="Course statistics">
      <div className="section-head stats-head">
        <div>
          <p className="eyebrow">Course History</p>
          <h1>Course Stats</h1>
          <p>Course-specific scoring, form, and source rounds.</p>
        </div>
      </div>
      <div className="stats-list">
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
            </div>
            <p className="stats-refs">{formatRefs(course.roundIds)}</p>
          </article>
        ))}
      </div>
    </section>
  )
}
