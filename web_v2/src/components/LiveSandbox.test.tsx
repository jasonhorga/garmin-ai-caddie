import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ComponentProps } from 'react'
import type {
  CaddieContextResponse,
  CaddieDecisionResponse,
  CoursePrepHole,
  CoursePrepOverlay,
  CoursePrepResponse,
  CourseSearchResponse,
  MobileCourseOptionsResponse,
  RoundCard as RoundCardType,
} from '../types'
import { fetchCaddieContext, fetchCaddieDecision, fetchCoursePrep, fetchWeatherSnapshot } from '../api'
import { LiveSandbox } from './LiveSandbox'

vi.mock('../api', () => ({
  fetchCoursePrep: vi.fn(),
  fetchCaddieContext: vi.fn(),
  fetchCaddieDecision: vi.fn(),
  fetchWeatherSnapshot: vi.fn(),
}))

const fetchCoursePrepMock = vi.mocked(fetchCoursePrep)
const fetchCaddieContextMock = vi.mocked(fetchCaddieContext)
const fetchCaddieDecisionMock = vi.mocked(fetchCaddieDecision)
const fetchWeatherSnapshotMock = vi.mocked(fetchWeatherSnapshot)

const overlay: CoursePrepOverlay = {
  w: 200,
  h: 200,
  ppm: 1,
  ln: 200,
  route: [
    [0, 0, 0],
    [100, 0, 100],
    [100, 100, 200],
  ],
}

function mappedHole(hole: number): CoursePrepHole {
  return {
    hole,
    par: 4,
    par_source: 'courseview',
    blue_yards: 219,
    route_len_m: 200,
    route: [
      [0, 0, 0],
      [100, 0, 100],
      [100, 100, 200],
    ],
    geometryCoverage: 'ready',
    sourceRefs: [`geometry:31870:${hole}`],
    missingData: [],
    candidateRoutes: [],
    carryTargets: [],
    steps: [],
    cautions: [],
    landing_m: 160,
    tee_club: null,
    hazards: { water_carry: [], bunkers: [] },
    map: { image: 'data:image/jpeg;base64,', overlay },
  }
}

function unmappedHole(hole: number): CoursePrepHole {
  return {
    hole,
    par: 4,
    par_source: 'estimate',
    blue_yards: 0,
    route_len_m: 0,
    route: [],
    geometryCoverage: 'missing',
    sourceRefs: [`geometry:31870:${hole}`],
    missingData: [{ label: 'geometry', reason: 'prodgeometry geometry is missing for this hole' }],
    candidateRoutes: [],
    carryTargets: [],
    steps: [],
    cautions: [],
    landing_m: null,
    tee_club: null,
    hazards: { water_carry: [], bunkers: [] },
  }
}

// 观澜湖 prep: mapped holes 7/9 around an unmapped hole 8 — chip numbers must
// come from the response hole list, not a synthesized 1..N; hole 8 drives the
// degraded no-map mode and 7↔9 the ball-reset-on-switch behavior.
function prepFixture(): CoursePrepResponse {
  return {
    schema: 'ai-caddie-course-prep-v1',
    globalId: 31870,
    holeCount: 3,
    clubs: [{ name: '1W', m: 200, yd: 219 }],
    holes: [mappedHole(7), unmappedHole(8), mappedHole(9)],
  }
}

function blackKnightPrepFixture(): CoursePrepResponse {
  return {
    schema: 'ai-caddie-course-prep-v1',
    globalId: 31795,
    holeCount: 1,
    clubs: [],
    holes: [mappedHole(1)],
  }
}

function courseOptionsFixture(): MobileCourseOptionsResponse {
  return {
    schema: 'ai-caddie-mobile-course-options-v1',
    dataMode: 'fixture',
    total: 2,
    courses: [
      // latestRoundId differs from sourceRefs[0] on purpose: the sourceRef rule
      // must prefer the explicit latestRoundId over the refs-list head.
      { globalId: 31795, courseKey: 'black_knight', name: 'Black Knight B/C', roundCount: 2, latestRoundId: '900777', holes: 18, geometryCoverage: 'partial', sourceRefs: ['900001'] },
      { globalId: 31870, name: '观澜湖·奥拉沙宝场', roundCount: 9, holes: 18, geometryCoverage: 'ready', sourceRefs: ['900002'] },
    ],
    emptyState: null,
    generatedAt: '2026-06-05T08:00:00Z',
  }
}

