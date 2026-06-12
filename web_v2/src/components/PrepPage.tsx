import { useEffect, useRef, useState } from 'react'
import { fetchCoursePrep, fetchPrepTips } from '../api'
import type {
  CoursePrepHole,
  CoursePrepResponse,
  CourseSearchResponse,
  HistoryStatsResponse,
  MobileCourseOption,
  MobileCourseOptionsResponse,
  PrepTip,
  PrepTipsResponse,
} from '../types'
import { tipBasisZh } from '../zhLabels'
import { CourseFinder } from './CourseFinder'
import { PrepHoleCard } from './PrepHoleCard'
import { asNumber, asRows, asString, type StatRow } from './statsValues'

interface PrepPageProps {
  globalId: number | null // null → entry state (course finder)
  selectedCourseName?: string | null // finder-handed name for courses absent from courseOptions
  courseOptions: MobileCourseOptionsResponse | null
  allStats: HistoryStatsResponse | null
  adminToken?: string
  onSearchCourses: (name: string) => Promise<CourseSearchResponse>
  onSelectCourse: (globalId: number, name?: string) => void
  onChangeCourse: () => void
}

// Completed-fetch state keyed by request identity (`gid:attempt`): the loading
// state is DERIVED (`done.key !== currentKey`), so switching courses never
// paints the previous course's numbers and effects never set state synchronously.
type PrepResult<T> = { data: T } | { error: string }
type PrepDone<T> = { key: string; result: PrepResult<T> }

type PrepTab = 'overview' | 'holes' | 'foryou'

// Local tab row, NOT SubNav: SubNavItem.page is typed as ProductPage and these
// inner tabs are not product pages (and navigation.ts types stay untouched).
const PREP_TABS: Array<{ key: PrepTab; label: string }> = [
  { key: 'overview', label: '概览' },
  { key: 'holes', label: '逐洞攻略' },
  { key: 'foryou', label: '针对你' },
]

function formatAverage(value: number): string {
  return String(Number(value.toFixed(1)))
}

// Signed to-par with at most one decimal: 1.25 → '+1.3', 0 → '0', -0.5 → '-0.5'.
function formatToParValue(value: number): string {
  const rounded = Number(value.toFixed(1))
  return rounded > 0 ? `+${rounded}` : String(rounded)
}

function findCourseOption(courseOptions: MobileCourseOptionsResponse | null, globalId: number): MobileCourseOption | null {
  if (!courseOptions || !Array.isArray(courseOptions.courses)) return null
  return (
    courseOptions.courses.find(
      (course): course is MobileCourseOption =>
        course !== null && typeof course === 'object' && course.globalId === globalId && typeof course.name === 'string',
    ) ?? null
  )
}

function optionCourseKey(option: MobileCourseOption | null): string | null {
  return typeof option?.courseKey === 'string' && option.courseKey.trim() ? option.courseKey : null
}

function courseRecord(
  allStats: HistoryStatsResponse | null,
  option: MobileCourseOption | null,
): { roundCount: number; average18: number } | null {
  const courseKey = optionCourseKey(option)
  if (!courseKey || !allStats || !Array.isArray(allStats.courses)) return null
  const row = allStats.courses.find(
    (candidate) => candidate !== null && typeof candidate === 'object' && candidate.courseKey === courseKey,
  )
  if (!row) return null
  const roundCount = asNumber(row.roundCount)
  const average18 = asNumber(row.average18)
  if (roundCount === null || average18 === null) return null
  return { roundCount, average18 }
}

function holeTotals(data: CoursePrepResponse | null): { par: number; yards: number } | null {
  if (!data || !Array.isArray(data.holes) || data.holes.length === 0) return null
  let par = 0
  let yards = 0
  for (const hole of data.holes) {
    par += asNumber(hole?.par) ?? 0
    yards += asNumber(hole?.blue_yards) ?? 0
  }
  return { par, yards }
}

// stats.holes rows that belong to this course (joined via courseOptions courseKey).
function courseHoleRows(allStats: HistoryStatsResponse | null, courseKey: string | null): StatRow[] {
  if (!allStats || !courseKey) return []
  return asRows(allStats.holes).filter((row) => asString(row.courseKey) === courseKey)
}

function holeAverages(rows: StatRow[]): Map<number, number> {
  const averages = new Map<number, number>()
  for (const row of rows) {
    const hole = asNumber(row.hole)
    const average = asNumber(row.averageToPar)
    if (hole !== null && average !== null && !averages.has(hole)) averages.set(hole, average)
  }
  return averages
}

interface PlayedKeyHole {
  hole: number
  par: number | null
  average: number
  worst: number | null
}

