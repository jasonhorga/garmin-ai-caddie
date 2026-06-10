import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type {
  CoursePrepResponse,
  CourseSearchResponse,
  HistoryStatsResponse,
  MobileCourseOptionsResponse,
  PrepTipsResponse,
} from '../types'
import { fetchCoursePrep, fetchPrepTips } from '../api'
import { PrepPage } from './PrepPage'

vi.mock('../api', () => ({
  fetchCoursePrep: vi.fn(),
  fetchPrepTips: vi.fn(),
}))

const fetchCoursePrepMock = vi.mocked(fetchCoursePrep)
const fetchPrepTipsMock = vi.mocked(fetchPrepTips)

function prepHole(hole: number, par: number, blueYards: number): CoursePrepResponse['holes'][number] {
  return {
    hole,
    par,
    par_source: 'courseview',
    blue_yards: blueYards,
    route_len_m: 380,
    route: [],
    geometryCoverage: 'ready',
    sourceRefs: [`course:31795`],
    missingData: [],
    candidateRoutes: [],
    carryTargets: [],
    steps: [],
    cautions: [],
    landing_m: null,
    tee_club: null,
    hazards: { water_carry: [], bunkers: [] },
  }
}

function prepResponse(globalId: number): CoursePrepResponse {
  return {
    schema: 'ai-caddie-course-prep-v1',
    globalId,
    holeCount: 2,
    clubs: [],
    holes: [prepHole(1, 4, 380), prepHole(2, 5, 520)],
  }
}

function tipsResponse(): PrepTipsResponse {
  return { schema: 'ai-caddie-prep-tips-v1', courseKey: 'black_knight', tips: [] }
}