// Latest ANY round (HomeOverview recentRounds shape) — id chosen so the
// fallback bare-round ref is unambiguous next to the course refs above.
function recentRoundsFixture(): RoundCardType[] {
  return [
    {
      id: '900050',
      date: '2026-05-30T08:00:00',
      courseName: '别的球场',
      courseKey: 'elsewhere',
      holesCompleted: 18,
      score: 80,
      par: 72,
      toPar: 8,
      scoreStrip: [],
      badges: [],
      primaryIssue: null,
    },
  ]
}

function caddieContextFixture(): CaddieContextResponse {
  return {
    schema: 'ai-caddie-context-v1',
    sourceRef: '900002:7',
    shotType: 'approach',
    context: {
      source: 'history_drilldown',
      sourceRef: '900002:7',
      roundId: '900002',
      courseName: '观澜湖·奥拉沙宝场',
      hole: 7,
      globalId: 31870,
      localHole: 7,
      geometry: { coverage: 'ready', hasHazards: true, hasMeshes: true, hazardCount: 2 },
      clubProfiles: { '8I': { clubName: '8I', sampleSize: 9, median: 132, p10: 121, p90: 141 } },
    },
    evidence: [{ label: 'history_ref', value: '900002:7' }],
    missingData: [],
  }
}

// App.test caddieDecisionPayload shape, extended with the option numbers the
// advice card renders (carry/risk/confidence) + explanation/acceptableMiss.
function caddieDecisionFixture(overrides: Partial<CaddieDecisionResponse> = {}): CaddieDecisionResponse {
  return {
    schema: 'ai-caddie-decision-v2',
    decisionId: '900002:7:approach',
    sourceRef: '900002:7',
    evidenceRefs: ['900002:7'],
    shotType: 'approach',
    phase: 'Approach',
    context: { courseName: '观澜湖·奥拉沙宝场', hole: 7 },
    options: [
      { id: 'safe', label: 'Safe', recommendedClub: '9I', carry_m: 118, riskScore: 1, confidence: 'high' },
      { id: 'stock', label: 'Stock', recommendedClub: '8I', carry_m: 132, riskScore: 3.4, confidence: 'medium' },
      { id: 'attack', label: 'Attack', recommendedClub: '7I', carry_m: 146, riskScore: 5.2, confidence: 'low' },
    ],
    selected: { id: 'stock' },
    selectedOptionId: 'stock',
    selectedOption: { id: 'stock' },
    avoidZones: [],
    forbiddenZones: [],
    acceptableMiss: { direction: 'long', rationale: 'short brings the water into play' },
    evidence: [],
    confidence: { level: 'medium' },
    missingData: [{ label: 'weather', reason: 'weather snapshot is missing or incomplete' }],
    auditCriteria: [],
    explanation: { narrative: '8I 中位 132m 覆盖 130m 缺口,短边有水。' },
    ...overrides,
  }
}

function attackDecisionFixture(): CaddieDecisionResponse {
  return caddieDecisionFixture({ selected: { id: 'attack' }, selectedOptionId: 'attack', selectedOption: { id: 'attack' } })
}

beforeEach(() => {
  fetchCoursePrepMock.mockReset()
  fetchCoursePrepMock.mockImplementation(async (globalId: number) =>
    globalId === 31795 ? blackKnightPrepFixture() : prepFixture(),
  )
  fetchCaddieContextMock.mockReset()
  fetchCaddieContextMock.mockImplementation(async () => caddieContextFixture())
  fetchCaddieDecisionMock.mockReset()
  fetchCaddieDecisionMock.mockImplementation(async () => caddieDecisionFixture())
  fetchWeatherSnapshotMock.mockReset()
})

