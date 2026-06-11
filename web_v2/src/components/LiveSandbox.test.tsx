import { act, fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ComponentProps } from 'react'
import type { CoursePrepHole, CoursePrepOverlay, CoursePrepResponse, CourseSearchResponse, MobileCourseOptionsResponse } from '../types'
import { fetchCoursePrep } from '../api'
import { LiveSandbox } from './LiveSandbox'

vi.mock('../api', () => ({
  fetchCoursePrep: vi.fn(),
}))

const fetchCoursePrepMock = vi.mocked(fetchCoursePrep)

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
      { globalId: 31795, courseKey: 'black_knight', name: 'Black Knight B/C', roundCount: 2, holes: 18, geometryCoverage: 'partial', sourceRefs: ['900001'] },
      { globalId: 31870, name: '观澜湖·奥拉沙宝场', roundCount: 9, holes: 18, geometryCoverage: 'ready', sourceRefs: ['900002'] },
    ],
    emptyState: null,
    generatedAt: '2026-06-05T08:00:00Z',
  }
}

beforeEach(() => {
  fetchCoursePrepMock.mockReset()
  fetchCoursePrepMock.mockImplementation(async (globalId: number) =>
    globalId === 31795 ? blackKnightPrepFixture() : prepFixture(),
  )
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
    ...overrides,
  }
  const view = render(<LiveSandbox {...props} />)
  return { onSearchCourses, view }
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
