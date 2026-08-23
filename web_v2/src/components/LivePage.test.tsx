import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ComponentProps } from 'react'
import type {
  CoursePrepResponse,
  CourseSearchResponse,
  HistoryRoundDetailResponse,
  MobileCourseOptionsResponse,
  RoundCard as RoundCardType,
} from '../types'
import { fetchCaddieContext, fetchCaddieDecision, fetchCoursePrep, fetchHistoryRoundDetail } from '../api'
import { LivePage } from './LivePage'
import { DiagnosticsProvider } from '../diagnosticsContext'

vi.mock('../api', () => ({
  fetchCoursePrep: vi.fn(),
  fetchHistoryRoundDetail: vi.fn(),
  fetchCaddieContext: vi.fn(),
  fetchCaddieDecision: vi.fn(),
  topoImageUrl: (gid: number, hole: number) => `/api/v2/courses/${gid}/holes/${hole}/topo.png`,
}))

const fetchCoursePrepMock = vi.mocked(fetchCoursePrep)
const fetchHistoryRoundDetailMock = vi.mocked(fetchHistoryRoundDetail)
const fetchCaddieContextMock = vi.mocked(fetchCaddieContext)
const fetchCaddieDecisionMock = vi.mocked(fetchCaddieDecision)

function recentRoundsFixture(): RoundCardType[] {
  return [
    {
      id: '900001',
      date: '2026-05-20T08:00:00',
      courseName: 'Black Knight B',
      courseKey: 'black_knight',
      holesCompleted: 18,
      score: 82,
      par: 72,
      toPar: 10,
      scoreStrip: [],
      badges: [],
      primaryIssue: null,
    },
    {
      id: '900002',
      date: '2026-05-12T07:30:00',
      courseName: '观澜湖·奥拉沙宝场',
      courseKey: 'mission_hills',
      holesCompleted: 18,
      score: 71,
      par: 72,
      toPar: -1,
      scoreStrip: [],
      badges: [],
      primaryIssue: null,
    },
  ]
}

function roundDetailFixture(roundRef: string): HistoryRoundDetailResponse {
  return {
    schema: 'ai-caddie-history-round-detail-v1',
    roundRef,
    requestedRef: roundRef,
    found: true,
    title: `详情 ${roundRef}`,
    round: { id: roundRef, score: 82, toPar: 10, holesScored: 18, shotCount: 2, confidence: 'high' },
    scorecard: [
      {
        hole: 1,
        par: 4,
        score: 4,
        toPar: 0,
        className: 'par',
        putts: 2,
        gir: true,
        fairway: 'hit',
        holeRef: `${roundRef}:1`,
        shotRefs: [`${roundRef}:1:0`],
        sourceRefs: [`${roundRef}:1`],
        status: 'complete',
      },
    ],
    phaseSummary: [],
    holeDetails: [],
    relatedRefs: { roundRefs: [roundRef], holeRefs: [`${roundRef}:1`], shotRefs: [], sourceRefs: [] },
    sourceFields: { id: roundRef },
    missingData: [],
  }
}

