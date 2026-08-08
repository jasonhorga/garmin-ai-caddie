import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type {
  CoursePrepHole,
  CoursePrepResponse,
  CourseSearchResponse,
  HistoryStatsResponse,
  LiveRoundPackageResponse,
  MobileCourseOptionsResponse,
  PrepTipsResponse,
} from '../types'
import { fetchCoursePrep, fetchMobileCoursePackage, fetchPrepTips } from '../api'
import { PrepPage } from './PrepPage'

vi.mock('../api', () => ({
  fetchCoursePrep: vi.fn(),
  fetchMobileCoursePackage: vi.fn(),
  fetchPrepTips: vi.fn(),
  topoImageUrl: (gid: number, hole: number) => `/api/v2/courses/${gid}/holes/${hole}/topo.png`,
  prewarmCourseTopo: vi.fn(async () => undefined),
  prefetchTopoImage: vi.fn(),
}))

const fetchCoursePrepMock = vi.mocked(fetchCoursePrep)
const fetchMobileCoursePackageMock = vi.mocked(fetchMobileCoursePackage)
const fetchPrepTipsMock = vi.mocked(fetchPrepTips)

function prepHole(hole: number, par: number, blueYards: number, extra: Partial<CoursePrepHole> = {}): CoursePrepHole {
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
    ...extra,
  }
}

// Hole 1 carries real geometry (map + overlay) + a shot scatter so the canvas,
// caddie recommendation and distance table all have deterministic inputs.
function richHole1(): CoursePrepHole {
  return prepHole(1, 4, 380, {
    route_len_m: 350,
    landing_m: 210,
    tee_club: '1D',
    steps: [
      { club: '1D', note: '开球瞄球道左侧' },
      { club: '8I', note: '第二杆攻果岭中部' },
    ],
    cautions: ['右侧长草密集,宁左勿右'],
    hazards: { water_carry: [[100, 150]], bunkers: [[200, 8]] },
    map: {
      image: 'data:image/png;base64,AAAA',
      overlay: {
        w: 360,
        h: 360,
        ppm: 0.85,
        ln: 350,
        route: [
          [180, 330, 0],
          [180, 40, 350],
        ],
      },
    },
    yourShots: [{ x: 170, y: 150, club: '1D', shotType: 'TEE', roundId: '900001' }],
  })
}

