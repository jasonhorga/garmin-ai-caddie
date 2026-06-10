import { useEffect, useRef, useState } from 'react'
import { fetchCoursePrep, fetchPrepTips } from '../api'
import type {
  CoursePrepResponse,
  CourseSearchResponse,
  HistoryStatsResponse,
  MobileCourseOption,
  MobileCourseOptionsResponse,
  PrepTipsResponse,
} from '../types'
import { CourseFinder } from './CourseFinder'

interface PrepPageProps {
  globalId: number | null // null → entry state (course finder)
  courseOptions: MobileCourseOptionsResponse | null
  allStats: HistoryStatsResponse | null
  adminToken?: string
  onSearchCourses: (name: string) => Promise<CourseSearchResponse>
  onSelectCourse: (globalId: number) => void
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

function asNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function formatAverage(value: number): string {
  return String(Number(value.toFixed(1)))
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

function courseRecord(
  allStats: HistoryStatsResponse | null,
  option: MobileCourseOption | null,
): { roundCount: number; average18: number } | null {
  const courseKey = typeof option?.courseKey === 'string' && option.courseKey.trim() ? option.courseKey : null
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

export function PrepPage({
  globalId,
  courseOptions,
  allStats,
  adminToken,
  onSearchCourses,
  onSelectCourse,
  onChangeCourse,
}: PrepPageProps) {
  const [tab, setTab] = useState<PrepTab>('overview')
  const [prepDone, setPrepDone] = useState<PrepDone<CoursePrepResponse> | null>(null)
  const [tipsDone, setTipsDone] = useState<PrepDone<PrepTipsResponse> | null>(null)
  const [prepAttempt, setPrepAttempt] = useState(0)
  const [tipsAttempt, setTipsAttempt] = useState(0)
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
  const tipsError = tipsCurrent !== null && 'error' in tipsCurrent ? tipsCurrent.error : null

  const option = findCourseOption(courseOptions, globalId)
  const courseName = option?.name ?? `球场 ${globalId}`
  const record = courseRecord(allStats, option)
  const totals = holeTotals(prepData)

  // B2 shell: 逐洞攻略 reports the loaded hole count (B3 renders hole cards);
  // 概览/针对你 stay placeholders until B4.
  const holesTabContent = prepData ? (
    <p className="prep-holes-count">已加载 {Array.isArray(prepData.holes) ? prepData.holes.length : 0} 洞</p>
  ) : prepError ? (
    <p className="prep-tab-placeholder">…</p>
  ) : (
    <p className="prep-tab-placeholder">球场攻略加载中…</p>
  )

  return (
    <section className="prep-page" aria-label="备战">
      <header className="panel prep-course-header">
        <div className="prep-course-info">
          <h2>{courseName}</h2>
          <p className="prep-course-meta">
            Par {totals ? totals.par : '—'} · 总码数 {totals ? totals.yards : '—'} 码
          </p>
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
      {tipsError ? (
        <section className="panel empty-state prep-load-error" aria-label="个性化提示加载失败">
          <h2>个性化提示加载失败</h2>
          <p>{tipsError}</p>
          <button type="button" onClick={() => setTipsAttempt((attempt) => attempt + 1)}>
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
        {tab === 'holes' ? holesTabContent : <p className="prep-tab-placeholder">…</p>}
      </section>
    </section>
  )
}