function renderSandbox(overrides: Partial<ComponentProps<typeof LiveSandbox>> = {}) {
  const onSearchCourses = vi.fn(async (): Promise<CourseSearchResponse> => ({
    schema: 'ai-caddie-course-search-v1',
    query: '观澜湖',
    matches: [{ globalId: 99999, name: '观澜湖·世界杯场', holes: 18, city: '深圳', province: '广东', ratio: 0.92 }],
  }))
  const props: ComponentProps<typeof LiveSandbox> = {
    courseOptions: courseOptionsFixture(),
    adminToken: 'admin-secret',
    onSearchCourses,
    recentRounds: recentRoundsFixture(),
    ...overrides,
  }
  const view = render(<LiveSandbox {...props} />)
  return { onSearchCourses, view }
}

async function openSearchCourse() {
  await userEvent.type(screen.getByLabelText('搜索球场'), '观澜湖{Enter}')
  await userEvent.click(await screen.findByRole('button', { name: /观澜湖·世界杯场/ }))
  await screen.findByLabelText('选洞')
}

async function openCourse(name = `开始模拟 观澜湖·奥拉沙宝场`) {
  await userEvent.click(screen.getByRole('button', { name }))
  await screen.findByLabelText('选洞')
}

// PrepHoleCard drag-test mechanics: the overlay svg scales pointer offsets by
// its bounding rect, so pin the rect to the overlay's 200x200.
function mockSvgRect(svg: SVGSVGElement) {
  vi.spyOn(svg, 'getBoundingClientRect').mockReturnValue({
    x: 0,
    y: 0,
    left: 0,
    top: 0,
    right: 200,
    bottom: 200,
    width: 200,
    height: 200,
    toJSON: () => ({}),
  } as DOMRect)
}