function prepResponse(globalId: number): CoursePrepResponse {
  return {
    schema: 'ai-caddie-course-prep-v1',
    globalId,
    holeCount: 2,
    clubs: [
      { name: '1D', m: 220, yd: 241 },
      { name: '8I', m: 131, yd: 143 },
    ],
    holes: [richHole1(), prepHole(2, 5, 520, { route_len_m: 480 })],
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
  fetchMobileCoursePackageMock.mockReset()
  fetchPrepTipsMock.mockReset()
  fetchMobileCoursePackageMock.mockImplementation(async (globalId: number) => ({
    holes: [
      { number: 1, sourceGlobalId: globalId, sourceLocalHole: 1 },
      { number: 2, sourceGlobalId: globalId, sourceLocalHole: 2 },
    ],
  } as unknown as LiveRoundPackageResponse))
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

describe('PrepPage workbench', () => {
  it('renders the course crumb, hole-list totals + record, and requests the shot scatter', async () => {
    renderPrep()

    expect(screen.getByRole('heading', { name: 'Black Knight B/C' })).toBeInTheDocument()
    expect(await screen.findByText('PAR 9 · 900 码')).toBeInTheDocument()
    // 你的战绩 joins stats.courses via the option's courseKey (5 rounds), not the
    // option's own roundCount (2).
    expect(screen.getByText('你的战绩:打过 5 次 · 均杆 80.5')).toBeInTheDocument()
    expect(fetchMobileCoursePackageMock).toHaveBeenCalledWith(
      31795,
      { roundId: 'web-prep-31795', backgroundGeometry: true, includeEventCursor: false },
      'admin-secret',
    )
    expect(fetchCoursePrepMock).toHaveBeenCalledWith(
      31795,
      { holes: [1, 2], render: false, includeShots: true },
      'admin-secret',
    )
    await waitFor(() => expect(fetchPrepTipsMock).toHaveBeenCalledWith(31795, 'admin-secret'))
    expect(screen.queryByText('选择球场开始备战')).not.toBeInTheDocument()
  })

  it('lists every hole and selects the first by default, driving the canvas + inspector', async () => {
    renderPrep()
    await screen.findByText('PAR 9 · 900 码')

    const holeButtons = screen.getAllByRole('button', { name: /第\d洞 Par\d/ })
    expect(holeButtons.map((button) => button.getAttribute('aria-label'))).toEqual([
      '第1洞 Par4 380码',
      '第2洞 Par5 520码',
    ])
    // hole 1 is active by default → its canvas + inspector are on screen.
    expect(holeButtons[0]).toHaveAttribute('aria-current', 'true')
    expect(screen.getByLabelText('第1洞球道图')).toBeInTheDocument()
    expect(screen.getByText('你的落点:')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '球童试算 · 第 1 洞' })).toBeInTheDocument()
  })

  it('caddie card recommends the nearest club and shows the hole hazards', async () => {
    const { view } = renderPrep()
    await screen.findByText('PAR 9 · 900 码')

    // Ball opens at the landing (210 m ≈ 230 y): 1D (241 y) is the nearest club.
    const big = view.container.querySelector('.prep-caddie-big')
    expect(big?.textContent).toContain('230')
    const recos = screen.getByLabelText('推荐球杆')
    expect(recos.querySelector('.prep-club.on')?.textContent).toMatch(/^1D/)
    const inspector = screen.getByRole('complementary', { name: '球童试算' })
    expect(within(inspector).getByText('水×1 · 沙×1')).toBeInTheDocument()
    expect(within(inspector).getByText('过水需')).toBeInTheDocument()
  })

  it('selecting another hole re-drives the canvas + inspector to that hole', async () => {
    renderPrep()
    await screen.findByText('PAR 9 · 900 码')

    await userEvent.click(screen.getByRole('button', { name: '第2洞 Par5 520码' }))

    expect(screen.getByRole('button', { name: '第2洞 Par5 520码' })).toHaveAttribute('aria-current', 'true')
    expect(screen.getByRole('button', { name: '第1洞 Par4 380码' })).not.toHaveAttribute('aria-current')
    expect(screen.getByLabelText('第2洞球道图')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '球童试算 · 第 2 洞' })).toBeInTheDocument()
    // Hole 2 has no scatter, so the shot legend is gone.
    expect(screen.queryByText('你的落点:')).not.toBeInTheDocument()
  })

  it('marks the played key hole and colors its average chip', async () => {
    renderPrep({
      allStats: {
        ...allStatsFixture(),
        holes: [statsHoleRow(1, { averageToPar: 1.1, sampleCount: 5, worstToPar: 3 })],
      },
    })
    await screen.findByText('PAR 9 · 900 码')

    const holeOne = screen.getByRole('button', { name: '第1洞 Par4 380码' })
    expect(within(holeOne).getByText('关键')).toBeInTheDocument()
    const chip = within(holeOne).getByText('平均+1.1')
    expect(chip).toHaveClass('bigover')
    // Hole 2 has no history → no chip, no key tag.
    const holeTwo = screen.getByRole('button', { name: '第2洞 Par5 520码' })
    expect(within(holeTwo).queryByText(/平均/)).not.toBeInTheDocument()
    expect(within(holeTwo).queryByText('关键')).not.toBeInTheDocument()
  })

  it('falls back to 球场 {gid} and hides 你的战绩 when courseOptions has no match', async () => {
    renderPrep({ globalId: 99999 })

    expect(screen.getByRole('heading', { name: '球场 99999' })).toBeInTheDocument()
    expect(await screen.findByText('PAR 9 · 900 码')).toBeInTheDocument()
    expect(screen.queryByText(/你的战绩/)).not.toBeInTheDocument()
  })

  it('header uses the handed-down search name when courseOptions has no match', async () => {
    renderPrep({ globalId: 99999, selectedCourseName: '观澜湖·世界杯场' })

    expect(screen.getByRole('heading', { name: '观澜湖·世界杯场' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: '球场 99999' })).not.toBeInTheDocument()
    await screen.findByText('PAR 9 · 900 码')
  })

  it('header prefers the courseOptions name over the handed-down search name', async () => {
    renderPrep({ globalId: 31795, selectedCourseName: '搜索结果名' })

    expect(screen.getByRole('heading', { name: 'Black Knight B/C' })).toBeInTheDocument()
    expect(screen.queryByText('搜索结果名')).not.toBeInTheDocument()
    await screen.findByText('PAR 9 · 900 码')
  })

  it('换球场 notifies onChangeCourse', async () => {
    const { onChangeCourse } = renderPrep()

    await userEvent.click(screen.getByRole('button', { name: '换球场' }))

    expect(onChangeCourse).toHaveBeenCalledTimes(1)
  })

  it('shows the loading panel and hides the workbench while prep is in flight', async () => {
    fetchCoursePrepMock.mockImplementation(() => new Promise<CoursePrepResponse>(() => {}))
    fetchPrepTipsMock.mockImplementation(() => new Promise<PrepTipsResponse>(() => {}))
    renderPrep()

    expect(screen.getByText('球场攻略加载中…')).toBeInTheDocument()
    expect(screen.queryByText(/PAR/)).not.toBeInTheDocument()
    expect(screen.queryByLabelText('球童试算')).not.toBeInTheDocument()
  })

  it('surfaces a prep error with 重试 that refetches', async () => {
    fetchCoursePrepMock.mockRejectedValueOnce(new Error('prep boom'))
    renderPrep()

    const panel = await screen.findByLabelText('球场攻略加载失败')
    expect(within(panel).getByText('prep boom')).toBeInTheDocument()

    await userEvent.click(within(panel).getByRole('button', { name: '重试' }))

    expect(await screen.findByText('PAR 9 · 900 码')).toBeInTheDocument()
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
    expect(await screen.findByText('PAR 6 · 310 码')).toBeInTheDocument()

    // The stale 31795 payload resolves late — the seq guard must drop it.
    await act(async () => {
      resolveFirst(prepResponse(31795))
      await first
    })

    expect(screen.getByText('PAR 6 · 310 码')).toBeInTheDocument()
    expect(screen.queryByText('PAR 9 · 900 码')).not.toBeInTheDocument()
  })

  it('shows fresh loading state, not the previous course data, immediately after switching courses', async () => {
    const { view, props } = renderPrep()
    expect(await screen.findByText('PAR 9 · 900 码')).toBeInTheDocument()

    fetchCoursePrepMock.mockImplementation(() => new Promise<CoursePrepResponse>(() => {}))
    fetchPrepTipsMock.mockImplementation(() => new Promise<PrepTipsResponse>(() => {}))
    view.rerender(<PrepPage {...props} globalId={31870} />)

    expect(screen.getByRole('heading', { name: '观澜湖·奥拉沙宝场' })).toBeInTheDocument()
    expect(screen.queryByText('PAR 9 · 900 码')).not.toBeInTheDocument()
    expect(screen.getByText('球场攻略加载中…')).toBeInTheDocument()
  })
})