// Played course: worst holes first — averageToPar desc, sampleCount≥2 so a single
// blow-up round can't define a "key hole"; par joined from this prep's holes.
// Rows whose hole is not in this prep payload belong to another nine (the server
// serves the REAL hole list) and are skipped.
function playedKeyHoles(rows: StatRow[], prepHoles: CoursePrepHole[]): PlayedKeyHole[] {
  const parByHole = new Map(prepHoles.map((hole) => [hole.hole, hole.par]))
  const qualified: Array<{ hole: number; average: number; worst: number | null }> = []
  for (const row of rows) {
    const hole = asNumber(row.hole)
    const average = asNumber(row.averageToPar)
    const samples = asNumber(row.sampleCount) ?? 0
    if (hole === null || average === null || samples < 2) continue
    if (!parByHole.has(hole)) continue
    qualified.push({ hole, average, worst: asNumber(row.worstToPar) })
  }
  qualified.sort(
    (a, b) =>
      b.average - a.average ||
      (b.worst ?? Number.NEGATIVE_INFINITY) - (a.worst ?? Number.NEGATIVE_INFINITY) ||
      a.hole - b.hole,
  )
  return qualified
    .slice(0, 3)
    .map((row) => ({ hole: row.hole, par: parByHole.get(row.hole) ?? null, average: row.average, worst: row.worst }))
}

interface LongKeyHole {
  hole: number
  par: number
  yards: number
}

// Unplayed degradation: the 3 longest par-4/5 holes by blue-tee yardage.
function longKeyHoles(prepHoles: CoursePrepHole[]): LongKeyHole[] {
  return prepHoles
    .filter((hole) => (hole.par === 4 || hole.par === 5) && asNumber(hole.blue_yards) !== null)
    .sort((a, b) => b.blue_yards - a.blue_yards || a.hole - b.hole)
    .slice(0, 3)
    .map((hole) => ({ hole: hole.hole, par: hole.par, yards: hole.blue_yards }))
}

type QuickBucket = 'under' | 'over' | 'bigover' | 'none'

// Per-hole buckets mirror the trends round chips scaled to one hole:
// ≤0 under par, ≥+1 (bogey pace) big-over, in between over; no history → neutral.
function quickBucket(average: number | null): QuickBucket {
  if (average === null) return 'none'
  if (average <= 0) return 'under'
  if (average >= 1) return 'bigover'
  return 'over'
}

interface PrepOverviewTabProps {
  holes: CoursePrepHole[]
  holeRows: StatRow[]
  onJumpToHole: (hole: number) => void
}

function PrepOverviewTab({ holes, holeRows, onJumpToHole }: PrepOverviewTabProps) {
  const played = playedKeyHoles(holeRows, holes)
  const longHoles = played.length === 0 ? longKeyHoles(holes) : []
  const averages = holeAverages(holeRows)
  return (
    <div className="prep-overview">
      <section className="prep-key-holes" aria-label="关键洞">
        <h3 className="prep-section-title">关键洞</h3>
        {played.length > 0 ? (
          <div className="prep-key-holes-grid">
            {played.map((card) => (
              <article key={card.hole} className="prep-key-hole">
                <h4>
                  第{card.hole}洞 · Par{card.par ?? '—'}
                </h4>
                <p className="prep-key-hole-stats">
                  <span>平均 {formatToParValue(card.average)}</span>
                  {card.worst !== null ? <span>最差 {formatToParValue(card.worst)}</span> : null}
                </p>
              </article>
            ))}
          </div>
        ) : longHoles.length > 0 ? (
          <div className="prep-key-holes-grid">
            {longHoles.map((card) => (
              <article key={card.hole} className="prep-key-hole">
                <h4>
                  第{card.hole}洞 · Par{card.par} · {card.yards}码
                </h4>
                <p className="prep-key-hole-stats">
                  <span className="prep-key-hole-warn">长洞注意</span>
                </p>
              </article>
            ))}
          </div>
        ) : (
          <p className="prep-tab-placeholder">暂无关键洞数据</p>
        )}
      </section>
      <section className="prep-quick-strip" aria-label="逐洞速览">
        <h3 className="prep-section-title">逐洞速览</h3>
        <div className="prep-quick-grid">
          {holes.map((hole) => {
            const average = averages.get(hole.hole) ?? null
            const bucket = quickBucket(average)
            const valueLabel = average === null ? '未打过' : `平均${formatToParValue(average)}`
            return (
              <button
                key={hole.hole}
                type="button"
                className={`prep-quick-chip ${bucket}`}
                aria-label={`第${hole.hole}洞 Par${hole.par} ${valueLabel}`}
                onClick={() => onJumpToHole(hole.hole)}
              >
                <span className="prep-quick-hole">{hole.hole}</span>
                <span className="prep-quick-par">Par{hole.par}</span>
                <span className="prep-quick-avg">{average === null ? '—' : formatToParValue(average)}</span>
              </button>
            )
          })}
        </div>
      </section>
    </div>
  )
}

