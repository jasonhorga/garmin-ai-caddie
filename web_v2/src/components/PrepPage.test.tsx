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

function statsHoleRow(hole: number, overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return { courseKey: 'black_knight', hole, sampleCount: 3, averageToPar: 1, worstToPar: 3, ...overrides }
}

function fiveHolePrep(globalId: number): CoursePrepResponse {
  return {
    ...prepResponse(globalId),
    holeCount: 5,
    holes: [prepHole(1, 4, 410), prepHole(2, 4, 395), prepHole(3, 5, 560), prepHole(4, 4, 430), prepHole(5, 3, 180)],
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

  it('selecting a frequent course hands its globalId and name to onSelectCourse', async () => {
    const { onSelectCourse } = renderPrep({ globalId: null })

    await userEvent.click(screen.getByRole('button', { name: '去备战 观澜湖·奥拉沙宝场' }))

    expect(onSelectCourse).toHaveBeenCalledWith(31870, '观澜湖·奥拉沙宝场')
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

  it('header uses the handed-down search name when courseOptions has no match', async () => {
    renderPrep({ globalId: 99999, selectedCourseName: '观澜湖·世界杯场' })

    expect(screen.getByRole('heading', { name: '观澜湖·世界杯场' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: '球场 99999' })).not.toBeInTheDocument()
    expect(await screen.findByText('Par 9 · 总码数 900 码')).toBeInTheDocument()
  })

  it('header prefers the courseOptions name over the handed-down search name', async () => {
    renderPrep({ globalId: 31795, selectedCourseName: '搜索结果名' })

    expect(screen.getByRole('heading', { name: 'Black Knight B/C' })).toBeInTheDocument()
    expect(screen.queryByText('搜索结果名')).not.toBeInTheDocument()
    expect(await screen.findByText('Par 9 · 总码数 900 码')).toBeInTheDocument()
  })

  it('hides 你的战绩 when the matched option has no courseKey into stats', async () => {
    renderPrep({ globalId: 31870 })

    expect(screen.getByRole('heading', { name: '观澜湖·奥拉沙宝场' })).toBeInTheDocument()
    expect(await screen.findByText('Par 9 · 总码数 900 码')).toBeInTheDocument()
    expect(screen.queryByText(/你的战绩/)).not.toBeInTheDocument()
  })

  it('switches the three local tabs: 概览 key sections, 逐洞攻略 hole cards, 针对你 tips state', async () => {
    renderPrep()
    await screen.findByText('Par 9 · 总码数 900 码')

    const tabs = screen.getByRole('navigation', { name: '备战页签' })
    expect(within(tabs).getByRole('button', { name: '概览' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('region', { name: '关键洞' })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: '逐洞速览' })).toBeInTheDocument()

    await userEvent.click(within(tabs).getByRole('button', { name: '逐洞攻略' }))
    expect(within(tabs).getByRole('button', { name: '逐洞攻略' })).toHaveAttribute('aria-current', 'page')
    expect(within(tabs).getByRole('button', { name: '概览' })).not.toHaveAttribute('aria-current')
    expect(screen.getByText('1 洞')).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: '逐洞速览' })).not.toBeInTheDocument()

    await userEvent.click(within(tabs).getByRole('button', { name: '针对你' }))
    expect(screen.getByText('暂无足够数据生成提示')).toBeInTheDocument()
    expect(screen.queryByText('1 洞')).not.toBeInTheDocument()
  })

  it('逐洞攻略 renders a PrepHoleCard per hole, in order, wrapped in prep-hole-{n} anchors', async () => {
    const { view } = renderPrep()
    await screen.findByText('Par 9 · 总码数 900 码')
    const tabs = screen.getByRole('navigation', { name: '备战页签' })

    await userEvent.click(within(tabs).getByRole('button', { name: '逐洞攻略' }))

    expect(screen.queryByText(/已加载/)).not.toBeInTheDocument()
    const anchors = Array.from(view.container.querySelectorAll('[id^="prep-hole-"]'))
    expect(anchors.map((anchor) => anchor.id)).toEqual(['prep-hole-1', 'prep-hole-2'])
    expect(within(anchors[0] as HTMLElement).getByText('1 洞')).toBeInTheDocument()
    expect(within(anchors[0] as HTMLElement).getByText('Par 4')).toBeInTheDocument()
    expect(within(anchors[1] as HTMLElement).getByText('2 洞')).toBeInTheDocument()
    expect(within(anchors[1] as HTMLElement).getByText('Par 5')).toBeInTheDocument()
  })

  it('switching to a different course resets the tab to 概览', async () => {
    const { view, props } = renderPrep()
    await screen.findByText('Par 9 · 总码数 900 码')
    const tabs = screen.getByRole('navigation', { name: '备战页签' })
    await userEvent.click(within(tabs).getByRole('button', { name: '针对你' }))
    expect(within(tabs).getByRole('button', { name: '针对你' })).toHaveAttribute('aria-current', 'page')

    view.rerender(<PrepPage {...props} globalId={31870} />)

    const tabsAfter = screen.getByRole('navigation', { name: '备战页签' })
    expect(within(tabsAfter).getByRole('button', { name: '概览' })).toHaveAttribute('aria-current', 'page')
    expect(within(tabsAfter).getByRole('button', { name: '针对你' })).not.toHaveAttribute('aria-current')
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

  it('discards a stale tips response that resolves after the course changed', async () => {
    let resolveFirst!: (value: PrepTipsResponse) => void
    const first = new Promise<PrepTipsResponse>((resolve) => {
      resolveFirst = resolve
    })
    fetchPrepTipsMock.mockImplementationOnce(() => first)
    fetchPrepTipsMock.mockImplementationOnce(async () => ({
      schema: 'ai-caddie-prep-tips-v1',
      courseKey: null,
      tips: [{ priority: 1, severity: 'high', text: '新球场:关注最长洞', basis: 'course.prepHoles', sourceRefs: [] }],
    }))
    const { view, props } = renderPrep()

    view.rerender(<PrepPage {...props} globalId={31870} />)
    await screen.findByText(/Par \d+ · 总码数/)
    const tabs = screen.getByRole('navigation', { name: '备战页签' })
    await userEvent.click(within(tabs).getByRole('button', { name: '针对你' }))
    expect(await screen.findByText('新球场:关注最长洞')).toBeInTheDocument()

    // The stale 31795 tips resolve late — the tipsSeq guard must drop them
    // (an empty stale payload would otherwise blank the fresh tip or regress
    // the tab to 加载中).
    await act(async () => {
      resolveFirst(tipsResponse())
      await first
    })

    expect(screen.getByText('新球场:关注最长洞')).toBeInTheDocument()
    expect(screen.queryByText('个性化提示加载中…')).not.toBeInTheDocument()
    expect(screen.queryByText('暂无足够数据生成提示')).not.toBeInTheDocument()
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

describe('PrepPage 概览 tab', () => {
  it('played course: top-3 key holes by averageToPar with sampleCount≥2, pars joined from prep holes', async () => {
    fetchCoursePrepMock.mockImplementation(async (globalId: number) => fiveHolePrep(globalId))
    renderPrep({
      allStats: {
        ...allStatsFixture(),
        holes: [
          // sampleCount 1 → excluded even though it has the worst average.
          statsHoleRow(2, { averageToPar: 2.5, sampleCount: 1, worstToPar: 6 }),
          statsHoleRow(3, { averageToPar: 1.8, sampleCount: 3, worstToPar: 4 }),
          statsHoleRow(1, { averageToPar: 0.6, sampleCount: 2, worstToPar: 2 }),
          statsHoleRow(4, { averageToPar: 1.2, sampleCount: 5, worstToPar: 3 }),
          statsHoleRow(5, { averageToPar: -0.2, sampleCount: 4, worstToPar: 1 }),
          // Another course's row → must be filtered out by courseKey.
          statsHoleRow(1, { courseKey: 'other_course', averageToPar: 9, sampleCount: 9, worstToPar: 9 }),
        ],
      },
    })
    await screen.findByText('Par 20 · 总码数 1975 码')

    const keyHoles = screen.getByRole('region', { name: '关键洞' })
    const titles = within(keyHoles)
      .getAllByRole('heading', { level: 4 })
      .map((heading) => heading.textContent)
    expect(titles).toEqual(['第3洞 · Par5', '第4洞 · Par4', '第1洞 · Par4'])
    const topCard = within(keyHoles).getByText('第3洞 · Par5').closest('article') as HTMLElement
    expect(within(topCard).getByText('平均 +1.8')).toBeInTheDocument()
    expect(within(topCard).getByText('最差 +4')).toBeInTheDocument()
    expect(within(keyHoles).queryByText('长洞注意')).not.toBeInTheDocument()
  })

  it('关键洞 skips stats rows whose hole is outside the loaded holes (another nine)', async () => {
    fetchCoursePrepMock.mockImplementation(async (globalId: number) => fiveHolePrep(globalId))
    renderPrep({
      allStats: {
        ...allStatsFixture(),
        holes: [
          // Worst average of all, but hole 13 belongs to the other nine when
          // only holes 1-5 are loaded — it must not become a 关键洞.
          statsHoleRow(13, { averageToPar: 4, sampleCount: 5, worstToPar: 8 }),
          statsHoleRow(3, { averageToPar: 1.8, sampleCount: 3, worstToPar: 4 }),
          statsHoleRow(1, { averageToPar: 0.6, sampleCount: 2, worstToPar: 2 }),
        ],
      },
    })
    await screen.findByText('Par 20 · 总码数 1975 码')

    const keyHoles = screen.getByRole('region', { name: '关键洞' })
    const titles = within(keyHoles)
      .getAllByRole('heading', { level: 4 })
      .map((heading) => heading.textContent)
    expect(titles).toEqual(['第3洞 · Par5', '第1洞 · Par4'])
    expect(within(keyHoles).queryByText(/第13洞/)).not.toBeInTheDocument()
  })

  it('关键洞 includes back-nine stats rows when the prep payload serves 18 holes', async () => {
    fetchCoursePrepMock.mockImplementation(async (globalId: number) => ({
      ...prepResponse(globalId),
      holeCount: 18,
      holes: Array.from({ length: 18 }, (_, index) => prepHole(index + 1, 4, 400)),
    }))
    renderPrep({
      allStats: {
        ...allStatsFixture(),
        holes: [
          statsHoleRow(13, { averageToPar: 4, sampleCount: 5, worstToPar: 8 }),
          statsHoleRow(3, { averageToPar: 1.8, sampleCount: 3, worstToPar: 4 }),
        ],
      },
    })
    await screen.findByText('Par 72 · 总码数 7200 码')

    const keyHoles = screen.getByRole('region', { name: '关键洞' })
    const titles = within(keyHoles)
      .getAllByRole('heading', { level: 4 })
      .map((heading) => heading.textContent)
    expect(titles).toEqual(['第13洞 · Par4', '第3洞 · Par4'])
  })

  it('unplayed course: falls back to the 3 longest par-4/5 holes with 长洞注意', async () => {
    fetchCoursePrepMock.mockImplementation(async (globalId: number) => fiveHolePrep(globalId))
    renderPrep() // allStatsFixture has no stats.holes rows → unplayed path

    await screen.findByText('Par 20 · 总码数 1975 码')

    const keyHoles = screen.getByRole('region', { name: '关键洞' })
    const titles = within(keyHoles)
      .getAllByRole('heading', { level: 4 })
      .map((heading) => heading.textContent)
    // Par-3 hole 5 (180y) is never a key hole; par-4 hole 2 (395y) is cut at 3.
    expect(titles).toEqual(['第3洞 · Par5 · 560码', '第4洞 · Par4 · 430码', '第1洞 · Par4 · 410码'])
    expect(within(keyHoles).getAllByText('长洞注意')).toHaveLength(3)
    expect(within(keyHoles).queryByText(/平均/)).not.toBeInTheDocument()
  })

  it('falls back to long holes when no row reaches sampleCount 2, while the strip still colors that hole', async () => {
    fetchCoursePrepMock.mockImplementation(async (globalId: number) => fiveHolePrep(globalId))
    renderPrep({
      allStats: { ...allStatsFixture(), holes: [statsHoleRow(1, { averageToPar: 3, sampleCount: 1, worstToPar: 5 })] },
    })
    await screen.findByText('Par 20 · 总码数 1975 码')

    const keyHoles = screen.getByRole('region', { name: '关键洞' })
    expect(within(keyHoles).getAllByText('长洞注意')).toHaveLength(3)
    expect(within(keyHoles).queryByText(/平均/)).not.toBeInTheDocument()
    // The 速览 strip has no sampleCount floor — a single round still colors it.
    const strip = screen.getByRole('region', { name: '逐洞速览' })
    expect(within(strip).getByRole('button', { name: '第1洞 Par4 平均+3' })).toHaveClass('bigover')
  })

  it('逐洞速览 chips bucket averageToPar into under/over/bigover and stay neutral without history', async () => {
    fetchCoursePrepMock.mockImplementation(async (globalId: number) => fiveHolePrep(globalId))
    renderPrep({
      allStats: {
        ...allStatsFixture(),
        holes: [
          statsHoleRow(1, { averageToPar: 0, sampleCount: 2, worstToPar: 2 }),
          statsHoleRow(2, { averageToPar: 0.5, sampleCount: 2, worstToPar: 2 }),
          statsHoleRow(3, { averageToPar: 1, sampleCount: 2, worstToPar: 3 }),
          statsHoleRow(5, { averageToPar: null, sampleCount: 2, worstToPar: null }),
        ],
      },
    })
    await screen.findByText('Par 20 · 总码数 1975 码')

    const strip = screen.getByRole('region', { name: '逐洞速览' })
    expect(within(strip).getByRole('button', { name: '第1洞 Par4 平均0' })).toHaveClass('under')
    const overChip = within(strip).getByRole('button', { name: '第2洞 Par4 平均+0.5' })
    expect(overChip).toHaveClass('over')
    expect(overChip).not.toHaveClass('bigover')
    expect(within(strip).getByRole('button', { name: '第3洞 Par5 平均+1' })).toHaveClass('bigover')
    expect(within(strip).getByRole('button', { name: '第4洞 Par4 未打过' })).toHaveClass('none')
    // A row whose averageToPar is null is as good as unplayed for the strip.
    expect(within(strip).getByRole('button', { name: '第5洞 Par3 未打过' })).toHaveClass('none')
  })

  it('clicking a 逐洞速览 chip switches to 逐洞攻略 and scrolls to that hole anchor', async () => {
    const scrolled: string[] = []
    const scrollSpy = vi.fn(function (this: Element) {
      scrolled.push((this as HTMLElement).id)
    })
    const prototype = Element.prototype as unknown as { scrollIntoView?: unknown }
    prototype.scrollIntoView = scrollSpy
    try {
      renderPrep()
      await screen.findByText('Par 9 · 总码数 900 码')

      await userEvent.click(screen.getByRole('button', { name: '第2洞 Par5 未打过' }))

      const tabs = screen.getByRole('navigation', { name: '备战页签' })
      expect(within(tabs).getByRole('button', { name: '逐洞攻略' })).toHaveAttribute('aria-current', 'page')
      expect(screen.getByText('2 洞')).toBeInTheDocument()
      expect(scrollSpy).toHaveBeenCalledTimes(1)
      expect(scrollSpy).toHaveBeenCalledWith({ behavior: 'smooth', block: 'start' })
      expect(scrolled).toEqual(['prep-hole-2'])
    } finally {
      delete prototype.scrollIntoView
    }
  })
})

describe('PrepPage 针对你 tab', () => {
  async function openForYouTab() {
    await screen.findByText(/Par \d+ · 总码数/)
    const tabs = screen.getByRole('navigation', { name: '备战页签' })
    await userEvent.click(within(tabs).getByRole('button', { name: '针对你' }))
  }

  it('renders tips in delivered order with severity dot classes and basis sub-lines', async () => {
    fetchPrepTipsMock.mockImplementation(async () => ({
      schema: 'ai-caddie-prep-tips-v1',
      courseKey: 'black_knight',
      tips: [
        { priority: 2, severity: 'medium', text: '攻果岭常偏短(38%),本场多带半杆', basis: '攻果岭分布 · 近20轮', sourceRefs: ['stats:approachMiss'] },
        { priority: 1, severity: 'high', text: '开球偏右(58%),第2洞右侧水域注意', basis: '开球方向 · 近20轮', sourceRefs: ['stats:teeDirection'] },
        { priority: 3, severity: 'info', text: '三杆洞稳定(平均+0.3),按部就班', basis: 'Par3 计分', sourceRefs: ['stats:parScoring'] },
      ],
    }))
    renderPrep()
    await openForYouTab()

    // Delivered order is preserved — the page must not re-sort by severity.
    const items = screen.getAllByRole('listitem')
    expect(items).toHaveLength(3)
    expect(items[0]).toHaveTextContent('攻果岭常偏短(38%),本场多带半杆')
    expect(items[0]).toHaveTextContent('攻果岭分布 · 近20轮')
    expect(items[1]).toHaveTextContent('开球偏右(58%),第2洞右侧水域注意')
    expect(items[2]).toHaveTextContent('三杆洞稳定(平均+0.3),按部就班')
    expect(items[0].querySelector('.prep-tip-dot')).toHaveClass('medium')
    expect(items[1].querySelector('.prep-tip-dot')).toHaveClass('high')
    expect(items[2].querySelector('.prep-tip-dot')).toHaveClass('info')
  })

  it('shows 暂无足够数据生成提示 when tips are empty', async () => {
    renderPrep()
    await openForYouTab()

    expect(screen.getByText('暂无足够数据生成提示')).toBeInTheDocument()
    expect(screen.queryByRole('listitem')).not.toBeInTheDocument()
  })

  it('shows a loading line while tips are in flight', async () => {
    fetchPrepTipsMock.mockImplementation(() => new Promise<PrepTipsResponse>(() => {}))
    renderPrep()
    await openForYouTab()

    expect(screen.getByText('个性化提示加载中…')).toBeInTheDocument()
  })

  it('surfaces the tips error inside the tab with 重试 that refetches', async () => {
    fetchPrepTipsMock.mockRejectedValueOnce(new Error('tips boom'))
    renderPrep()
    await screen.findByText('Par 9 · 总码数 900 码')
    // The tips failure belongs to the 针对你 tab — 概览 must stay clean.
    expect(screen.queryByLabelText('个性化提示加载失败')).not.toBeInTheDocument()

    const tabs = screen.getByRole('navigation', { name: '备战页签' })
    await userEvent.click(within(tabs).getByRole('button', { name: '针对你' }))

    const panel = await screen.findByLabelText('个性化提示加载失败')
    expect(within(panel).getByText('tips boom')).toBeInTheDocument()

    await userEvent.click(within(panel).getByRole('button', { name: '重试' }))

    expect(await screen.findByText('暂无足够数据生成提示')).toBeInTheDocument()
    expect(fetchPrepTipsMock).toHaveBeenCalledTimes(2)
    expect(screen.queryByLabelText('个性化提示加载失败')).not.toBeInTheDocument()
  })
})
