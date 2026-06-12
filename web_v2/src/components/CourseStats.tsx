import { useState } from 'react'
import type { HistoryStatsResponse, MobileCourseOptionsResponse } from '../types'
import { issueLabel } from '../issueLabels'
import { coverageZh, formDirectionZh, phaseZh } from '../zhLabels'
import { AggregateEvidence } from './AggregateEvidence'
import { CourseDistributionMap } from './CourseDistributionMap'
import { ShowAllToggle } from './ShowAllToggle'
import { SourceRefs } from './SourceRefs'
import { StatsQualityChips } from './StatsQualityChips'
import { asRows, asString, formatNumber, formatSigned, semanticClass } from './statsValues'

interface CourseStatsProps {
  data: HistoryStatsResponse
  onSelectRef?: (sourceRef: string) => void
  courseOptions?: MobileCourseOptionsResponse | null
  onPrepCourse?: (globalId: number) => void
}

// 70 real courses rendered every sub-block at once and froze the page — cap
// the list and keep breakdowns in lazy <details>. Display truncation only.
const COURSES_CAP = 20

export function CourseStats({ data, onSelectRef, courseOptions, onPrepCourse }: CourseStatsProps) {
  const courses = data.courses
  const [coursesExpanded, setCoursesExpanded] = useState(false)
  const visibleCourses = coursesExpanded ? courses : courses.slice(0, COURSES_CAP)

  // Build courseKey → globalId lookup from courseOptions
  const courseKeyToGlobalId: Map<string, number> = new Map(
    (courseOptions?.courses ?? []).flatMap((opt) =>
      opt.courseKey ? [[opt.courseKey, opt.globalId]] : [],
    ),
  )

  return (
    <section className="stats-page" aria-label="球场表现">
      <div className="section-head stats-head">
        <div>
          <p className="eyebrow">球场历史</p>
          <h1>球场表现</h1>
          <p>各球场历史成绩、近期走势与数据来源。</p>
        </div>
        <StatsQualityChips data={data} labels={['geometry']} />
      </div>
      <section className="panel compact-panel" aria-label="球场分布">
        <div className="section-head">
          <div>
            <h2>球场分布</h2>
            <p>各球场球局占比与地理分布。</p>
          </div>
        </div>
        <CourseDistributionMap rows={data.courseDistribution} onSelectRef={onSelectRef} />
      </section>
      <div className="stats-list">
        {courses.length === 0 ? (
          <article className="stats-empty">
            <h2>暂无球场表现数据</h2>
            <p>同步 Garmin 球局或切换到 fixture 模式以填充球场分布。</p>
          </article>
        ) : null}
        {visibleCourses.map((course) => (
          <CourseRow
            key={asString(course.courseKey) ?? asString(course.courseName) ?? 'course'}
            course={course}
            prepGlobalId={(() => {
              const courseKey = asString(course.courseKey)
              return courseKey ? courseKeyToGlobalId.get(courseKey) : undefined
            })()}
            onSelectRef={onSelectRef}
            onPrepCourse={onPrepCourse}
          />
        ))}
      </div>
      {courses.length > COURSES_CAP ? (
        <ShowAllToggle total={courses.length} expanded={coursesExpanded} onToggle={() => setCoursesExpanded((value) => !value)} />
      ) : null}
    </section>
  )
}

interface CourseRowProps {
  course: HistoryStatsResponse['courses'][number]
  prepGlobalId: number | undefined
  onSelectRef?: (sourceRef: string) => void
  onPrepCourse?: (globalId: number) => void
}