interface PrepTipsTabProps {
  tips: PrepTip[] | null // null while the fetch is in flight
  error: string | null
  onRetry: () => void
}

function PrepTipsTab({ tips, error, onRetry }: PrepTipsTabProps) {
  if (error) {
    return (
      <section className="empty-state prep-load-error" aria-label="个性化提示加载失败">
        <h3>个性化提示加载失败</h3>
        <p>{error}</p>
        <button type="button" onClick={onRetry}>
          重试
        </button>
      </section>
    )
  }
  if (tips === null) return <p className="prep-tab-placeholder">个性化提示加载中…</p>
  if (tips.length === 0) return <p className="prep-tab-placeholder">暂无足够数据生成提示</p>
  return (
    <ul className="prep-tips-list">
      {tips.map((tip, index) => {
        // basis arrives as a backend machine key (course.parScoring.par5…);
        // unknown keys are hidden rather than rendered raw.
        const basisZh = tipBasisZh(tip.basis)
        return (
          <li key={index} className="prep-tip">
            <span className={`prep-tip-dot ${tip.severity}`} aria-hidden="true" />
            <div className="prep-tip-body">
              <p className="prep-tip-text">{tip.text}</p>
              {basisZh ? <p className="prep-tip-basis">依据:{basisZh}</p> : null}
            </div>
          </li>
        )
      })}
    </ul>
  )
}