describe('LiveSandbox course pick', () => {
  it('entry shows 选择球场开始模拟 with 开始模拟 CTAs and fetches nothing', () => {
    renderSandbox()

    expect(screen.getByRole('heading', { name: '选择球场开始模拟' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '开始模拟 观澜湖·奥拉沙宝场' })).toBeInTheDocument()
    // The sandbox CTA replaces the prep wording on this instance only.
    expect(screen.queryByRole('button', { name: /^去备战 / })).not.toBeInTheDocument()
    expect(fetchCoursePrepMock).not.toHaveBeenCalled()
  })

  it('selecting a frequent course fetches default-holes prep and renders response hole chips', async () => {
    renderSandbox()

    await userEvent.click(screen.getByRole('button', { name: '开始模拟 观澜湖·奥拉沙宝场' }))

    // Default holes, no include_shots/render overrides — the sandbox needs maps.
    expect(fetchCoursePrepMock).toHaveBeenCalledWith(31870, {}, 'admin-secret')
    const chips = within(await screen.findByLabelText('选洞'))
    expect(chips.getByRole('button', { name: '第7洞' })).toHaveAttribute('aria-current', 'true')
    expect(chips.getByRole('button', { name: '第8洞' })).not.toHaveAttribute('aria-current')
    expect(chips.getAllByRole('button')).toHaveLength(3)
    expect(screen.getByRole('heading', { name: '观澜湖·奥拉沙宝场' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: '选择球场开始模拟' })).not.toBeInTheDocument()
  })

  it('shows 沙盘加载中… while the prep fetch is in flight', async () => {
    fetchCoursePrepMock.mockImplementationOnce(() => new Promise<CoursePrepResponse>(() => {}))
    renderSandbox()

    await userEvent.click(screen.getByRole('button', { name: '开始模拟 观澜湖·奥拉沙宝场' }))

    expect(await screen.findByText('沙盘加载中…')).toBeInTheDocument()
    expect(screen.queryByLabelText('选洞')).not.toBeInTheDocument()
  })

  it('a search match hands its course name through to the sandbox header', async () => {
    renderSandbox()

    await userEvent.type(screen.getByLabelText('搜索球场'), '观澜湖{Enter}')
    await userEvent.click(await screen.findByRole('button', { name: /观澜湖·世界杯场/ }))

    expect(fetchCoursePrepMock).toHaveBeenCalledWith(99999, {}, 'admin-secret')
    expect(await screen.findByRole('heading', { name: '观澜湖·世界杯场' })).toBeInTheDocument()
  })

  it('换球场 returns to the course entry', async () => {
    renderSandbox()
    await openCourse()

    await userEvent.click(screen.getByRole('button', { name: '换球场' }))

    expect(screen.getByRole('heading', { name: '选择球场开始模拟' })).toBeInTheDocument()
    expect(screen.queryByLabelText('选洞')).not.toBeInTheDocument()
  })

  it('surfaces a zh error with 重试 that refetches the same course', async () => {
    fetchCoursePrepMock.mockRejectedValueOnce(new Error('prep boom'))
    renderSandbox()

    await userEvent.click(screen.getByRole('button', { name: '开始模拟 观澜湖·奥拉沙宝场' }))

    const errorPanel = await screen.findByLabelText('沙盘加载失败')
    expect(within(errorPanel).getByText('prep boom')).toBeInTheDocument()

    await userEvent.click(within(errorPanel).getByRole('button', { name: '重试' }))

    expect(await screen.findByLabelText('选洞')).toBeInTheDocument()
    expect(fetchCoursePrepMock).toHaveBeenCalledTimes(2)
    expect(fetchCoursePrepMock).toHaveBeenLastCalledWith(31870, {}, 'admin-secret')
  })

  it('hole chips render and switch the selected hole', async () => {
    renderSandbox()
    await openCourse()

    await userEvent.click(screen.getByRole('button', { name: '第9洞' }))

    expect(screen.getByRole('button', { name: '第9洞' })).toHaveAttribute('aria-current', 'true')
    expect(screen.getByRole('button', { name: '第7洞' })).not.toHaveAttribute('aria-current')
  })

  it('discards a stale prep response that resolves after switching courses', async () => {
    let resolveFirst!: (value: CoursePrepResponse) => void
    const first = new Promise<CoursePrepResponse>((resolve) => {
      resolveFirst = resolve
    })
    fetchCoursePrepMock.mockImplementationOnce(() => first)
    fetchCoursePrepMock.mockImplementationOnce(async () => blackKnightPrepFixture())
    renderSandbox()

    // First course's prep hangs; switch course while it is still in flight.
    await userEvent.click(screen.getByRole('button', { name: '开始模拟 观澜湖·奥拉沙宝场' }))
    await userEvent.click(screen.getByRole('button', { name: '换球场' }))
    await userEvent.click(screen.getByRole('button', { name: '开始模拟 Black Knight B/C' }))
    const chips = within(await screen.findByLabelText('选洞'))
    expect(chips.getByRole('button', { name: '第1洞' })).toBeInTheDocument()

    // The stale 观澜湖 payload resolves late — the seq guard must drop it.
    await act(async () => {
      resolveFirst(prepFixture())
      await first
    })

    expect(screen.getByRole('heading', { name: 'Black Knight B/C' })).toBeInTheDocument()
    expect(within(screen.getByLabelText('选洞')).queryByRole('button', { name: '第7洞' })).not.toBeInTheDocument()
    expect(within(screen.getByLabelText('选洞')).getByRole('button', { name: '第1洞' })).toBeInTheDocument()
  })
})

