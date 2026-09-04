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
  onSearchCourses: (name: string, city?: string) => Promise<CourseSearchResponse>
  onNearbyCourses?: (latitude: number, longitude: number, radiusKm: number) => Promise<CourseSearchResponse>
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

function validCourses(courseOptions: MobileCourseOptionsResponse | null): MobileCourseOption[] {
  if (!courseOptions || !Array.isArray(courseOptions.courses)) return []
  return courseOptions.courses.filter(
    (course): course is MobileCourseOption =>
      course !== null &&
      typeof course === 'object' &&
      typeof course.globalId === 'number' &&
      typeof course.name === 'string',
  )
}

// Garmin lists each 9-hole loop as its own entry ("…黑骑士 ~ C/A", "~ A"). The
// owner asked to pick the COURSE first, then which nine — so group by base name
// (strip the " ~ <nine>" suffix) into one card whose nine variants are chips.
interface BaseCourse {
  base: string
  rounds: number
  variants: { globalId: number; nine: string | null; name: string; rounds: number }[]
}

function splitNine(name: string): { base: string; nine: string | null } {
  const match = name.match(/^(.*?)\s*~\s*(.+)$/)
  if (match) return { base: match[1].trim(), nine: match[2].trim() }
  return { base: name.trim(), nine: null }
}

function frequentBaseCourses(courseOptions: MobileCourseOptionsResponse | null): BaseCourse[] {
  const byBase = new Map<string, BaseCourse>()
  for (const course of validCourses(courseOptions)) {
    const { base, nine } = splitNine(course.name)
    const rounds = asNumber(course.roundCount) ?? 0
    const group = byBase.get(base) ?? { base, rounds: 0, variants: [] }
    group.rounds += rounds
    group.variants.push({ globalId: course.globalId, nine, name: course.name, rounds })
    byBase.set(base, group)
  }
  return [...byBase.values()]
    .map((group) => ({ ...group, variants: group.variants.sort((a, b) => b.rounds - a.rounds) }))
    .sort((a, b) => b.rounds - a.rounds)
    .slice(0, 3)
}

function matchMeta(match: CourseSearchMatch): string {
  const holes = asNumber(match.holes)
  return [asString(match.city), holes === null ? null : `${holes}洞`].filter(Boolean).join(' · ')
}

export function CourseFinder({
  courseOptions,
  onSearchCourses,
  onNearbyCourses,
  onSelectCourse,
  heading = '想备哪场?',
  sub = '搜索球场,或从常打球场直接开备战。',
  ctaLabel = '去备战',
}: CourseFinderProps) {
  const [city, setCity] = useState('')
  const [nearbyRadiusKm, setNearbyRadiusKm] = useState(50)
  const [nearbyState, setNearbyState] = useState<'idle' | 'loading' | 'error'>('idle')
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
      const data = city.trim() ? await onSearchCourses(name, city.trim()) : await onSearchCourses(name)
      if (searchSeq.current !== seq) return
      setSearch({ status: 'ready', matches: Array.isArray(data.matches) ? data.matches : [] })
    } catch (error: unknown) {
      if (searchSeq.current !== seq) return
      setSearch({ status: 'error', message: error instanceof Error ? error.message : '未知错误' })
    }
  }

  async function handleNearby() {
    if (!onNearbyCourses || typeof navigator === 'undefined' || !navigator.geolocation) return
    setNearbyState('loading')
    navigator.geolocation.getCurrentPosition(
      (position) => {
        void onNearbyCourses(position.coords.latitude, position.coords.longitude, nearbyRadiusKm)
          .then((data) => {
            setSearch({ status: 'ready', matches: Array.isArray(data.matches) ? data.matches : [] })
            setNearbyState('idle')
          })
          .catch((error: unknown) => {
            setNearbyState('error')
            setSearch({ status: 'error', message: error instanceof Error ? error.message : '附近球场加载失败' })
          })
      },
      () => {
        setNearbyState('error')
        setSearch({ status: 'error', message: '无法获取当前位置' })
      },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 },
    )
  }

  const frequents = frequentBaseCourses(courseOptions)

  return (
    <>
      <h2>{heading}</h2>
      <p className="home-prep-sub">{sub}</p>
      <form className="home-search" onSubmit={(event) => void handleSearchSubmit(event)}>
        <input
          type="text"
          aria-label="城市"
          placeholder="城市（可选）"
          value={city}
          onChange={(event) => setCity(event.target.value)}
        />
        <input
          type="text"
          aria-label="搜索球场"
          placeholder="球场名,如:观澜湖"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <button type="submit">搜索</button>
      </form>
      {onNearbyCourses ? (
        <div className="home-nearby-search">
          <select aria-label="附近范围" value={nearbyRadiusKm} onChange={(event) => setNearbyRadiusKm(Number(event.target.value))}>
            <option value={50}>附近 50 km</option>
            <option value={100}>附近 100 km</option>
            <option value={200}>附近 200 km</option>
          </select>
          <button type="button" onClick={() => void handleNearby()} disabled={nearbyState === 'loading'}>
            {nearbyState === 'loading' ? '定位中…' : '查看附近球场'}
          </button>
        </div>
      ) : null}
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
            {frequents.map((group) => (
              <article key={group.base} className="home-course-card">
                <b className="home-course-name">{group.base}</b>
                <span className="home-course-meta">打过 {group.rounds} 次</span>
                {group.variants.length === 1 && group.variants[0].nine === null ? (
                  <button
                    type="button"
                    aria-label={`${ctaLabel} ${group.base}`}
                    onClick={() => onSelectCourse(group.variants[0].globalId, group.variants[0].name)}
                  >
                    {ctaLabel}
                  </button>
                ) : (
                  <div className="home-course-nines">
                    <span className="home-course-nines-label">选 9 洞</span>
                    {group.variants.map((variant) => (
                      <button
                        key={variant.globalId}
                        type="button"
                        className="home-course-nine"
                        aria-label={`${ctaLabel} ${variant.name}`}
                        onClick={() => onSelectCourse(variant.globalId, variant.name)}
                      >
                        {variant.nine ?? '全场'}
                      </button>
                    ))}
                  </div>
                )}
              </article>
            ))}
          </div>
        </div>
      ) : null}
    </>
  )
}