export function PrepPage({
  globalId,
  selectedCourseName,
  courseOptions,
  allStats,
  adminToken,
  onSearchCourses,
  onSelectCourse,
  onChangeCourse,
}: PrepPageProps) {
  const [tab, setTab] = useState<PrepTab>('overview')
  // Last-gid tracking (React "adjust state during render"): a NEW course must
  // start on 概览, not whatever tab the previous course left behind.
  const [lastGlobalId, setLastGlobalId] = useState<number | null>(globalId)
  if (globalId !== lastGlobalId) {
    setLastGlobalId(globalId)
    setTab('overview')
  }
  const [prepDone, setPrepDone] = useState<PrepDone<CoursePrepResponse> | null>(null)
  const [tipsDone, setTipsDone] = useState<PrepDone<PrepTipsResponse> | null>(null)
  const [prepAttempt, setPrepAttempt] = useState(0)
  const [tipsAttempt, setTipsAttempt] = useState(0)
  // 逐洞速览 chip target: a ref consumed by the tab effect, because the
  // prep-hole-{n} anchor only exists after the 逐洞攻略 tab has rendered.
  const scrollHoleRef = useRef<number | null>(null)
  // The W1b seq-ref race guard (HomeOverview searchSeq idiom): stale responses
  // from an earlier course/attempt must never clobber the latest request.
  const prepSeq = useRef(0)
  const tipsSeq = useRef(0)

  useEffect(() => {
    if (globalId === null) return
    const key = `${globalId}:${prepAttempt}`
    const seq = ++prepSeq.current
    fetchCoursePrep(globalId, { includeShots: true }, adminToken)
      .then((data) => {
        if (prepSeq.current !== seq) return
        setPrepDone({ key, result: { data } })
      })
      .catch((error: unknown) => {
        if (prepSeq.current !== seq) return
        setPrepDone({ key, result: { error: error instanceof Error ? error.message : '未知错误' } })
      })
  }, [globalId, adminToken, prepAttempt])

  useEffect(() => {
    if (globalId === null) return
    const key = `${globalId}:${tipsAttempt}`
    const seq = ++tipsSeq.current
    fetchPrepTips(globalId, adminToken)
      .then((data) => {
        if (tipsSeq.current !== seq) return
        setTipsDone({ key, result: { data } })
      })
      .catch((error: unknown) => {
        if (tipsSeq.current !== seq) return
        setTipsDone({ key, result: { error: error instanceof Error ? error.message : '未知错误' } })
      })
  }, [globalId, adminToken, tipsAttempt])

  useEffect(() => {
    if (tab !== 'holes' || scrollHoleRef.current === null) return
    const target = document.getElementById(`prep-hole-${scrollHoleRef.current}`)
    if (target && typeof target.scrollIntoView === 'function') {
      target.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
    scrollHoleRef.current = null
  }, [tab])

  if (globalId === null) {
    return (
      <section className="prep-page" aria-label="备战">
        <section className="panel prep-entry">
          <CourseFinder
            heading="选择球场开始备战"
            courseOptions={courseOptions}
            onSearchCourses={onSearchCourses}
            onSelectCourse={onSelectCourse}
          />
        </section>
      </section>
    )
  }

  const prepCurrent = prepDone !== null && prepDone.key === `${globalId}:${prepAttempt}` ? prepDone.result : null
  const prepData = prepCurrent !== null && 'data' in prepCurrent ? prepCurrent.data : null
  const prepError = prepCurrent !== null && 'error' in prepCurrent ? prepCurrent.error : null
  const tipsCurrent = tipsDone !== null && tipsDone.key === `${globalId}:${tipsAttempt}` ? tipsDone.result : null
  const tipsData = tipsCurrent !== null && 'data' in tipsCurrent ? tipsCurrent.data : null
  const tipsError = tipsCurrent !== null && 'error' in tipsCurrent ? tipsCurrent.error : null

  const option = findCourseOption(courseOptions, globalId)
  // courseOptions (played, canonical) wins; the finder-handed search name covers
  // never-played courses; the bare gid is the last resort.
  const handedName = typeof selectedCourseName === 'string' && selectedCourseName.trim() ? selectedCourseName : null
  const courseName = option?.name ?? handedName ?? `球场 ${globalId}`
  const record = courseRecord(allStats, option)
  const totals = holeTotals(prepData)
  const prepHoles = prepData && Array.isArray(prepData.holes) ? prepData.holes : []

  const jumpToHole = (hole: number) => {
    scrollHoleRef.current = hole
    setTab('holes')
  }

  const loadingPlaceholder = prepError ? (
    <p className="prep-tab-placeholder">…</p>
  ) : (
    <p className="prep-tab-placeholder">球场攻略加载中…</p>
  )

  // 概览: 关键洞 (played stats or long-hole degradation) + 逐洞速览 jump strip.
  const overviewTabContent = prepData ? (
    <PrepOverviewTab
      holes={prepHoles}
      holeRows={courseHoleRows(allStats, optionCourseKey(option))}
      onJumpToHole={jumpToHole}
    />
  ) : (
    loadingPlaceholder
  )

  // 逐洞攻略: one PrepHoleCard per hole, each wrapped in a prep-hole-{n} anchor
  // that the 逐洞速览 chips scroll to.
  const holesTabContent = prepData ? (
    <>
      {prepHoles.map((hole) => (
        <div key={hole.hole} id={`prep-hole-${hole.hole}`}>
          <PrepHoleCard hole={hole} clubs={Array.isArray(prepData.clubs) ? prepData.clubs : []} />
        </div>
      ))}
    </>
  ) : (
    loadingPlaceholder
  )

  // 针对你: tips as delivered (already priority-ordered by the backend).
  const foryouTabContent = (
    <PrepTipsTab
      tips={tipsData && Array.isArray(tipsData.tips) ? tipsData.tips : null}
      error={tipsError}
      onRetry={() => setTipsAttempt((attempt) => attempt + 1)}
    />
  )

  return (
    <section className="prep-page" aria-label="备战">
      <header className="panel prep-course-header">
        <div className="prep-course-info">
          <h2>{courseName}</h2>
          {/* the meta row only exists once the totals do — never 「Par — · 总码数 —码」 */}
          {totals ? (
            <p className="prep-course-meta">
              Par {totals.par} · 总码数 {totals.yards} 码
            </p>
          ) : null}
          {record ? (
            <p className="prep-course-record">
              你的战绩:打过 {record.roundCount} 次 · 均杆 {formatAverage(record.average18)}
            </p>
          ) : null}
        </div>
        <button type="button" className="prep-change-course" onClick={onChangeCourse}>
          换球场
        </button>
      </header>

      {prepError ? (
        <section className="panel empty-state prep-load-error" aria-label="球场攻略加载失败">
          <h2>球场攻略加载失败</h2>
          <p>{prepError}</p>
          <button type="button" onClick={() => setPrepAttempt((attempt) => attempt + 1)}>
            重试
          </button>
        </section>
      ) : null}

      <nav className="subnav subnav--inner" aria-label="备战页签">
        {PREP_TABS.map((item) => (
          <button
            key={item.key}
            type="button"
            className={tab === item.key ? 'subnav-tab active' : 'subnav-tab'}
            aria-current={tab === item.key ? 'page' : undefined}
            onClick={() => setTab(item.key)}
          >
            {item.label}
          </button>
        ))}
      </nav>
      <section className="panel prep-tab-panel">
        {tab === 'overview' ? overviewTabContent : tab === 'holes' ? holesTabContent : foryouTabContent}
      </section>
    </section>
  )
}