describe('LiveSandbox ball + situation readout', () => {
  it('starts the ball at the tee with the metric readout and derived 开球', async () => {
    const { view } = renderSandbox()
    await openCourse()

    expect(screen.getByRole('img', { name: '第7洞球道图' })).toBeInTheDocument()
    expect(screen.getByText('距T 0m · 到果岭 200m')).toBeInTheDocument()
    const select = screen.getByLabelText('击球类型')
    expect(select).toHaveValue('tee')
    expect(
      within(select as HTMLElement)
        .getAllByRole('option')
        .map((option) => option.textContent),
    ).toEqual(['开球', '攻果岭', '救球'])
    // The draggable ball is the orange r=12 circle sitting at the tee.
    const ball = view.container.querySelector('circle[r="12"]')
    expect(ball).not.toBeNull()
    expect(ball!.getAttribute('fill')).toBe('#e8963a')
    expect(ball!.getAttribute('cx')).toBe('0')
    expect(ball!.getAttribute('cy')).toBe('0')
  })

  it('dragging the ball updates the readout, the ball position, and the derived shot type', async () => {
    const { view } = renderSandbox()
    await openCourse()
    const svg = view.container.querySelector('svg')
    expect(svg).not.toBeNull()
    mockSvgRect(svg!)

    fireEvent.pointerDown(svg!, { clientX: 100, clientY: 0 })

    expect(screen.getByText('距T 100m · 到果岭 100m')).toBeInTheDocument()
    expect(screen.getByLabelText('击球类型')).toHaveValue('approach')
    expect(view.container.querySelector('circle[r="12"]')!.getAttribute('cx')).toBe('100')

    // pointermove with a held button keeps dragging (1dp metre rounding)…
    fireEvent.pointerMove(svg!, { clientX: 33.5, clientY: 0, buttons: 1 })
    expect(screen.getByText('距T 33.5m · 到果岭 166.5m')).toBeInTheDocument()

    // …but hovering without a pressed button must not move the ball.
    fireEvent.pointerMove(svg!, { clientX: 180, clientY: 0, buttons: 0 })
    expect(screen.getByText('距T 33.5m · 到果岭 166.5m')).toBeInTheDocument()
  })

  it('击球类型 override to 救球 survives drags and resets when the hole changes', async () => {
    const { view } = renderSandbox()
    await openCourse()

    await userEvent.selectOptions(screen.getByLabelText('击球类型'), 'recovery')
    expect(screen.getByLabelText('击球类型')).toHaveValue('recovery')

    const svg = view.container.querySelector('svg')
    mockSvgRect(svg!)
    fireEvent.pointerDown(svg!, { clientX: 100, clientY: 0 })
    expect(screen.getByLabelText('击球类型')).toHaveValue('recovery')

    await userEvent.click(screen.getByRole('button', { name: '第9洞' }))
    expect(screen.getByLabelText('击球类型')).toHaveValue('tee')
  })

  it('switching holes resets the ball to that hole tee', async () => {
    const { view } = renderSandbox()
    await openCourse()
    const svg = view.container.querySelector('svg')
    mockSvgRect(svg!)
    fireEvent.pointerDown(svg!, { clientX: 100, clientY: 0 })
    expect(screen.getByText('距T 100m · 到果岭 100m')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '第9洞' }))

    expect(screen.getByText('距T 0m · 到果岭 200m')).toBeInTheDocument()
    expect(screen.queryByText('距T 100m · 到果岭 100m')).not.toBeInTheDocument()
    expect(view.container.querySelector('circle[r="12"]')!.getAttribute('cx')).toBe('0')
  })
})

describe('LiveSandbox degraded no-map mode', () => {
  it('a hole without a map renders the numeric 到果岭 input instead of the canvas', async () => {
    const { view } = renderSandbox()
    await openCourse()

    await userEvent.click(screen.getByRole('button', { name: '第8洞' }))

    expect(screen.getByText('此洞暂无几何图,直接输入到果岭距离。')).toBeInTheDocument()
    expect(screen.getByLabelText('到果岭(m)')).toBeInTheDocument()
    expect(view.container.querySelector('svg')).toBeNull()
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
    expect(screen.queryByText(/距T /)).not.toBeInTheDocument()
    // The sandbox stays fully usable: shot type is still selectable.
    expect(screen.getByLabelText('击球类型')).toHaveValue('tee')
  })

  it('accepts a numeric 到果岭 distance and derives 攻果岭 from it', async () => {
    renderSandbox()
    await openCourse()
    await userEvent.click(screen.getByRole('button', { name: '第8洞' }))

    const input = screen.getByLabelText('到果岭(m)')
    await userEvent.type(input, '135')

    expect(input).toHaveValue(135)
    expect(screen.getByLabelText('击球类型')).toHaveValue('approach')

    await userEvent.clear(input)
    expect(screen.getByLabelText('击球类型')).toHaveValue('tee')
  })

  it('clears the manual distance when the hole changes', async () => {
    renderSandbox()
    await openCourse()
    await userEvent.click(screen.getByRole('button', { name: '第8洞' }))
    await userEvent.type(screen.getByLabelText('到果岭(m)'), '135')

    await userEvent.click(screen.getByRole('button', { name: '第7洞' }))
    await userEvent.click(screen.getByRole('button', { name: '第8洞' }))

    expect(screen.getByLabelText('到果岭(m)')).toHaveValue(null)
    expect(screen.getByLabelText('击球类型')).toHaveValue('tee')
  })
})