function CourseRow({ course, prepGlobalId, onSelectRef, onPrepCourse }: CourseRowProps) {
  // The heavy sub-blocks render ONLY while the <details> is open — the
  // summary stays informative without paying their render cost up front.
  const [showBreakdown, setShowBreakdown] = useState(false)
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
  const courseName = asString(course.courseName) ?? '球场'
  const courseKey = asString(course.courseKey)
  const hasDifficultyAdjusted = Object.keys(difficultyAdjusted).length > 0
  const breakdownParts = [
    hasDifficultyAdjusted ? '难度调整' : null,
    issueProfile.length ? `问题分布(${issueProfile.length})` : null,
    toughestHoles.length ? `最难球洞(${toughestHoles.length})` : null,
  ].filter((part): part is string => part !== null)
  return (
    <article className="stats-item">
      <div className="stats-item-main">
        <h2>{asString(course.courseName) ?? '未知球场'}</h2>
        <p>{courseKey ?? 'unknown'}</p>
      </div>
      <div className="stats-item-facts" aria-label={`${asString(course.courseName) ?? '球场'} 数据`}>
        <span>{formatNumber(course.roundCount)} 场次</span>
        <span>平均 {formatNumber(course.average18)}</span>
        <span>最好 {formatNumber(course.bestScore)}</span>
        <span>最差 {formatNumber(course.worstScore)}</span>
        {course.averageDifferential !== undefined ? <span>均差 {formatNumber(course.averageDifferential)}</span> : null}
        {course.bestDifferential !== undefined ? <span>最好差 {formatNumber(course.bestDifferential)}</span> : null}
        {recentForm.recentAverage18 !== undefined ? <span>近期 {formatNumber(recentForm.recentAverage18)}</span> : null}
        {teeDirection.hitPct !== undefined ? <span>FIR {formatNumber(teeDirection.hitPct)}%</span> : null}
        {dominantMiss && dominantMiss !== 'unknown' ? (
          <span className={`semantic-chip ${semanticClass('tee', dominantMiss)}`}>
            开球 {dominantMiss} {formatNumber(teeDirection[`${dominantMiss}Pct`])}%
          </span>
        ) : null}
        {approachMiss.girPct !== undefined ? <span>GIR {formatNumber(approachMiss.girPct)}%</span> : null}
        {dominantApproachMiss && dominantApproachMiss !== 'unknown' ? (
          <span className={`semantic-chip ${semanticClass('approach', dominantApproachMiss)}`}>
            攻果岭 {dominantApproachMiss} {formatNumber(approachMiss[`${dominantApproachMiss}Pct`])}%
          </span>
        ) : null}
        {direction ? (
          <span className={`semantic-chip ${semanticClass('trend', direction)}`}>
            {formDirectionZh(direction)} {formatSigned(recentForm.deltaAverage18)}
          </span>
        ) : null}
        {differentialDirection ? (
          <span className={`semantic-chip ${semanticClass('trend', differentialDirection)}`}>
            差分 {formDirectionZh(differentialDirection)} {formatSigned(recentForm.deltaAverageDifferential)}
          </span>
        ) : null}
        {asString(course.geometryCoverage) ? (
          <span className={`semantic-chip ${semanticClass('quality', course.geometryCoverage)}`}>几何 {coverageZh(asString(course.geometryCoverage) ?? '')}</span>
        ) : null}
        <AggregateEvidence row={course} />
      </div>
      <p className="stats-refs">
        <SourceRefs refs={course.roundRefs ?? course.roundIds} onSelectRef={onSelectRef} />
      </p>
      {prepGlobalId !== undefined && onPrepCourse ? (
        <div className="stats-item-actions">
          <button
            type="button"
            className="w4-goto-prep"
            aria-label={`去备战 ${courseName}`}
            onClick={() => onPrepCourse(prepGlobalId)}
          >
            去备战 →
          </button>
        </div>
      ) : null}
      {breakdownParts.length ? (
        <details className="course-breakdown-details" open={showBreakdown}>
          {/* preventDefault keeps the native toggle from fighting the
              controlled open prop; content mounts only while open */}
          <summary
            onClick={(event) => {
              event.preventDefault()
              setShowBreakdown((value) => !value)
            }}
          >
            详情:{breakdownParts.join(' · ')}
          </summary>
          {showBreakdown ? (
            <div className="course-breakdown">
              {hasDifficultyAdjusted ? (
                <section aria-label={`${courseName} 难度调整`}>
                  <h3>难度调整</h3>
                  <div className="course-insight-list">
                    <div className="course-insight-row">
                      <span>
                        <strong>评级/坡度覆盖</strong>
                        <b>
                          {formatNumber(difficultyAdjusted.ratedRoundCount)} / {formatNumber(difficultyAdjusted.eligibleRoundCount)} 场次
                        </b>
                        <em>均差 {formatNumber(difficultyAdjusted.averageDifferential)}</em>
                        <em>最好 {formatNumber(difficultyAdjusted.bestDifferential)}</em>
                        {difficultyCoverage.ready !== undefined ? (
                          <em>
                            覆盖 {formatNumber(difficultyCoverage.ready)}/{formatNumber(difficultyCoverage.total)} {formatNumber(difficultyCoverage.pct)}%
                          </em>
                        ) : null}
                      </span>
                      <SourceRefs refs={difficultyAdjusted.roundRefs ?? difficultyAdjusted.sourceRefs} onSelectRef={onSelectRef} />
                    </div>
                    {Array.isArray(difficultyAdjusted.missingRoundRefs) && difficultyAdjusted.missingRoundRefs.length > 0 ? (
                      <div className="course-insight-row">
                        <span>
                          <strong>缺失评级/坡度</strong>
                          <b>{formatNumber(difficultyAdjusted.missingRoundRefs.length)} 场次</b>
                        </span>
                        <SourceRefs refs={difficultyAdjusted.missingRoundRefs} onSelectRef={onSelectRef} />
                      </div>
                    ) : null}
                  </div>
                </section>
              ) : null}
              {issueProfile.length ? (
                <section aria-label={`${courseName} 问题分布`}>
                  <h3>球场问题分布</h3>
                  <div className="course-insight-list">
                    {issueProfile.map((issue) => (
                      <div key={`${asString(issue.issue) ?? 'issue'}-${asString(issue.source) ?? 'source'}`} className="course-insight-row">
                        <span>
                          <strong>{issueLabel(asString(issue.issue) ?? '未知问题')}</strong>
                          {asString(issue.phase) ? <b>{phaseZh(asString(issue.phase) ?? '')}</b> : null}
                          <em>{formatNumber(issue.affectedHoleCount)} 洞</em>
                          <em>{formatNumber(issue.samplePct)}% 样本</em>
                          <em>风险 {formatNumber(issue.estimatedStrokesRisk)}</em>
                        </span>
                        <SourceRefs refs={issue.sourceRefs ?? issue.refs} onSelectRef={onSelectRef} />
                      </div>
                    ))}
                  </div>
                </section>
              ) : null}
              {toughestHoles.length ? (
                <section aria-label={`${courseName} 最难球洞`}>
                  <h3>最难球洞</h3>
                  <div className="course-insight-list">
                    {toughestHoles.map((hole) => (
                      <div key={`hole-${formatNumber(hole.hole)}`} className="course-insight-row">
                        <span>
                          <strong>第{formatNumber(hole.hole)}洞</strong>
                          <b>{formatSigned(hole.averageToPar)} 均</b>
                          <em>{formatSigned(hole.worstToPar)} 最差</em>
                          <em>风险 {formatNumber(hole.issueScore)}</em>
                        </span>
                        <SourceRefs refs={hole.holeRefs ?? hole.sourceRefs} onSelectRef={onSelectRef} />
                      </div>
                    ))}
                  </div>
                </section>
              ) : null}
            </div>
          ) : null}
        </details>
      ) : null}
    </article>
  )
}

function asRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {}
}