describe('PrepPage 针对你 tips (inspector)', () => {
  it('renders tips in delivered order with severity dots + zh 依据, mapping machine basis keys', async () => {
    fetchPrepTipsMock.mockImplementation(async () => ({
      schema: 'ai-caddie-prep-tips-v1',
      courseKey: 'black_knight',
      tips: [
        { priority: 2, severity: 'medium', text: '攻果岭常偏短(38%),本场多带半杆', basis: 'course.approachMiss', sourceRefs: ['stats:approachMiss'] },
        { priority: 1, severity: 'high', text: '开球偏右(58%),第2洞右侧水域注意', basis: 'course.teeDirection', sourceRefs: ['stats:teeDirection'] },
        { priority: 3, severity: 'info', text: '三杆洞稳定(平均+0.3),按部就班', basis: 'course.parScoring.par3', sourceRefs: ['stats:parScoring'] },
      ],
    }))
    renderPrep()
    await screen.findByText('PAR 9 · 900 码')
    await screen.findByText('攻果岭常偏短(38%),本场多带半杆')

    const items = screen.getAllByRole('listitem').filter((item) => item.classList.contains('prep-tip'))
    expect(items).toHaveLength(3)
    expect(items[0]).toHaveTextContent('攻果岭常偏短(38%),本场多带半杆')
    expect(items[0]).toHaveTextContent('依据:你在本场的攻果岭落点')
    expect(items[1]).toHaveTextContent('开球偏右(58%),第2洞右侧水域注意')
    expect(items[2]).toHaveTextContent('三杆洞稳定(平均+0.3),按部就班')
    expect(items[0].querySelector('.prep-tip-dot')).toHaveClass('medium')
    expect(items[1].querySelector('.prep-tip-dot')).toHaveClass('high')
  })

  it('hides the 依据 line for unknown machine basis keys instead of rendering them raw', async () => {
    fetchPrepTipsMock.mockImplementation(async () => ({
      schema: 'ai-caddie-prep-tips-v1',
      courseKey: 'black_knight',
      tips: [{ priority: 1, severity: 'high', text: '保守开局', basis: 'course.someFutureKey', sourceRefs: [] }],
    }))
    renderPrep()
    await screen.findByText('PAR 9 · 900 码')

    expect(await screen.findByText('保守开局')).toBeInTheDocument()
    expect(screen.queryByText(/course\.someFutureKey/)).not.toBeInTheDocument()
    expect(screen.queryByText(/依据/)).not.toBeInTheDocument()
  })

  it('shows 暂无足够数据生成提示 when tips are empty', async () => {
    renderPrep()
    await screen.findByText('PAR 9 · 900 码')

    expect(await screen.findByText('暂无足够数据生成提示')).toBeInTheDocument()
  })

  it('surfaces the tips error inside the inspector with 重试 that refetches', async () => {
    fetchPrepTipsMock.mockRejectedValueOnce(new Error('tips boom'))
    renderPrep()
    await screen.findByText('PAR 9 · 900 码')

    const panel = await screen.findByLabelText('个性化提示加载失败')
    expect(within(panel).getByText('tips boom')).toBeInTheDocument()

    await userEvent.click(within(panel).getByRole('button', { name: '重试' }))

    expect(await screen.findByText('暂无足够数据生成提示')).toBeInTheDocument()
    expect(fetchPrepTipsMock).toHaveBeenCalledTimes(2)
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

    // Tips now wait until the matching course package/prep is ready. Let the first course reach
    // that point so `first` genuinely represents an in-flight stale response.
    await screen.findByText('PAR 9 · 900 码')
    await waitFor(() => expect(fetchPrepTipsMock).toHaveBeenCalledTimes(1))

    view.rerender(<PrepPage {...props} globalId={31870} />)
    await screen.findByText(/PAR \d+ · /)
    expect(await screen.findByText('新球场:关注最长洞')).toBeInTheDocument()

    await act(async () => {
      resolveFirst(tipsResponse())
      await first
    })

    expect(screen.getByText('新球场:关注最长洞')).toBeInTheDocument()
    expect(screen.queryByText('暂无足够数据生成提示')).not.toBeInTheDocument()
  })
})