describe('LiveSandbox 沙盘建议 inputs + sourceRef rule', () => {
  it('tee default: 要建议 sends the course-played ref + full-hole distance, omits lie and stock strategy', async () => {
    renderSandbox()
    await openCourse()

    // On the tee the lie does not apply (the backend excuses tee shots from
    // the lie requirement) — the select must read as inactive.
    expect(screen.getByLabelText('球位状态')).toBeDisabled()

    await userEvent.click(screen.getByRole('button', { name: '要建议' }))

    expect(fetchCaddieContextMock).toHaveBeenCalledTimes(1)
    const [params, token] = fetchCaddieContextMock.mock.calls[0]
    expect(token).toBe('admin-secret')
    // 观澜湖 31870 has no latestRoundId → sourceRefs[0] ('900002') + selected hole.
    expect(params.sourceRef).toBe('900002:7')
    expect(params.shotType).toBe('tee')
    expect(params.distanceToPinM).toBe(200)
    expect(params.lie).toBeUndefined()
    expect(params.strategyMode).toBeUndefined()
  })

  it('drag + 长草 + 稳 flow into the context params', async () => {
    const { view } = renderSandbox()
    await openCourse()
    const svg = view.container.querySelector('svg')
    mockSvgRect(svg!)
    fireEvent.pointerDown(svg!, { clientX: 100, clientY: 0 })

    await userEvent.selectOptions(screen.getByLabelText('球位状态'), 'rough')
    await userEvent.click(screen.getByRole('button', { name: '稳' }))
    await userEvent.click(screen.getByRole('button', { name: '要建议' }))

    expect(fetchCaddieContextMock.mock.calls[0][0]).toEqual(
      expect.objectContaining({
        sourceRef: '900002:7',
        shotType: 'approach',
        distanceToPinM: 100,
        lie: 'rough',
        strategyMode: 'protect_score',
      }),
    )
  })

  it('prefers the course option latestRoundId over its sourceRefs head', async () => {
    renderSandbox()
    await openCourse('开始模拟 Black Knight B/C')

    await userEvent.click(screen.getByRole('button', { name: '要建议' }))

    expect(fetchCaddieContextMock.mock.calls[0][0].sourceRef).toBe('900777:1')
  })

  it('a never-played course falls back to the latest ANY round as a BARE round ref', async () => {
    renderSandbox()
    await openSearchCourse()

    await userEvent.click(screen.getByRole('button', { name: '要建议' }))

    // No ':hole' suffix: a cross-course roundId:hole ref would bind the WRONG
    // course's geometry (or fail outright when that round lacks the hole).
    expect(fetchCaddieContextMock.mock.calls[0][0].sourceRef).toBe('900050')
  })

  it('disables 要建议 with a zh hint when no played ref is derivable', async () => {
    renderSandbox({ recentRounds: [] })
    await openSearchCourse()

    expect(screen.getByRole('button', { name: '要建议' })).toBeDisabled()
    expect(screen.getByText('暂无历史球局,无法生成建议')).toBeInTheDocument()
    expect(fetchCaddieContextMock).not.toHaveBeenCalled()
  })

  it('manual wind merges a ready manual weatherSnapshot into the decision context without any weather fetch', async () => {
    renderSandbox()
    await openCourse()

    await userEvent.type(screen.getByLabelText('风速(m/s)'), '4.5')
    await userEvent.type(screen.getByLabelText('风向(°)'), '270')
    await userEvent.click(screen.getByRole('button', { name: '要建议' }))
    await screen.findByLabelText('沙盘建议')

    expect(fetchCaddieDecisionMock).toHaveBeenCalledTimes(1)
    const [request, token] = fetchCaddieDecisionMock.mock.calls[0]
    expect(token).toBe('admin-secret')
    expect(request.shotType).toBe('tee')
    expect(request.includeExplanation).toBe(true)
    // The loaded context spreads through with shotType re-asserted (CaddiePage
    // buildDecisionRequest idiom) and the snapshot layered on top.
    expect(request.context).toEqual(
      expect.objectContaining({ roundId: '900002', shotType: 'tee', clubProfiles: caddieContextFixture().context.clubProfiles }),
    )
    expect(request.context.weatherSnapshot).toEqual(
      expect.objectContaining({
        schema: 'ai-caddie-weather-snapshot-v1',
        state: 'ready',
        source: 'manual',
        windSpeedMps: 4.5,
        windDirectionDeg: 270,
        confidence: 'medium',
      }),
    )
    // A snapshot fetched without coordinates would come back state:'missing'
    // and the engine would ignore the wind — the endpoint must NOT be used.
    expect(fetchWeatherSnapshotMock).not.toHaveBeenCalled()
  })

  it('without wind speed the decision context carries no weatherSnapshot', async () => {
    renderSandbox()
    await openCourse()

    await userEvent.type(screen.getByLabelText('风向(°)'), '90')
    await userEvent.click(screen.getByRole('button', { name: '要建议' }))
    await screen.findByLabelText('沙盘建议')

    expect('weatherSnapshot' in fetchCaddieDecisionMock.mock.calls[0][0].context).toBe(false)
  })

  it('degraded no-map flow works end-to-end with the manual distance', async () => {
    renderSandbox()
    await openCourse()
    await userEvent.click(screen.getByRole('button', { name: '第8洞' }))
    await userEvent.type(screen.getByLabelText('到果岭(m)'), '135')

    await userEvent.click(screen.getByRole('button', { name: '要建议' }))

    expect(fetchCaddieContextMock.mock.calls[0][0]).toEqual(
      expect.objectContaining({ sourceRef: '900002:8', shotType: 'approach', distanceToPinM: 135, lie: 'fairway' }),
    )
    const card = await screen.findByLabelText('沙盘建议')
    expect(within(card).getByText('8I', { selector: '.live-advice-club' })).toBeInTheDocument()
  })
})

