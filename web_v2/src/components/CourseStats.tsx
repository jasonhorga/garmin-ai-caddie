import type { HistoryStatsResponse } from '../types'
import { AggregateEvidence } from './AggregateEvidence'
import { CourseDistributionMap } from './CourseDistributionMap'
import { SourceRefs } from './SourceRefs'
import { StatsQualityChips } from './StatsQualityChips'
import { asRows, asString, formatNumber, formatSigned, semanticClass } from './statsValues'

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
          const difficultyAdjusted = asRecord(course.difficultyAdjusted)
          const difficultyCoverage = asRecord(difficultyAdjusted.coverage ?? recentForm.difficultyAdjustedCoverage)
          const issueProfile = asRows(course.issueProfile).slice(0, 4)
          const toughestHoles = asRows(course.toughestHoles).slice(0, 4)
          const direction = asString(recentForm.direction)
          const differentialDirection = asString(recentForm.differentialDirection)
          const dominantMiss = asString(teeDirection.dominantMiss)
          const dominantApproachMiss = asString(approachMiss.dominantMiss)
          const courseName = asString(course.courseName) ?? 'course'
          const hasDifficultyAdjusted = Object.keys(difficultyAdjusted).length > 0
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
                {course.averageDifferential !== undefined ? <span>avg diff {formatNumber(course.averageDifferential)}</span> : null}
                {course.bestDifferential !== undefined ? <span>best diff {formatNumber(course.bestDifferential)}</span> : null}
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
                {differentialDirection ? (
                  <span className={`semantic-chip ${semanticClass('trend', differentialDirection)}`}>
                    diff {differentialDirection} {formatSigned(recentForm.deltaAverageDifferential)}
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
              {issueProfile.length || toughestHoles.length || hasDifficultyAdjusted ? (
                <div className="course-breakdown">
                  {hasDifficultyAdjusted ? (
                    <section aria-label={`${courseName} difficulty adjusted`}>
                      <h3>Difficulty Adjusted</h3>
                      <div className="course-insight-list">
                        <div className="course-insight-row">
                          <span>
                            <strong>Rating / slope coverage</strong>
                            <b>
                              {formatNumber(difficultyAdjusted.ratedRoundCount)} / {formatNumber(difficultyAdjusted.eligibleRoundCount)} rounds
                            </b>
                            <em>avg diff {formatNumber(difficultyAdjusted.averageDifferential)}</em>
                            <em>best {formatNumber(difficultyAdjusted.bestDifferential)}</em>
                            {difficultyCoverage.ready !== undefined ? (
                              <em>
                                coverage {formatNumber(difficultyCoverage.ready)}/{formatNumber(difficultyCoverage.total)} {formatNumber(difficultyCoverage.pct)}%
                              </em>
                            ) : null}
                          </span>
                          <SourceRefs refs={difficultyAdjusted.roundRefs ?? difficultyAdjusted.sourceRefs} onSelectRef={onSelectRef} />
                        </div>
                        {Array.isArray(difficultyAdjusted.missingRoundRefs) && difficultyAdjusted.missingRoundRefs.length > 0 ? (
                          <div className="course-insight-row">
                            <span>
                              <strong>Missing rating / slope</strong>
                              <b>{formatNumber(difficultyAdjusted.missingRoundRefs.length)} rounds</b>
                            </span>
                            <SourceRefs refs={difficultyAdjusted.missingRoundRefs} onSelectRef={onSelectRef} />
                          </div>
                        ) : null}
                      </div>
                    </section>
                  ) : null}
                  {issueProfile.length ? (
                    <section aria-label={`${courseName} issue profile`}>
                      <h3>Course Issue Profile</h3>
                      <div className="course-insight-list">
                        {issueProfile.map((issue) => (
                          <div key={`${asString(issue.issue) ?? 'issue'}-${asString(issue.source) ?? 'source'}`} className="course-insight-row">
                            <span>
                              <strong>{asString(issue.issue) ?? 'Unknown issue'}</strong>
                              {asString(issue.phase) ? <b>{asString(issue.phase)}</b> : null}
                              <em>{formatNumber(issue.affectedHoleCount)} holes</em>
                              <em>{formatNumber(issue.samplePct)}% sample</em>
                              <em>risk {formatNumber(issue.estimatedStrokesRisk)}</em>
                            </span>
                            <SourceRefs refs={issue.sourceRefs ?? issue.refs} onSelectRef={onSelectRef} />
                          </div>
                        ))}
                      </div>
                    </section>
                  ) : null}
                  {toughestHoles.length ? (
                    <section aria-label={`${courseName} toughest holes`}>
                      <h3>Toughest Holes</h3>
                      <div className="course-insight-list">
                        {toughestHoles.map((hole) => (
                          <div key={`hole-${formatNumber(hole.hole)}`} className="course-insight-row">
                            <span>
                              <strong>Hole {formatNumber(hole.hole)}</strong>
                              <b>{formatSigned(hole.averageToPar)} avg</b>
                              <em>{formatSigned(hole.worstToPar)} worst</em>
                              <em>risk {formatNumber(hole.issueScore)}</em>
                            </span>
                            <SourceRefs refs={hole.holeRefs ?? hole.sourceRefs} onSelectRef={onSelectRef} />
                          </div>
                        ))}
                      </div>
                    </section>
                  ) : null}
                </div>
              ) : null}
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
