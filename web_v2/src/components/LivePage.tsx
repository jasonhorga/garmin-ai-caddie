import { useState, type ComponentProps } from 'react'
import type { CourseSearchResponse, MobileCourseOptionsResponse, RoundCard as RoundCardType } from '../types'
import { CaddiePage } from './CaddiePage'
import { CourseFinder } from './CourseFinder'

// 实战 page shell (spec §5.4 web scope), three inner tabs in the PrepPage idiom
// (local tab state + subnav--inner classes, NOT SubNav — these tabs are not
// ProductPages): 决策沙盘 (default; course/hole simulation, sandbox lands in
// W3 T3/T4) / 最近回放 (recent-round replay, W3 T2) / 完整工具 — the EXISTING
// CaddiePage rendered VERBATIM so every media/audit/context tool stays
// reachable with zero functionality deleted.
interface LivePageProps {
  // 决策沙盘 course-pick entry (sandbox state machine consumes these in T3).
  courseOptions: MobileCourseOptionsResponse | null
  adminToken?: string
  onSearchCourses: (name: string) => Promise<CourseSearchResponse>
  // 最近回放 (T2).
  recentRounds: RoundCardType[]
  // 完整工具: CaddiePage's full props bundle, spread through untouched.
  // ComponentProps keeps this in lockstep with CaddiePage without exporting or
  // re-listing its private props interface.
  caddieProps: ComponentProps<typeof CaddiePage>
}

type LiveTab = 'sandbox' | 'replay' | 'tools'

const LIVE_TABS: Array<{ key: LiveTab; label: string }> = [
  { key: 'sandbox', label: '决策沙盘' },
  { key: 'replay', label: '最近回放' },
  { key: 'tools', label: '完整工具' },
]

export function LivePage({ courseOptions, onSearchCourses, caddieProps }: LivePageProps) {
  const [tab, setTab] = useState<LiveTab>('sandbox')

  // Entry state only for now — T3 replaces the no-op onSelectCourse with the
  // sandbox state machine (course → prep fetch → hole picker → ball drag).
  // prep-entry / prep-tab-placeholder are the shared entry-panel/placeholder
  // styles introduced for 备战; the sandbox restyle in T3 owns any live-叫法.
  const sandboxContent = (
    <section className="panel prep-entry">
      <CourseFinder
        heading="选择球场开始模拟"
        sub="搜索球场,或从常打球场直接开始模拟。"
        courseOptions={courseOptions}
        onSearchCourses={onSearchCourses}
        onSelectCourse={() => undefined}
      />
    </section>
  )

  const replayContent = (
    <section className="panel">
      <p className="prep-tab-placeholder">…</p>
    </section>
  )

  return (
    <section className="live-page" aria-label="实战">
      <nav className="subnav subnav--inner" aria-label="实战页签">
        {LIVE_TABS.map((item) => (
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
      {tab === 'sandbox' ? sandboxContent : tab === 'replay' ? replayContent : <CaddiePage {...caddieProps} />}
    </section>
  )
}
