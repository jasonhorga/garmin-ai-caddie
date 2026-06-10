import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type {
  CourseSearchResponse,
  HistoryOverviewResponse,
  HistoryStatsResponse,
  MobileCourseOptionsResponse,
} from '../types'
import { HomeOverview } from './HomeOverview'

function overviewFixture(overrides: Partial<HistoryOverviewResponse> = {}): HistoryOverviewResponse {
  return {
    schema: 'ai-caddie-history-overview-v2',
    metrics: {
      totalRounds: 12,
      eighteenHoleRounds: 10,
      nineHoleRounds: 2,
      courseCount: 4,
      shotCount: 612,
      average18: 90.2,
      recent10Average: 89.5,
      bestScore: 82,
    },
    recentRounds: [
      {
        id: '900010',
        date: '2026-06-05T08:00:00',
        courseName: '翡翠湖国际高尔夫',
        courseKey: 'emerald_lake',
        holesCompleted: 18,
        score: 88,
        par: 72,
        toPar: 16,
        scoreStrip: [],
        badges: [],
        primaryIssue: 'approach_short',
      },
      {
        id: '900009',
        date: '2026-05-28T08:00:00',
        courseName: '观澜湖·奥拉沙宝场',
        courseKey: 'mission_hills',
        holesCompleted: 18,
        score: 91,
        par: 72,
        toPar: 19,
        scoreStrip: [],
        badges: [],
        primaryIssue: null,
      },
    ],
    distribution: { total: 12, average: 90.2, best: 82, worst: 98, families: [], histogram: [] },
    dataQuality: [],
    emptyState: null,
    ...overrides,
  }
}

function statsFixture(overrides: Partial<HistoryStatsResponse> = {}): HistoryStatsResponse {
  return {
    schema: 'ai-caddie-history-stats-v1',
    dataMode: 'fixture',
    summary: {
      totalRounds: 12,
      average18: 90.2,
      recent10Average: 89.5,
      bestScore: 82,
      worstScore: 98,
      handicapEstimate: 16.4,
      handicapTrend: -0.8,
    },
    time: {},
    scoring: {},
    courseDistribution: [],
    records: {},
    courses: [],
    holes: [],
    clubs: [],
    issues: [{ issue: 'approach_short', count: 6, refs: ['900001:7'] }],
    dataQuality: [],
    drillDown: {},
    ...overrides,
  }
}

function courseOptionsFixture(): MobileCourseOptionsResponse {
  return {
    schema: 'ai-caddie-mobile-course-options-v1',
    dataMode: 'fixture',
    total: 4,
    courses: [
      {
        globalId: 31795,
        name: '黑骑士 B/C',
        roundCount: 2,
        holes: 18,
        geometryCoverage: 'partial',
        sourceRefs: ['900001'],
      },
      {
        globalId: 31870,
        name: '观澜湖·奥拉沙宝场',
        roundCount: 9,
        holes: 18,
        geometryCoverage: 'ready',
        sourceRefs: ['900002'],
      },
      {
        globalId: 40001,
        name: '翡翠湖国际高尔夫',
        roundCount: 5,
        holes: 18,
        geometryCoverage: 'partial',
        sourceRefs: ['900003'],
      },
      {
        globalId: 40002,
        name: '深圳沙河',
        roundCount: 7,
        holes: 18,
        geometryCoverage: 'missing',
        sourceRefs: ['900004'],
      },
    ],
    emptyState: null,
    generatedAt: '2026-06-05T08:00:00Z',
  }
}

function searchResponse(): CourseSearchResponse {
  return {
    schema: 'ai-caddie-course-search-v1',
    query: '观澜湖',
    matches: [
      { globalId: 31870, name: '观澜湖·奥拉沙宝场', holes: 18, city: '深圳', province: '广东', ratio: 0.92 },
      { globalId: 31999, name: '观澜湖·世界杯场', holes: 18, city: '深圳', province: '广东', ratio: 0.88 },
    ],
  }
}

