import { useEffect, useRef, useState, type FormEvent } from 'react'
import { fetchCoursePrep, fetchPrepTips, prewarmCourseTopo } from '../api'
import type {
  CoursePrepResponse,
  CourseSearchMatch,
  CourseSearchResponse,
  HistoryStatsResponse,
  MobileCourseOption,
  MobileCourseOptionsResponse,
  PrepTipsResponse,
} from '../types'
import { CourseFinder } from './CourseFinder'
import { PrepWorkbench } from './PrepWorkbench'
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

type SearchState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ready'; matches: CourseSearchMatch[] }
  | { status: 'error'; message: string }

function matchMeta(match: CourseSearchMatch): string {
  const holes = asNumber(match.holes)
  return [asString(match.city), holes === null ? null : `${holes}洞`].filter(Boolean).join(' · ')
}

// Inline top-bar course search — the same onSearchCourses wiring as the entry
// finder, surfaced without leaving the workbench. Picking a result swaps courses.
function PrepCourseSearch({
  onSearchCourses,
  onSelectCourse,
}: {
  onSearchCourses: (name: string) => Promise<CourseSearchResponse>
  onSelectCourse: (globalId: number, name?: string) => void
}) {
  const [query, setQuery] = useState('')
  const [search, setSearch] = useState<SearchState>({ status: 'idle' })
  const searchSeq = useRef(0)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const name = query.trim()
    if (!name) return
    const seq = ++searchSeq.current
    setSearch({ status: 'loading' })
    try {
      const data = await onSearchCourses(name)
      if (searchSeq.current !== seq) return
      setSearch({ status: 'ready', matches: Array.isArray(data.matches) ? data.matches : [] })
    } catch (error: unknown) {
      if (searchSeq.current !== seq) return
      setSearch({ status: 'error', message: error instanceof Error ? error.message : '未知错误' })
    }
  }

  return (
    <div className="prep-search">
      <form className="prep-search-box" onSubmit={(event) => void handleSubmit(event)}>
        <span aria-hidden="true">🔍</span>
        <input
          type="text"
          aria-label="搜索球场"
          placeholder="搜索球场…"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
      </form>
      {search.status === 'loading' ? <p className="prep-search-state">搜索中…</p> : null}
      {search.status === 'error' ? <p className="prep-search-state">搜索失败:{search.message}</p> : null}
      {search.status === 'ready' && search.matches.length === 0 ? <p className="prep-search-state">没有找到球场</p> : null}
      {search.status === 'ready' && search.matches.length > 0 ? (
        <ul className="prep-search-results">
          {search.matches.map((match) => (
            <li key={match.globalId}>
              <button
                type="button"
                onClick={() => {
                  onSelectCourse(match.globalId, match.name)
                  setQuery('')
                  setSearch({ status: 'idle' })
                }}
              >
                <span className="prep-search-name">{match.name}</span>
                <span className="prep-search-meta">{matchMeta(match)}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
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

  // On course select, kick a background render of ALL the course's hole topo bitmaps so browsing
  // holes hits a warm cache instead of paying ~6–10s on each hole's first view. Fire-and-forget:
  // failures are swallowed (holes still render lazily on first view as before).
  useEffect(() => {
    if (globalId === null) return
    void prewarmCourseTopo(globalId).catch(() => {})
  }, [globalId])

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
  const tipsData = tipsCurrent !== null && 'data' in tipsCurrent ? tipsCurrent.data : null
  const tipsError = tipsCurrent !== null && 'error' in tipsCurrent ? tipsCurrent.error : null

  const option = findCourseOption(courseOptions, globalId)
  // courseOptions (played, canonical) wins; the finder-handed search name covers
  // never-played courses; the bare gid is the last resort.
  const handedName = typeof selectedCourseName === 'string' && selectedCourseName.trim() ? selectedCourseName : null
  const courseName = option?.name ?? handedName ?? `球场 ${globalId}`
  const record = courseRecord(allStats, option)
  const totals = holeTotals(prepData)
  const holeRows = courseHoleRows(allStats, optionCourseKey(option))

  // Export the crib sheet through the browser print/share sheet — the honest
  // "take these numbers with you" path (save as PDF / AirDrop to the phone).
  const handleExport = () => {
    if (typeof window !== 'undefined' && typeof window.print === 'function') window.print()
  }

  return (
    <section className="prep-page prep-workbench-page" aria-label="备战">
      <div className="prep-topbar">
        <div className="prep-crumb">
          <h2 className="prep-crumb-name">{courseName}</h2>
          <span className="prep-crumb-tee">蓝 T</span>
        </div>
        <PrepCourseSearch onSearchCourses={onSearchCourses} onSelectCourse={onSelectCourse} />
        <div className="prep-topbar-actions">
          <button type="button" className="prep-topbtn" onClick={handleExport}>
            导出 Crib Sheet
          </button>
          <button type="button" className="prep-topbtn primary" onClick={handleExport}>
            发到手表/手机
          </button>
          <button type="button" className="prep-change-course" onClick={onChangeCourse}>
            换球场
          </button>
        </div>
      </div>

      {prepError ? (
        <section className="panel empty-state prep-load-error" aria-label="球场攻略加载失败">
          <h2>球场攻略加载失败</h2>
          <p>{prepError}</p>
          <button type="button" onClick={() => setPrepAttempt((attempt) => attempt + 1)}>
            重试
          </button>
        </section>
      ) : prepData ? (
        <PrepWorkbench
          prepData={prepData}
          holeRows={holeRows}
          tips={tipsData && Array.isArray(tipsData.tips) ? tipsData.tips : null}
          tipsError={tipsError}
          onRetryTips={() => setTipsAttempt((attempt) => attempt + 1)}
          totals={totals}
          record={record}
        />
      ) : (
        <section className="panel prep-loading" aria-label="球场攻略加载中">
          <p>球场攻略加载中…</p>
        </section>
      )}
    </section>
  )
}