describe('LiveSandbox 沙盘建议 card', () => {
  async function openAdvice() {
    renderSandbox()
    await openCourse()
    await userEvent.click(screen.getByRole('button', { name: '要建议' }))
    return await screen.findByLabelText('沙盘建议')
  }

  it('renders 主建议 club/label/carry/risk/confidence with 为什么, acceptableMiss and missing chips', async () => {
    const card = await openAdvice()

    expect(within(card).getByText('8I')).toHaveClass('live-advice-club')
    expect(within(card).getByText('Stock')).toBeInTheDocument()
    expect(within(card).getByText('落点 132m')).toBeInTheDocument()
    expect(within(card).getByLabelText('风险 3.4')).toHaveClass('live-risk-dot', 'medium')
    expect(within(card).getByText('信心中')).toHaveClass('confidence-pill', 'medium')
    expect(within(card).getByText('为什么')).toBeInTheDocument()
    expect(within(card).getByText(/8I 中位 132m/)).toBeInTheDocument()
    expect(within(card).getByText(/可接受偏向/)).toBeInTheDocument()
    expect(within(card).getByText(/long — short brings the water into play/)).toBeInTheDocument()
    const missing = within(card).getByLabelText('数据缺口')
    expect(within(missing).getByText('weather')).toHaveAttribute('title', 'weather snapshot is missing or incomplete')
  })

  it('hides 为什么 when the explanation narrative is missing', async () => {
    fetchCaddieDecisionMock.mockImplementation(async () => caddieDecisionFixture({ explanation: null }))

    const card = await openAdvice()

    expect(within(card).queryByText('为什么')).not.toBeInTheDocument()
  })

  it('其它选项 chips exclude the selected option and reveal that option numbers on click', async () => {
    const card = await openAdvice()

    const others = within(card).getByLabelText('其它选项')
    expect(within(others).queryByRole('button', { name: /Stock/ })).not.toBeInTheDocument()
    expect(within(others).getByRole('button', { name: 'Safe · 9I' })).toBeInTheDocument()

    await userEvent.click(within(others).getByRole('button', { name: 'Attack · 7I' }))

    expect(within(card).getByText('落点 146m · 风险 5.2 · 信心低')).toBeInTheDocument()
  })

  it('稳→博 re-requests the context+decision pair with strategyMode=attack', async () => {
    await openAdvice()

    await userEvent.click(screen.getByRole('button', { name: '博' }))

    await waitFor(() => expect(fetchCaddieDecisionMock).toHaveBeenCalledTimes(2))
    expect(fetchCaddieContextMock).toHaveBeenCalledTimes(2)
    expect(fetchCaddieContextMock.mock.calls[1][0].strategyMode).toBe('attack')
  })

  it('shows 建议生成中… and disables 要建议 while the advice is loading', async () => {
    fetchCaddieContextMock.mockImplementationOnce(() => new Promise<CaddieContextResponse>(() => {}))
    renderSandbox()
    await openCourse()

    await userEvent.click(screen.getByRole('button', { name: '要建议' }))

    expect(await screen.findByText('建议生成中…')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '要建议' })).toBeDisabled()
  })

  it('drops a stale decision that resolves after a 稳/博 re-request', async () => {
    let resolveFirst!: (value: CaddieDecisionResponse) => void
    const first = new Promise<CaddieDecisionResponse>((resolve) => {
      resolveFirst = resolve
    })
    fetchCaddieDecisionMock.mockImplementationOnce(() => first)
    fetchCaddieDecisionMock.mockImplementationOnce(async () => attackDecisionFixture())
    renderSandbox()
    await openCourse()

    // First request hangs at the decision step; the 博 switch supersedes it.
    await userEvent.click(screen.getByRole('button', { name: '要建议' }))
    await userEvent.click(screen.getByRole('button', { name: '博' }))
    const card = await screen.findByLabelText('沙盘建议')
    expect(within(card).getByText('7I', { selector: '.live-advice-club' })).toBeInTheDocument()

    // The stale stock decision resolves late — the seq guard must drop it.
    await act(async () => {
      resolveFirst(caddieDecisionFixture())
      await first
    })

    expect(within(screen.getByLabelText('沙盘建议')).getByText('7I', { selector: '.live-advice-club' })).toBeInTheDocument()
    expect(within(screen.getByLabelText('沙盘建议')).queryByText('8I', { selector: '.live-advice-club' })).not.toBeInTheDocument()
  })

  it('surfaces a zh error with 重试 that re-runs the advice request', async () => {
    fetchCaddieContextMock.mockRejectedValueOnce(new Error('context boom'))
    renderSandbox()
    await openCourse()

    await userEvent.click(screen.getByRole('button', { name: '要建议' }))

    const errorPanel = await screen.findByLabelText('建议生成失败')
    expect(within(errorPanel).getByText('context boom')).toBeInTheDocument()

    await userEvent.click(within(errorPanel).getByRole('button', { name: '重试' }))

    expect(await screen.findByLabelText('沙盘建议')).toBeInTheDocument()
    expect(fetchCaddieContextMock).toHaveBeenCalledTimes(2)
  })

  it('switching holes clears the advice card', async () => {
    const card = await openAdvice()
    expect(card).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '第9洞' }))

    expect(screen.queryByLabelText('沙盘建议')).not.toBeInTheDocument()
  })
})
