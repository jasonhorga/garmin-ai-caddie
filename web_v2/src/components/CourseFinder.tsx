import { useRef, useState, type FormEvent } from 'react'
import type {
  CourseSearchMatch,
  CourseSearchResponse,
  MobileCourseOption,
  MobileCourseOptionsResponse,
} from '../types'

// Shared 搜索球场 + 常打球场 building blocks (spec §5.3): the 概览 prep card and
// the 备战 entry state render the same finder with different heading copy.
interface CourseFinderProps {
  courseOptions: MobileCourseOptionsResponse | null
  onSearchCourses: (name: string) => Promise<CourseSearchResponse>
  // name rides along so the prep header can show searched courses that have
  // no courseOptions row (never-played) instead of a bare 球场 {gid}.
  onSelectCourse: (globalId: number, name?: string) => void
  heading?: string
  sub?: string
  // Frequent-card CTA copy: prep keeps the default 去备战, the 实战 sandbox
  // passes 开始模拟 (same select handler either way).
  ctaLabel?: string
}

type SearchState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ready'; matches: CourseSearchMatch[] }
  | { status: 'error'; message: string }

function asNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function asString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null
}

function frequentCourses(courseOptions: MobileCourseOptionsResponse | null): MobileCourseOption[] {
  if (!courseOptions || !Array.isArray(courseOptions.courses)) return []
  return courseOptions.courses
    .filter(
      (course): course is MobileCourseOption =>
        course !== null &&
        typeof course === 'object' &&
        typeof course.globalId === 'number' &&
        typeof course.name === 'string',
    )
    .sort((a, b) => (asNumber(b.roundCount) ?? 0) - (asNumber(a.roundCount) ?? 0))
    .slice(0, 3)
}

function matchMeta(match: CourseSearchMatch): string {
  const holes = asNumber(match.holes)
  return [asString(match.city), holes === null ? null : `${holes}洞`].filter(Boolean).join(' · ')
}

export function CourseFinder({
  courseOptions,
  onSearchCourses,
  onSelectCourse,
  heading = '想备哪场?',
  sub = '搜索球场,或从常打球场直接开备战。',
  ctaLabel = '去备战',
}: CourseFinderProps) {
  const [query, setQuery] = useState('')
  const [search, setSearch] = useState<SearchState>({ status: 'idle' })
  const searchSeq = useRef(0)

  async function handleSearchSubmit(event: FormEvent<HTMLFormElement>) {
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

  const frequents = frequentCourses(courseOptions)

  return (
    <>
      <h2>{heading}</h2>
      <p className="home-prep-sub">{sub}</p>
      <form className="home-search" onSubmit={(event) => void handleSearchSubmit(event)}>
        <input
          type="text"
          aria-label="搜索球场"
          placeholder="球场名,如:观澜湖"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <button type="submit">搜索</button>
      </form>
      {search.status === 'loading' ? <p className="home-search-state">搜索中…</p> : null}
      {search.status === 'error' ? <p className="home-search-state">搜索失败:{search.message}</p> : null}
      {search.status === 'ready' && search.matches.length === 0 ? <p className="home-search-state">没有找到球场</p> : null}
      {search.status === 'ready' && search.matches.length > 0 ? (
        <ul className="home-search-results">
          {search.matches.map((match) => (
            <li key={match.globalId}>
              <button type="button" className="home-search-match" onClick={() => onSelectCourse(match.globalId, match.name)}>
                <span className="home-search-match-name">{match.name}</span>
                <span className="home-search-match-meta">{matchMeta(match)}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      {frequents.length > 0 ? (
        <div className="home-frequent">
          <span className="home-frequent-label">常打球场</span>
          <div className="home-frequent-cards">
            {frequents.map((course) => (
              <article key={course.globalId} className="home-course-card">
                <b className="home-course-name">{course.name}</b>
                <span className="home-course-meta">打过 {asNumber(course.roundCount) ?? 0} 次</span>
                <button type="button" aria-label={`${ctaLabel} ${course.name}`} onClick={() => onSelectCourse(course.globalId, course.name)}>
                  {ctaLabel}
                </button>
              </article>
            ))}
          </div>
        </div>
      ) : null}
    </>
  )
}