function renderHome(overrides: Partial<Parameters<typeof HomeOverview>[0]> = {}) {
  const onSearchCourses = vi.fn(async () => searchResponse())
  const onPrepCourse = vi.fn()
  const onOpenRoundDetail = vi.fn()
  const onNavigateHistory = vi.fn()
  const onNavigateAnalysis = vi.fn()
  render(
    <HomeOverview
      overview={overviewFixture()}
      stats={statsFixture()}
      courseOptions={courseOptionsFixture()}
      onSearchCourses={onSearchCourses}
      onPrepCourse={onPrepCourse}
      onOpenRoundDetail={onOpenRoundDetail}
      onNavigateHistory={onNavigateHistory}
      onNavigateAnalysis={onNavigateAnalysis}
      {...overrides}
    />,
  )
  return { onSearchCourses, onPrepCourse, onOpenRoundDetail, onNavigateHistory, onNavigateAnalysis }
}

describe('HomeOverview', () => {
  it('sorts frequent courses by round count, caps them at three, and preps the clicked course', async () => {
    const { onPrepCourse } = renderHome()

    expect(screen.getByText('想备哪场?')).toBeInTheDocument()
    const prepButtons = screen.getAllByRole('button', { name: /^去备战 / })
    expect(prepButtons.map((button) => button.getAttribute('aria-label'))).toEqual([
      '去备战 观澜湖·奥拉沙宝场',
      '去备战 深圳沙河',
      '去备战 翡翠湖国际高尔夫',
    ])
    expect(screen.getByText('打过 9 次')).toBeInTheDocument()
    // The 4th course (least played) is capped out of the list.
    expect(screen.queryByText('黑骑士 B/C')).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '去备战 深圳沙河' }))
    expect(onPrepCourse).toHaveBeenCalledWith(40002)
  })

  it('search submit calls onSearchCourses and renders the matches', async () => {
    const { onSearchCourses } = renderHome()

    await userEvent.type(screen.getByLabelText('搜索球场'), ' 观澜湖 ')
    await userEvent.click(screen.getByRole('button', { name: '搜索' }))

    expect(onSearchCourses).toHaveBeenCalledWith('观澜湖')
    expect(await screen.findByText('观澜湖·世界杯场')).toBeInTheDocument()
    expect(screen.getAllByText('深圳 · 18洞').length).toBe(2)
  })

  it('submitting with Enter also searches, and picking a match preps that course', async () => {
    const { onSearchCourses, onPrepCourse } = renderHome()

    await userEvent.type(screen.getByLabelText('搜索球场'), '观澜湖{Enter}')
    expect(onSearchCourses).toHaveBeenCalledWith('观澜湖')

    await userEvent.click(await screen.findByRole('button', { name: /观澜湖·世界杯场/ }))
    expect(onPrepCourse).toHaveBeenCalledWith(31999)
  })

  it('shows 没有找到球场 when the search returns no matches', async () => {
    renderHome({
      onSearchCourses: vi.fn(async () => ({
        schema: 'ai-caddie-course-search-v1' as const,
        query: '不存在',
        matches: [],
      })),
    })

    await userEvent.type(screen.getByLabelText('搜索球场'), '不存在{Enter}')
    expect(await screen.findByText('没有找到球场')).toBeInTheDocument()
  })

  it('上一场 shows the newest round and 看复盘 opens its detail', async () => {
    const { onOpenRoundDetail } = renderHome()

    const card = screen.getByLabelText('上一场')
    expect(within(card).getByText('88')).toBeInTheDocument()
    expect(within(card).getByText('+16')).toBeInTheDocument()
    expect(within(card).getByText('翡翠湖国际高尔夫')).toBeInTheDocument()
    expect(within(card).getByText('06-05')).toBeInTheDocument()
    expect(within(card).queryByText('观澜湖·奥拉沙宝场')).not.toBeInTheDocument()

    await userEvent.click(within(card).getByRole('button', { name: '看复盘 →' }))
    expect(onOpenRoundDetail).toHaveBeenCalledWith('900010')
  })

  it('shows 还没有球局 when there are no rounds', () => {
    renderHome({ overview: overviewFixture({ recentRounds: [] }) })
    expect(within(screen.getByLabelText('上一场')).getByText('还没有球局')).toBeInTheDocument()
  })

  it('近期状态 renders the handicap estimate with trend and 看历史 navigates', async () => {
    const { onNavigateHistory } = renderHome()

    const card = screen.getByLabelText('近期状态')
    expect(within(card).getByText('近10场')).toBeInTheDocument()
    expect(within(card).getByText('16.4')).toBeInTheDocument()
    expect(within(card).getByText(/▼ 0.8/)).toBeInTheDocument()
    expect(within(card).getByText('89.5')).toBeInTheDocument()

    await userEvent.click(within(card).getByRole('button', { name: '看历史 →' }))
    expect(onNavigateHistory).toHaveBeenCalledTimes(1)
  })

  it('本周该练 banner uses the Chinese issue label and 看强弱分析 navigates', async () => {
    const { onNavigateAnalysis } = renderHome()

    const banner = screen.getByLabelText('本周该练')
    expect(within(banner).getByText('攻果岭偏短')).toBeInTheDocument()

    await userEvent.click(within(banner).getByRole('button', { name: /看强弱分析/ }))
    expect(onNavigateAnalysis).toHaveBeenCalledTimes(1)
  })

  it('renders with null stats and course options: dashes, no banner, no frequent courses', () => {
    renderHome({ stats: null, courseOptions: null })

    expect(screen.getByText('你好 👋')).toBeInTheDocument()
    expect(screen.getByText('想备哪场?')).toBeInTheDocument()
    expect(screen.queryByLabelText('本周该练')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^去备战 / })).not.toBeInTheDocument()
    const card = screen.getByLabelText('近期状态')
    expect(within(card).getAllByText('—').length).toBeGreaterThan(0)
  })

  it('hides the banner when stats has no issues', () => {
    renderHome({ stats: statsFixture({ issues: [] }) })
    expect(screen.queryByLabelText('本周该练')).not.toBeInTheDocument()
  })

  it('renders the empty state title and detail instead of dash-cards', () => {
    renderHome({
      overview: overviewFixture({
        metrics: {
          totalRounds: 0,
          eighteenHoleRounds: 0,
          nineHoleRounds: 0,
          courseCount: 0,
          shotCount: 0,
          average18: null,
          recent10Average: null,
          bestScore: null,
        },
        recentRounds: [],
        emptyState: {
          kind: 'no_rounds',
          title: 'No local Garmin data loaded',
          detail:
            'The v2 UI is connected, but this remote workspace has 0 rounds and 0 shot rows. Sync Garmin data into data/scorecards and data/shots, or run the fetch workflow, then refresh.',
        },
      }),
    })

    expect(screen.getByText('你好 👋')).toBeInTheDocument()
    expect(screen.getByText('No local Garmin data loaded')).toBeInTheDocument()
    expect(screen.getByText(/this remote workspace has 0 rounds and 0 shot rows/i)).toBeInTheDocument()
    expect(screen.queryByLabelText('上一场')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('近期状态')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('搜索球场')).not.toBeInTheDocument()
  })

  it('falls back to a zh empty state when totalRounds is 0 without an emptyState payload', () => {
    renderHome({
      overview: overviewFixture({
        metrics: {
          totalRounds: 0,
          eighteenHoleRounds: 0,
          nineHoleRounds: 0,
          courseCount: 0,
          shotCount: 0,
          average18: null,
          recent10Average: null,
          bestScore: null,
        },
        recentRounds: [],
        emptyState: null,
      }),
    })

    expect(screen.getByText('还没有球局数据')).toBeInTheDocument()
    expect(screen.queryByLabelText('近期状态')).not.toBeInTheDocument()
  })
})