// Minimal geometry-less sandbox hole (chips render from the holes list).
function sandboxHolePayload(hole: number): CoursePrepResponse['holes'][number] {
  return {
    hole,
    par: 4,
    par_source: 'estimate',
    blue_yards: 0,
    route_len_m: 0,
    route: [],
    geometryCoverage: 'missing',
    sourceRefs: [],
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

beforeEach(() => {
  fetchCoursePrepMock.mockReset()
  fetchHistoryRoundDetailMock.mockReset()
  fetchHistoryRoundDetailMock.mockImplementation(async (roundRef: string) => roundDetailFixture(roundRef))
  fetchCaddieContextMock.mockReset()
  fetchCaddieDecisionMock.mockReset()
})

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

function renderLive(overrides: Partial<ComponentProps<typeof LivePage>> = {}) {
  const onSearchCourses = vi.fn(async (): Promise<CourseSearchResponse> => ({
    schema: 'ai-caddie-course-search-v1',
    query: '观澜湖',
    matches: [{ globalId: 99999, name: '观澜湖·世界杯场', holes: 18, city: '深圳', province: '广东', ratio: 0.92 }],
  }))
  const onRequestDecision = vi.fn()
  const props: ComponentProps<typeof LivePage> = {
    courseOptions: courseOptionsFixture(),
    adminToken: 'admin-secret',
    onSearchCourses,
    recentRounds: [],
    caddieProps: {
      decisionState: { status: 'idle' },
      onRequestDecision,
      selectedSourceRef: '900042:3',
    },
    ...overrides,
  }
  // Owner power-user surface (raw refs, clickable scorecard cells) is diagnostics-only now.
  const view = render(
    <DiagnosticsProvider value={true}>
      <LivePage {...props} />
    </DiagnosticsProvider>,
  )
  return { onSearchCourses, onRequestDecision, view }
}

function liveTabs() {
  return within(screen.getByRole('navigation', { name: '实战页签' }))
}

describe('LivePage tabs', () => {
  it('defaults to 决策沙盘: course-pick entry heading, finder wiring, and no CaddiePage', () => {
    renderLive()

    expect(liveTabs().getByRole('button', { name: '决策沙盘' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('heading', { name: '选择球场开始模拟' })).toBeInTheDocument()
    expect(screen.getByLabelText('搜索球场')).toBeInTheDocument()
    // courseOptions flow through to the finder's 常打球场 cards.
    expect(screen.getByText('Black Knight B/C')).toBeInTheDocument()
    // The legacy dashboard must stay OFF the default tab.
    expect(screen.queryByRole('heading', { name: '智能球童' })).not.toBeInTheDocument()
  })

  it('hands the search query to onSearchCourses and lists matches on the sandbox entry', async () => {
    const { onSearchCourses } = renderLive()

    await userEvent.type(screen.getByLabelText('搜索球场'), '观澜湖')
    await userEvent.click(screen.getByRole('button', { name: '搜索' }))

    expect(onSearchCourses).toHaveBeenCalledWith('观澜湖')
    expect(await screen.findByText('观澜湖·世界杯场')).toBeInTheDocument()
  })

  it('决策沙盘 delegates to LiveSandbox: 开始模拟 pick fetches prep and shows hole chips', async () => {
    fetchCoursePrepMock.mockResolvedValue({
      schema: 'ai-caddie-course-prep-v1',
      globalId: 31870,
      holeCount: 1,
      clubs: [],
      holes: [
        {
          hole: 1,
          par: 4,
          par_source: 'estimate',
          blue_yards: 0,
          route_len_m: 0,
          route: [],
          geometryCoverage: 'missing',
          sourceRefs: [],
          missingData: [],
          candidateRoutes: [],
          carryTargets: [],
          steps: [],
          cautions: [],
          landing_m: null,
          tee_club: null,
          hazards: { water_carry: [], bunkers: [] },
        },
      ],
    } satisfies CoursePrepResponse)
    renderLive()

    await userEvent.click(screen.getByRole('button', { name: '开始模拟 观澜湖·奥拉沙宝场' }))

    expect(fetchCoursePrepMock).toHaveBeenCalledWith(31870, { render: false }, 'admin-secret')
    const chips = within(await screen.findByLabelText('选洞'))
    expect(chips.getByRole('button', { name: '第1洞' })).toHaveAttribute('aria-current', 'true')
    expect(screen.getByRole('heading', { name: '观澜湖·奥拉沙宝场' })).toBeInTheDocument()
  })

  it('threads recentRounds into the sandbox: 要建议 on a never-played course falls back to the latest round ref', async () => {
    fetchCoursePrepMock.mockResolvedValue({
      schema: 'ai-caddie-course-prep-v1',
      globalId: 99999,
      holeCount: 1,
      clubs: [],
      holes: [
        {
          hole: 1,
          par: 4,
          par_source: 'estimate',
          blue_yards: 0,
          route_len_m: 0,
          route: [],
          geometryCoverage: 'missing',
          sourceRefs: [],
          missingData: [],
          candidateRoutes: [],
          carryTargets: [],
          steps: [],
          cautions: [],
          landing_m: null,
          tee_club: null,
          hazards: { water_carry: [], bunkers: [] },
        },
      ],
    } satisfies CoursePrepResponse)
    fetchCaddieContextMock.mockResolvedValue({
      schema: 'ai-caddie-context-v1',
      sourceRef: '900001',
      shotType: 'tee',
      context: { source: 'history_drilldown', sourceRef: '900001', roundId: '900001' },
      evidence: [],
      missingData: [],
    })
    fetchCaddieDecisionMock.mockResolvedValue({
      schema: 'ai-caddie-decision-v2',
      decisionId: '900001:tee',
      sourceRef: '900001',
      evidenceRefs: [],
      shotType: 'tee',
      phase: 'Tee',
      context: {},
      options: [{ id: 'stock', label: 'Stock', recommendedClub: '1W' }],
      selected: { id: 'stock' },
      selectedOptionId: 'stock',
      selectedOption: { id: 'stock' },
      avoidZones: [],
      forbiddenZones: [],
      acceptableMiss: {},
      evidence: [],
      confidence: { level: 'medium' },
      missingData: [],
      auditCriteria: [],
    })
    renderLive({ recentRounds: recentRoundsFixture() })

    // 观澜湖·世界杯场 (99999) is NOT in courseOptions → the sandbox must fall
    // back to the LivePage-provided recentRounds[0] bare round ref.
    await userEvent.type(screen.getByLabelText('搜索球场'), '观澜湖')
    await userEvent.click(screen.getByRole('button', { name: '搜索' }))
    await userEvent.click(await screen.findByRole('button', { name: /观澜湖·世界杯场/ }))
    await screen.findByLabelText('选洞')
    await userEvent.click(screen.getByRole('button', { name: '要建议' }))

    expect(fetchCaddieContextMock).toHaveBeenCalledWith(
      expect.objectContaining({ sourceRef: '900001', shotType: 'tee' }),
      'admin-secret',
    )
    expect(await screen.findByLabelText('沙盘建议')).toBeInTheDocument()
  })

  it('最近回放 lists recent rounds as 日期/球场/杆数/±标准杆 rows', async () => {
    renderLive({ recentRounds: recentRoundsFixture() })

    await userEvent.click(liveTabs().getByRole('button', { name: '最近回放' }))

    expect(liveTabs().getByRole('button', { name: '最近回放' })).toHaveAttribute('aria-current', 'page')
    expect(liveTabs().getByRole('button', { name: '决策沙盘' })).not.toHaveAttribute('aria-current')
    // The sandbox stays MOUNTED (state retention) but hidden off this tab.
    expect(screen.getByRole('heading', { name: '选择球场开始模拟', hidden: true })).not.toBeVisible()

    const list = within(screen.getByLabelText('最近回放球局'))
    expect(list.getByRole('button', { name: '回放 Black Knight B 05-20' })).toBeInTheDocument()
    expect(list.getByText('05-20')).toBeInTheDocument()
    expect(list.getByText('82')).toBeInTheDocument()
    // The toPar chips reuse the trends chip classes (under/over coloring).
    expect(list.getByText('+10')).toHaveClass('trends-pchip', 'over')
    expect(list.getByRole('button', { name: '回放 观澜湖·奥拉沙宝场 05-12' })).toBeInTheDocument()
    expect(list.getByText('-1')).toHaveClass('trends-pchip', 'under')
  })

  it('完整工具 renders the verbatim CaddiePage; 决策沙盘 returns to the entry', async () => {
    renderLive()

    await userEvent.click(liveTabs().getByRole('button', { name: '完整工具' }))

    expect(liveTabs().getByRole('button', { name: '完整工具' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('heading', { name: '智能球童' })).toBeInTheDocument()
    // The props bundle is spread through untouched: selectedSourceRef reaches
    // CaddiePage's Source ref input exactly as it did when App rendered it.
    expect(screen.getByLabelText('Source ref')).toHaveValue('900042:3')
    // The sandbox stays MOUNTED (state retention) but hidden off this tab.
    expect(screen.getByRole('heading', { name: '选择球场开始模拟', hidden: true })).not.toBeVisible()

    await userEvent.click(liveTabs().getByRole('button', { name: '决策沙盘' }))

    expect(screen.getByRole('heading', { name: '选择球场开始模拟' })).toBeVisible()
    expect(screen.queryByRole('heading', { name: '智能球童' })).not.toBeInTheDocument()
  })

  it('keeps the 决策沙盘 course/hole selection across a 最近回放 peek', async () => {
    fetchCoursePrepMock.mockResolvedValue({
      schema: 'ai-caddie-course-prep-v1',
      globalId: 31870,
      holeCount: 2,
      clubs: [],
      holes: [sandboxHolePayload(7), sandboxHolePayload(9)],
    } satisfies CoursePrepResponse)
    renderLive()
    await userEvent.click(screen.getByRole('button', { name: '开始模拟 观澜湖·奥拉沙宝场' }))
    await screen.findByLabelText('选洞')
    await userEvent.click(screen.getByRole('button', { name: '第9洞' }))

    await userEvent.click(liveTabs().getByRole('button', { name: '最近回放' }))
    expect(screen.getByText('还没有球局数据')).toBeInTheDocument()
    // Mounted-but-hidden: the simulation must NOT be torn down by a tab peek.
    expect(screen.getByRole('heading', { name: '观澜湖·奥拉沙宝场', hidden: true })).not.toBeVisible()

    await userEvent.click(liveTabs().getByRole('button', { name: '决策沙盘' }))

    expect(screen.getByRole('heading', { name: '观澜湖·奥拉沙宝场' })).toBeVisible()
    expect(screen.getByRole('button', { name: '第9洞' })).toHaveAttribute('aria-current', 'true')
    // No refetch: the mounted sandbox kept its loaded prep payload.
    expect(fetchCoursePrepMock).toHaveBeenCalledTimes(1)
  })
})

describe('LivePage 最近回放 detail', () => {
  it('lazily auto-loads the first round only when the tab opens', async () => {
    renderLive({ recentRounds: recentRoundsFixture() })

    // Nothing is fetched while 最近回放 stays closed (lazy).
    expect(fetchHistoryRoundDetailMock).not.toHaveBeenCalled()

    await userEvent.click(liveTabs().getByRole('button', { name: '最近回放' }))

    expect(await screen.findByText('详情 900001')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '球局回顾' })).toBeInTheDocument()
    expect(fetchHistoryRoundDetailMock).toHaveBeenCalledWith('900001', 'admin-secret')
    expect(screen.getByRole('button', { name: '回放 Black Knight B 05-20' })).toHaveAttribute('aria-current', 'true')
  })

  it('clicking a row fetches and renders that round detail', async () => {
    renderLive({ recentRounds: recentRoundsFixture() })
    await userEvent.click(liveTabs().getByRole('button', { name: '最近回放' }))
    expect(await screen.findByText('详情 900001')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '回放 观澜湖·奥拉沙宝场 05-12' }))

    expect(await screen.findByText('详情 900002')).toBeInTheDocument()
    expect(fetchHistoryRoundDetailMock).toHaveBeenLastCalledWith('900002', 'admin-secret')
    expect(screen.queryByText('详情 900001')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '回放 观澜湖·奥拉沙宝场 05-12' })).toHaveAttribute('aria-current', 'true')
    expect(screen.getByRole('button', { name: '回放 Black Knight B 05-20' })).not.toHaveAttribute('aria-current')
  })

  it('discards a stale detail response that resolves after switching rounds', async () => {
    let resolveFirst!: (value: HistoryRoundDetailResponse) => void
    const first = new Promise<HistoryRoundDetailResponse>((resolve) => {
      resolveFirst = resolve
    })
    fetchHistoryRoundDetailMock.mockImplementationOnce(() => first)
    fetchHistoryRoundDetailMock.mockImplementationOnce(async (roundRef: string) => roundDetailFixture(roundRef))
    renderLive({ recentRounds: recentRoundsFixture() })
    await userEvent.click(liveTabs().getByRole('button', { name: '最近回放' }))

    // Switch rounds while the first detail is still in flight.
    await userEvent.click(screen.getByRole('button', { name: '回放 观澜湖·奥拉沙宝场 05-12' }))
    expect(await screen.findByText('详情 900002')).toBeInTheDocument()

    // The stale 900001 payload resolves late — the seq guard must drop it.
    await act(async () => {
      resolveFirst(roundDetailFixture('900001'))
      await first
    })

    expect(screen.getByText('详情 900002')).toBeInTheDocument()
    expect(screen.queryByText('详情 900001')).not.toBeInTheDocument()
  })

  it('surfaces a zh error with 重试 that refetches the same round', async () => {
    fetchHistoryRoundDetailMock.mockRejectedValueOnce(new Error('detail boom'))
    renderLive({ recentRounds: recentRoundsFixture() })

    await userEvent.click(liveTabs().getByRole('button', { name: '最近回放' }))

    const errorPanel = await screen.findByLabelText('回放加载失败')
    expect(within(errorPanel).getByText('detail boom')).toBeInTheDocument()

    await userEvent.click(within(errorPanel).getByRole('button', { name: '重试' }))

    expect(await screen.findByText('详情 900001')).toBeInTheDocument()
    expect(fetchHistoryRoundDetailMock).toHaveBeenCalledTimes(2)
    expect(fetchHistoryRoundDetailMock).toHaveBeenLastCalledWith('900001', 'admin-secret')
  })

  it('shows the zh empty state and fetches nothing without recent rounds', async () => {
    renderLive()

    await userEvent.click(liveTabs().getByRole('button', { name: '最近回放' }))

    expect(screen.getByText('还没有球局数据')).toBeInTheDocument()
    expect(fetchHistoryRoundDetailMock).not.toHaveBeenCalled()
    expect(screen.queryByRole('heading', { name: '球局回顾' })).not.toBeInTheDocument()
  })

  it('threads drilldown and report handlers into the round detail panel', async () => {
    const onSelectRef = vi.fn()
    const onLoadRoundReport = vi.fn()
    renderLive({
      recentRounds: recentRoundsFixture(),
      onSelectRef,
      onLoadRoundReport,
      reportState: { status: 'idle' },
    })
    await userEvent.click(liveTabs().getByRole('button', { name: '最近回放' }))
    expect(await screen.findByText('详情 900001')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '第1洞详情' }))
    expect(onSelectRef).toHaveBeenCalledWith('900001:1')

    await userEvent.click(screen.getByRole('button', { name: '载入 AI 回顾' }))
    expect(onLoadRoundReport).toHaveBeenCalledWith('900001')
  })
})
