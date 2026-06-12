import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ReportsPage } from './ReportsPage'
import type { HistoryStatsResponse, ReviewReportIndexResponse, ReviewReportResponse } from '../types'

const stats: HistoryStatsResponse = {
  schema: 'ai-caddie-history-stats-v1',
  dataMode: 'fixture',
  summary: { totalRounds: 3 },
  time: {
    byQuarter: [{ key: '2026-Q2', roundCount: 2, average18: 86 }],
    byYear: [{ key: '2026', roundCount: 3, average18: 86 }],
  },
  scoring: {},
  courseDistribution: [{ courseKey: 'black_knight', courseName: 'Black Knight B/C', roundCount: 2 }],
  records: {},
  courses: [{ courseKey: 'black_knight', courseName: 'Black Knight B/C', roundCount: 2 }],
  holes: [{ courseKey: 'black_knight', hole: 7, sampleCount: 2, averageToPar: 1.5 }],
  clubs: [{ club: '1D', sampleCount: 2, median: 240 }],
  issues: [],
  dataQuality: [{ label: 'reports', state: 'partial', ready: 1, total: 3, refs: ['900002', '900003'] }],
  drillDown: { roundRefs: ['900001', '900002'] },
}

const report: ReviewReportResponse = {
  schema: 'ai-caddie-review-report-v1',
  kind: 'trend',
  subjectId: 'recent_10',
  sourceRefs: ['900001', '900002'],
  provider: 'StaticProvider',
  model: 'static',
  factsUsed: [
    {
      label: 'summary_trend',
      source: 'summary',
      value: { totalRounds: 3, roundRefs: ['900001'] },
      sourceRefs: ['900001', '900002'],
      coverage: { ready: 2, total: 3, pct: 66.7 },
      confidence: 'medium',
    },
    {
      label: 'round_scorecard',
      source: 'history.rounds',
      value: {
        roundRef: '900001',
        course: 'Black Knight B/C',
        score: 77,
        toPar: 5,
        rating: 72.0,
        slope: 120.0,
        differential: 4.7,
      },
    },
    {
      label: 'round_hole_outcomes',
      source: 'history.rounds.holes',
      value: [
        { holeRef: '900001:1', hole: 1, strokes: 4, par: 4, toPar: 0 },
        { holeRef: '900001:2', hole: 2, strokes: 3, par: 4, toPar: -1 },
      ],
    },
    {
      label: 'round_shots',
      source: 'history.shots',
      value: [{ shotRef: '900001:1:0', hole: 1, club: '1D', distance: 238, surface: 'fairway' }],
    },
  ],
  missingData: [
    {
      label: 'weather',
      state: 'partial',
      refs: ['900002'],
      coverage: { ready: 1, total: 3, pct: 33.3 },
      confidence: 'low',
    },
  ],
  inferencesMade: [
    {
      claim: 'Recent review is based on 3 rounds.',
      factLabels: ['summary_trend'],
      sourceRefs: ['900001'],
      confidence: 'medium',
      missingDataRefs: ['900002'],
      missingDataLabels: ['weather'],
    },
  ],
  unsupportedClaims: [
    {
      category: 'weather',
      claim: 'Wind was strong all day.',
      reason: 'Narrative references weather without a supporting structured fact.',
      missingDataRefs: ['900002'],
      missingDataLabels: ['weather'],
    },
  ],
  factBinding: { state: 'needs_review', unsupportedClaimCount: 1 },
  narrative: 'Recent scoring improved, but weather coverage is partial.',
  confidence: 'medium',
}

const reportIndex: ReviewReportIndexResponse = {
  schema: 'ai-caddie-review-report-index-v1',
  total: 5,
  reports: [
    {
      id: 'trend-report',
      storedAt: '2026-05-26T00:00:00Z',
      kind: 'trend',
      subjectId: 'recent_10',
      confidence: 'medium',
      provider: 'StaticProvider',
      model: 'static',
      sourceRefs: ['900001', '900002'],
    },
    {
      id: 'round-report',
      storedAt: '2026-05-25T00:00:00Z',
      kind: 'round',
      subjectId: '900001',
      confidence: 'high',
      provider: 'StaticProvider',
      model: 'static',
      sourceRefs: ['900001'],
    },
    {
      id: 'course-report',
      storedAt: '2026-05-24T00:00:00Z',
      kind: 'course',
      subjectId: 'black_knight',
      confidence: 'medium',
      provider: 'StaticProvider',
      model: 'static',
      sourceRefs: ['900001', '900002'],
    },
    {
      id: 'hole-report',
      storedAt: '2026-05-23T00:00:00Z',
      kind: 'hole',
      subjectId: 'black_knight:7',
      confidence: 'medium',
      provider: 'StaticProvider',
      model: 'static',
      sourceRefs: ['900001:7', '900002:7'],
    },
    {
      id: 'club-report',
      storedAt: '2026-05-22T00:00:00Z',
      kind: 'club',
      subjectId: '1D',
      confidence: 'low',
      provider: 'StaticProvider',
      model: 'static',
      sourceRefs: ['900001:1:0'],
    },
  ],
}