function courseOptionsFixture(): MobileCourseOptionsResponse {
  return {
    schema: 'ai-caddie-mobile-course-options-v1',
    dataMode: 'fixture',
    total: 2,
    courses: [
      {
        globalId: 31795,
        courseKey: 'black_knight',
        name: 'Black Knight B/C',
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
    ],
    emptyState: null,
    generatedAt: '2026-06-05T08:00:00Z',
  }
}

function allStatsFixture(): HistoryStatsResponse {
  return {
    schema: 'ai-caddie-history-stats-v1',
    dataMode: 'fixture',
    summary: {},
    time: {},
    scoring: {},
    courseDistribution: [],
    records: {},
    courses: [{ courseKey: 'black_knight', courseName: 'Black Knight B', roundCount: 5, average18: 80.5 }],
    holes: [],
    clubs: [],
    issues: [],
    dataQuality: [],
    drillDown: {},
  }
}

function renderPrep(overrides: Partial<Parameters<typeof PrepPage>[0]> = {}) {
  const onSearchCourses = vi.fn(async (): Promise<CourseSearchResponse> => ({
    schema: 'ai-caddie-course-search-v1',
    query: '观澜湖',
    matches: [{ globalId: 31870, name: '观澜湖·奥拉沙宝场', holes: 18, city: '深圳', province: '广东', ratio: 0.92 }],
  }))
  const onSelectCourse = vi.fn()
  const onChangeCourse = vi.fn()
  const props = {
    globalId: 31795 as number | null,
    courseOptions: courseOptionsFixture(),
    allStats: allStatsFixture(),
    adminToken: 'admin-secret',
    onSearchCourses,
    onSelectCourse,
    onChangeCourse,
    ...overrides,
  }
  const view = render(<PrepPage {...props} />)
  return { onSearchCourses, onSelectCourse, onChangeCourse, view, props }
}

beforeEach(() => {
  fetchCoursePrepMock.mockReset()
  fetchPrepTipsMock.mockReset()
  fetchCoursePrepMock.mockImplementation(async (globalId: number) => prepResponse(globalId))
  fetchPrepTipsMock.mockImplementation(async () => tipsResponse())
})

describe('PrepPage entry state', () => {
  it('shows the course finder with the entry heading and fetches nothing', () => {
    renderPrep({ globalId: null })

    expect(screen.getByRole('heading', { name: '选择球场开始备战' })).toBeInTheDocument()
    expect(screen.getByLabelText('搜索球场')).toBeInTheDocument()
    expect(fetchCoursePrepMock).not.toHaveBeenCalled()
    expect(fetchPrepTipsMock).not.toHaveBeenCalled()
    expect(screen.queryByRole('button', { name: '换球场' })).not.toBeInTheDocument()
  })

  it('selecting a frequent course hands its globalId to onSelectCourse', async () => {
    const { onSelectCourse } = renderPrep({ globalId: null })

    await userEvent.click(screen.getByRole('button', { name: '去备战 观澜湖·奥拉沙宝场' }))

    expect(onSelectCourse).toHaveBeenCalledWith(31870)
  })
})

describe('PrepPage course state', () => {
  it('renders the course header joined from courseOptions and allStats once prep loads', async () => {
    renderPrep()

    expect(screen.getByRole('heading', { name: 'Black Knight B/C' })).toBeInTheDocument()
    expect(await screen.findByText('Par 9 · 总码数 900 码')).toBeInTheDocument()
    // 你的战绩 joins stats.courses via the option's courseKey (5 rounds), not the
    // option's own roundCount (2).
    expect(screen.getByText('你的战绩:打过 5 次 · 均杆 80.5')).toBeInTheDocument()
    expect(fetchCoursePrepMock).toHaveBeenCalledWith(31795, { includeShots: true }, 'admin-secret')
    expect(fetchPrepTipsMock).toHaveBeenCalledWith(31795, 'admin-secret')
    expect(screen.queryByText('选择球场开始备战')).not.toBeInTheDocument()
  })

  it('falls back to 球场 {gid} and hides 你的战绩 when courseOptions has no match', async () => {
    renderPrep({ globalId: 99999 })

    expect(screen.getByRole('heading', { name: '球场 99999' })).toBeInTheDocument()
    expect(await screen.findByText('Par 9 · 总码数 900 码')).toBeInTheDocument()
    expect(screen.queryByText(/你的战绩/)).not.toBeInTheDocument()
  })

  it('hides 你的战绩 when the matched option has no courseKey into stats', async () => {
    renderPrep({ globalId: 31870 })

    expect(screen.getByRole('heading', { name: '观澜湖·奥拉沙宝场' })).toBeInTheDocument()
    expect(await screen.findByText('Par 9 · 总码数 900 码')).toBeInTheDocument()
    expect(screen.queryByText(/你的战绩/)).not.toBeInTheDocument()
  })

  it('switches the three local tabs: 概览/针对你 placeholders, 逐洞攻略 shows loaded hole count', async () => {
    renderPrep()
    await screen.findByText('Par 9 · 总码数 900 码')

    const tabs = screen.getByRole('navigation', { name: '备战页签' })
    expect(within(tabs).getByRole('button', { name: '概览' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByText('…')).toBeInTheDocument()

    await userEvent.click(within(tabs).getByRole('button', { name: '逐洞攻略' }))
    expect(within(tabs).getByRole('button', { name: '逐洞攻略' })).toHaveAttribute('aria-current', 'page')
    expect(within(tabs).getByRole('button', { name: '概览' })).not.toHaveAttribute('aria-current')
    expect(screen.getByText('已加载 2 洞')).toBeInTheDocument()

    await userEvent.click(within(tabs).getByRole('button', { name: '针对你' }))
    expect(screen.getByText('…')).toBeInTheDocument()
    expect(screen.queryByText('已加载 2 洞')).not.toBeInTheDocument()
  })

  it('换球场 notifies onChangeCourse', async () => {
    const { onChangeCourse } = renderPrep()

    await userEvent.click(screen.getByRole('button', { name: '换球场' }))

    expect(onChangeCourse).toHaveBeenCalledTimes(1)
  })

  it('shows loading placeholders while prep is in flight', async () => {
    fetchCoursePrepMock.mockImplementation(() => new Promise<CoursePrepResponse>(() => {}))
    renderPrep()

    expect(screen.getByText('Par — · 总码数 — 码')).toBeInTheDocument()
    const tabs = screen.getByRole('navigation', { name: '备战页签' })
    await userEvent.click(within(tabs).getByRole('button', { name: '逐洞攻略' }))
    expect(screen.getByText('球场攻略加载中…')).toBeInTheDocument()
  })

  it('surfaces a prep error with 重试 that refetches', async () => {
    fetchCoursePrepMock.mockRejectedValueOnce(new Error('prep boom'))
    renderPrep()

    const panel = await screen.findByLabelText('球场攻略加载失败')
    expect(within(panel).getByText('prep boom')).toBeInTheDocument()

    await userEvent.click(within(panel).getByRole('button', { name: '重试' }))

    expect(await screen.findByText('Par 9 · 总码数 900 码')).toBeInTheDocument()
    expect(fetchCoursePrepMock).toHaveBeenCalledTimes(2)
  })

  it('surfaces a tips error with 重试 that refetches', async () => {
    fetchPrepTipsMock.mockRejectedValueOnce(new Error('tips boom'))
    renderPrep()

    const panel = await screen.findByLabelText('个性化提示加载失败')
    expect(within(panel).getByText('tips boom')).toBeInTheDocument()

    await userEvent.click(within(panel).getByRole('button', { name: '重试' }))

    await screen.findByText('Par 9 · 总码数 900 码')
    expect(fetchPrepTipsMock).toHaveBeenCalledTimes(2)
    expect(screen.queryByLabelText('个性化提示加载失败')).not.toBeInTheDocument()
  })

  it('discards a stale prep response that resolves after the course changed', async () => {
    let resolveFirst!: (value: CoursePrepResponse) => void
    const first = new Promise<CoursePrepResponse>((resolve) => {
      resolveFirst = resolve
    })
    fetchCoursePrepMock.mockImplementationOnce(() => first)
    fetchCoursePrepMock.mockImplementationOnce(async () => ({
      ...prepResponse(31870),
      holes: [prepHole(1, 3, 150), prepHole(2, 3, 160)],
    }))
    const { view, props } = renderPrep()

    view.rerender(<PrepPage {...props} globalId={31870} />)
    expect(await screen.findByText('Par 6 · 总码数 310 码')).toBeInTheDocument()

    // The stale 31795 payload resolves late — the seq guard must drop it.
    await act(async () => {
      resolveFirst(prepResponse(31795))
      await first
    })

    expect(screen.getByText('Par 6 · 总码数 310 码')).toBeInTheDocument()
    expect(screen.queryByText('Par 9 · 总码数 900 码')).not.toBeInTheDocument()
  })

  it('shows fresh loading state, not the previous course data, immediately after switching courses', async () => {
    const { view, props } = renderPrep()
    expect(await screen.findByText('Par 9 · 总码数 900 码')).toBeInTheDocument()

    fetchCoursePrepMock.mockImplementation(() => new Promise<CoursePrepResponse>(() => {}))
    fetchPrepTipsMock.mockImplementation(() => new Promise<PrepTipsResponse>(() => {}))
    view.rerender(<PrepPage {...props} globalId={31870} />)

    expect(screen.getByRole('heading', { name: '观澜湖·奥拉沙宝场' })).toBeInTheDocument()
    expect(screen.getByText('Par — · 总码数 — 码')).toBeInTheDocument()
    expect(screen.queryByText('Par 9 · 总码数 900 码')).not.toBeInTheDocument()
  })
})
