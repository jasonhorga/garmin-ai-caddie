import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ComponentProps } from 'react'
import type { CourseSearchResponse, HistoryRoundDetailResponse, MobileCourseOptionsResponse, RoundCard as RoundCardType } from '../types'
import { fetchHistoryRoundDetail } from '../api'
import { LivePage } from './LivePage'

vi.mock('../api', () => ({
  fetchHistoryRoundDetail: vi.fn(),
}))

const fetchHistoryRoundDetailMock = vi.mocked(fetchHistoryRoundDetail)

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

beforeEach(() => {
  fetchHistoryRoundDetailMock.mockReset()
  fetchHistoryRoundDetailMock.mockImplementation(async (roundRef: string) => roundDetailFixture(roundRef))
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
  const view = render(<LivePage {...props} />)
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
    expect(screen.queryByRole('heading', { name: 'Caddie' })).not.toBeInTheDocument()
  })

  it('hands the search query to onSearchCourses and lists matches on the sandbox entry', async () => {
    const { onSearchCourses } = renderLive()

    await userEvent.type(screen.getByLabelText('搜索球场'), '观澜湖')
    await userEvent.click(screen.getByRole('button', { name: '搜索' }))

    expect(onSearchCourses).toHaveBeenCalledWith('观澜湖')
    expect(await screen.findByText('观澜湖·世界杯场')).toBeInTheDocument()
  })

  it('最近回放 lists recent rounds as 日期/球场/杆数/±标准杆 rows', async () => {
    renderLive({ recentRounds: recentRoundsFixture() })

    await userEvent.click(liveTabs().getByRole('button', { name: '最近回放' }))

    expect(liveTabs().getByRole('button', { name: '最近回放' })).toHaveAttribute('aria-current', 'page')
    expect(liveTabs().getByRole('button', { name: '决策沙盘' })).not.toHaveAttribute('aria-current')
    expect(screen.queryByRole('heading', { name: '选择球场开始模拟' })).not.toBeInTheDocument()

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
    expect(screen.getByRole('heading', { name: 'Caddie' })).toBeInTheDocument()
    // The props bundle is spread through untouched: selectedSourceRef reaches
    // CaddiePage's Source ref input exactly as it did when App rendered it.
    expect(screen.getByLabelText('Source ref')).toHaveValue('900042:3')
    expect(screen.queryByRole('heading', { name: '选择球场开始模拟' })).not.toBeInTheDocument()

    await userEvent.click(liveTabs().getByRole('button', { name: '决策沙盘' }))

    expect(screen.getByRole('heading', { name: '选择球场开始模拟' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Caddie' })).not.toBeInTheDocument()
  })
})

describe('LivePage 最近回放 detail', () => {
  it('lazily auto-loads the first round only when the tab opens', async () => {
    renderLive({ recentRounds: recentRoundsFixture() })

    // Nothing is fetched while 最近回放 stays closed (lazy).
    expect(fetchHistoryRoundDetailMock).not.toHaveBeenCalled()

    await userEvent.click(liveTabs().getByRole('button', { name: '最近回放' }))

    expect(await screen.findByText('详情 900001')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Round Review' })).toBeInTheDocument()
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
    expect(screen.queryByRole('heading', { name: 'Round Review' })).not.toBeInTheDocument()
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

    await userEvent.click(screen.getByRole('button', { name: 'Open hole 1 detail 900001:1' }))
    expect(onSelectRef).toHaveBeenCalledWith('900001:1')

    await userEvent.click(screen.getByRole('button', { name: 'Load AI Review' }))
    expect(onLoadRoundReport).toHaveBeenCalledWith('900001')
  })
})