describe('ReportsPage', () => {
  it('renders trend and round report controls and displayed evidence', async () => {
    const onLoadTrend = vi.fn()
    const onGenerateTrend = vi.fn()
    const onLoadRound = vi.fn()
    const onGenerateRound = vi.fn()
    const onLoadCourse = vi.fn()
    const onGenerateCourse = vi.fn()
    const onLoadHole = vi.fn()
    const onGenerateHole = vi.fn()
    const onLoadClub = vi.fn()
    const onGenerateClub = vi.fn()
    const onSelectRef = vi.fn()

    render(
      <ReportsPage
        stats={stats}
        reportState={{ status: 'ready', data: report }}
        reportIndexState={{ status: 'ready', data: reportIndex }}
        onLoadTrend={onLoadTrend}
        onGenerateTrend={onGenerateTrend}
        onLoadRound={onLoadRound}
        onGenerateRound={onGenerateRound}
        onLoadCourse={onLoadCourse}
        onGenerateCourse={onGenerateCourse}
        onLoadHole={onLoadHole}
        onGenerateHole={onGenerateHole}
        onLoadClub={onLoadClub}
        onGenerateClub={onGenerateClub}
        onSelectRef={onSelectRef}
      />,
    )

    expect(screen.getByRole('heading', { name: '报告' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '报告索引' })).toBeInTheDocument()
    const inventory = screen.getByLabelText('报告索引')
    expect(within(inventory).getByText('5 条')).toBeInTheDocument()
    expect(within(inventory).getByText('趋势')).toBeInTheDocument()
    expect(within(inventory).getByText('球局')).toBeInTheDocument()
    expect(within(inventory).getByText('球场')).toBeInTheDocument()
    expect(within(inventory).getByText('球洞')).toBeInTheDocument()
    expect(within(inventory).getByText('球杆')).toBeInTheDocument()
    expect(within(inventory).getByText('recent_10')).toBeInTheDocument()
    expect(within(inventory).getAllByRole('button', { name: 'Open source 900001' }).length).toBeGreaterThan(0)
    expect(screen.getByText('报告覆盖 部分 1/3')).toHaveClass('quality-partial')
    expect(screen.getByRole('option', { name: '近10场' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: '2026年Q2' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: '2026年' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: '900001' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Black Knight B/C' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Black Knight B/C H7' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: '1D' })).toBeInTheDocument()
    expect(screen.getByText('Recent scoring improved, but weather coverage is partial.')).toBeInTheDocument()
    expect(screen.getAllByText('recent_10').length).toBeGreaterThan(0)
    expect(screen.getAllByText('static').length).toBeGreaterThan(0)
    expect(screen.getByText('summary_trend')).toBeInTheDocument()
    expect(screen.getAllByText('Black Knight B/C').length).toBeGreaterThan(0)
    expect(screen.getByText('score 77')).toBeInTheDocument()
    expect(screen.getByText('toPar +5')).toBeInTheDocument()
    expect(screen.getByText('rating 72')).toBeInTheDocument()
    expect(screen.getByText('slope 120')).toBeInTheDocument()
    expect(screen.getByText('differential 4.7')).toBeInTheDocument()
    expect(screen.getByText('holeRef 900001:2')).toBeInTheDocument()
    expect(screen.getByText('toPar -1')).toBeInTheDocument()
    expect(screen.getByText('club 1D')).toBeInTheDocument()
    expect(screen.getByText('distance 238')).toBeInTheDocument()
    expect(screen.getAllByText('weather').length).toBeGreaterThan(0)
    expect(screen.getByText('覆盖率 2/3 66.7%')).toBeInTheDocument()
    expect(screen.getByText('中 事实置信')).toBeInTheDocument()
    expect(screen.getByText('覆盖率 1/3 33.3%')).toBeInTheDocument()
    expect(screen.getByText('低 缺失置信')).toBeInTheDocument()
    const inferences = screen.getByLabelText('推断')
    expect(within(inferences).getByRole('heading', { name: '推断' })).toBeInTheDocument()
    expect(within(inferences).getByText('Recent review is based on 3 rounds.')).toBeInTheDocument()
    expect(within(inferences).getByText('summary_trend 事实')).toBeInTheDocument()
    expect(within(inferences).getByText('weather 缺失')).toBeInTheDocument()
    expect(within(inferences).getByText('中 推断置信')).toBeInTheDocument()
    expect(within(inferences).getByRole('button', { name: 'Open source 900001' })).toBeInTheDocument()
    expect(within(inferences).getByRole('button', { name: 'Open source 900002' })).toBeInTheDocument()
    expect(screen.getByText('待复核')).toBeInTheDocument()
    const unsupportedClaims = screen.getByLabelText('无依据断言')
    expect(within(unsupportedClaims).getByRole('heading', { name: '无依据断言' })).toBeInTheDocument()
    expect(within(unsupportedClaims).getByText('weather')).toBeInTheDocument()
    expect(within(unsupportedClaims).getByText('Wind was strong all day.')).toBeInTheDocument()
    expect(within(unsupportedClaims).getByText('Narrative references weather without a supporting structured fact.')).toBeInTheDocument()
    expect(within(unsupportedClaims).getByText('weather 缺失')).toBeInTheDocument()
    expect(within(unsupportedClaims).getByRole('button', { name: 'Open source 900002' })).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Open source 900001' }).length).toBeGreaterThan(0)
    expect(screen.getAllByRole('button', { name: 'Open source 900002' }).length).toBeGreaterThan(0)
    expect(screen.getAllByText('中 置信').length).toBeGreaterThan(0)
    expect(within(screen.getByLabelText('报告信息')).getAllByRole('button', { name: 'Open source 900001' }).length).toBeGreaterThan(0)

    await userEvent.click(screen.getAllByRole('button', { name: 'Open source 900002' })[0])
    await userEvent.click(screen.getByRole('button', { name: '载入趋势报告' }))
    await userEvent.click(screen.getByRole('button', { name: '生成趋势报告' }))
    await userEvent.click(screen.getByRole('button', { name: '载入球局报告' }))
    await userEvent.click(screen.getByRole('button', { name: '生成球局报告' }))
    await userEvent.click(screen.getByRole('button', { name: '载入球场报告' }))
    await userEvent.click(screen.getByRole('button', { name: '生成球场报告' }))
    await userEvent.click(screen.getByRole('button', { name: '载入球洞报告' }))
    await userEvent.click(screen.getByRole('button', { name: '生成球洞报告' }))
    await userEvent.click(screen.getByRole('button', { name: '载入球杆报告' }))
    await userEvent.click(screen.getByRole('button', { name: '生成球杆报告' }))
    await userEvent.click(screen.getByRole('button', { name: '打开已存 趋势 recent_10' }))
    await userEvent.click(screen.getByRole('button', { name: '打开已存 球局 900001' }))
    await userEvent.click(screen.getByRole('button', { name: '打开已存 球场 black_knight' }))
    await userEvent.click(screen.getByRole('button', { name: '打开已存 球洞 black_knight:7' }))
    await userEvent.click(screen.getByRole('button', { name: '打开已存 球杆 1D' }))

    expect(onLoadTrend).toHaveBeenCalledWith('recent_10')
    expect(onGenerateTrend).toHaveBeenCalledWith('recent_10')
    expect(onSelectRef).toHaveBeenCalledWith('900002')
    expect(onLoadRound).toHaveBeenCalledWith('900001')
    expect(onGenerateRound).toHaveBeenCalledWith('900001')
    expect(onLoadCourse).toHaveBeenCalledWith('black_knight')
    expect(onGenerateCourse).toHaveBeenCalledWith('black_knight')
    expect(onLoadHole).toHaveBeenCalledWith('black_knight', 7)
    expect(onGenerateHole).toHaveBeenCalledWith('black_knight', 7)
    expect(onLoadClub).toHaveBeenCalledWith('1D')
    expect(onGenerateClub).toHaveBeenCalledWith('1D')
    expect(onLoadTrend).toHaveBeenCalledWith('recent_10')
    expect(onLoadRound).toHaveBeenCalledWith('900001')

    const facts = screen.getByLabelText('事实')
    expect(within(facts).getByText('summary')).toBeInTheDocument()
  })

  it('truncates the report inventory and appends batches on demand', async () => {
    // 973 real reports rendered at once froze the renderer — the index must cap.
    const manyReports: ReviewReportIndexResponse = {
      schema: 'ai-caddie-review-report-index-v1',
      total: 35,
      reports: Array.from({ length: 35 }, (_, i) => ({
        id: `bulk-${i}`,
        storedAt: '2026-05-26T00:00:00Z',
        kind: 'round' as const,
        subjectId: `r-${i}`,
        confidence: 'medium' as const,
        provider: 'StaticProvider',
        model: 'static',
        sourceRefs: [],
      })),
    }
    render(
      <ReportsPage
        stats={stats}
        reportState={{ status: 'idle' }}
        reportIndexState={{ status: 'ready', data: manyReports }}
        onLoadTrend={vi.fn()}
        onGenerateTrend={vi.fn()}
        onLoadRound={vi.fn()}
        onGenerateRound={vi.fn()}
        onLoadCourse={vi.fn()}
        onGenerateCourse={vi.fn()}
        onLoadHole={vi.fn()}
        onGenerateHole={vi.fn()}
        onLoadClub={vi.fn()}
        onGenerateClub={vi.fn()}
        onSelectRef={vi.fn()}
      />,
    )

    const inventory = screen.getByLabelText('报告索引')
    expect(within(inventory).getAllByText(/^r-\d+$/)).toHaveLength(30)
    const loadMore = within(inventory).getByRole('button', { name: '加载更多(还有 5 条)' })
    await userEvent.click(loadMore)
    expect(within(inventory).getAllByText(/^r-\d+$/)).toHaveLength(35)
    expect(within(inventory).queryByRole('button', { name: /加载更多/ })).not.toBeInTheDocument()
  })
})
