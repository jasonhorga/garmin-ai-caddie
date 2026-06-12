import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { HistoryStatsResponse } from '../types'
import { StrengthsPage } from './StrengthsPage'

// Test ledger: this suite absorbs the behavioral assertions of the deleted
// HoleStats.test / ClubStats.test / IssueStats.test suites — hole aggregates +
// distribution + repeated issues, club distance/dispersion/confidence, issue
// counts + trend diagnosis + decision-audit content, the onSelectRef drilldown
// clicks, and the per-section empty states. Display-only chips that the
// redesign intentionally drops (StatsQualityChips header chips, club
// valid/invalid/outlier/surface/consistency chips, AggregateEvidence coverage
// chips on simple rows) are not re-asserted.

const baseFixture: HistoryStatsResponse = {
  schema: 'ai-caddie-history-stats-v1',
  dataMode: 'fixture',
  summary: {},
  time: {},
  scoring: {
    phaseStats: [
      { phase: 'Tee', fairwaysHit: 6, sampleCount: 10, sourceRefs: ['900001:1'] },
      { phase: 'Approach', girPct: 44, sampleCount: 18, sourceRefs: ['900001:7'] },
      { phase: 'Putting', averagePutts: 1.9, sampleCount: 18, sourceRefs: ['900001:8'] },
    ],
  },
  courseDistribution: [],
  records: {},
  courses: [{ courseKey: 'black_knight', courseName: 'Black Knight B' }],
  holes: [
    {
      courseKey: 'black_knight',
      hole: 7,
      sampleCount: 2,
      averageToPar: 1.5,
      worstToPar: 3,
      geometryCoverage: 'missing',
      scoreDistribution: [
        { key: 'par', label: 'Par', className: 'par', count: 0, pct: 0, holeRefs: [] },
        { key: 'bogey', label: 'Bogey', className: 'bogey', count: 1, pct: 50, holeRefs: ['900001:7'] },
        { key: 'doubleOrWorse', label: 'Double+', className: 'double', count: 1, pct: 50, holeRefs: ['900002:7'] },
      ],
      repeatedIssues: [
        { issue: 'double_or_worse', count: 1, refs: ['900002:7'], phase: 'Course Management', confidence: 'high' },
      ],
      refs: ['900001:7', '900002:7'],
    },
  ],
  clubs: [
    {
      club: '1D',
      sampleCount: 2,
      median: 240,
      p10: 225,
      p90: 255,
      max: 270,
      confidence: 'low',
      hazardRate: 25,
      shotRefs: ['900001:1:0', '900002:5:4'],
      validShotRefs: ['900001:1:0', '900002:5:4'],
      riskShotRefs: ['900005:7:1'],
    },
  ],
  issues: [
    {
      issue: 'missing_shots',
      count: 2,
      refs: ['900002', '900003'],
      phase: 'Data Quality',
      source: 'deterministic',
      confidence: 'high',
    },
  ],
  diagnosis: {
    issueTrends: [
      {
        issue: 'three_putt',
        phase: 'Putting',
        direction: 'new',
        deltaCount: 3,
        estimatedStrokesLost: 3,
        recentRefs: ['900004:7', '900005:7'],
        sourceRefs: ['900004:7', '900005:7'],
        confidence: 'medium',
      },
    ],
    decisionAuditTrends: {
      classificationCounts: [
        { classification: 'execution', count: 2, pct: 66.7, sourceRefs: ['900001:7', '900002:8'], confidence: 'medium' },
      ],
      recentCostDrivers: [
        {
          classification: 'strategy',
          phase: 'tee_shot',
          direction: 'new',
          deltaCount: 1,
          estimatedStrokesLost: 1.2,
          recentRefs: ['900002:7'],
          confidence: 'low',
        },
      ],
      criteriaBreakdown: [
        { label: 'avoid_zones', status: 'fail', count: 2, pct: 66.7, sourceRefs: ['900001:7', '900002:7'], confidence: 'medium' },
      ],
      optionOutcomes: [
        { selectedOptionId: 'safe', actualOptionId: 'attack', classification: 'strategy', count: 1, pct: 33.3, sourceRefs: ['900002:7'], confidence: 'low' },
      ],
    },
  },
  playerProfile: {
    weaknesses: [
      {
        key: 'three_putt_pressure',
        label: 'Three-putt pressure',
        kind: 'weakness',
        phase: 'Putting',
        reason: '3 three-putt holes in recorded putting data',
        value: 3,
        unit: 'count',
        severityScore: 1.05,
        sourceRefs: ['900001:8'],
      },
      {
        key: 'tee_miss_right',
        label: 'Tee miss right',
        kind: 'weakness',
        phase: 'Tee',
        reason: 'dominant tee miss is right with 62% recorded misses',
        value: 62,
        unit: 'pct',
        direction: 'right',
        severityScore: 1.1,
        sourceRefs: ['900001:1'],
      },
      {
        key: 'par5_scoring_loss',
        label: 'Par 5 scoring loss',
        kind: 'weakness',
        phase: 'Scoring',
        reason: 'Par 5 averages +1.2 to par',
        value: 1.2,
        unit: 'to_par',
        severityScore: 1.2,
        sourceRefs: ['900001:5'],
      },
      {
        key: 'club_distance_shorter_1d',
        label: '1D trending shorter',
        kind: 'weakness',
        phase: 'Club Confidence',
        reason: '1D recent median is 16.0m shorter',
        value: 16,
        unit: 'meters',
        severityScore: 0.4,
        sourceRefs: ['900002:5:4'],
      },
    ],
    strengths: [],
  },
  dataQuality: [],
  drillDown: {},
}

function fixture(overrides: Partial<HistoryStatsResponse> = {}): HistoryStatsResponse {
  return { ...baseFixture, ...overrides }
}

describe('StrengthsPage 你最该练', () => {
  it('shows the top-3 weaknesses sorted by severity with zh labels and English reasons as secondary lines', () => {
    render(<StrengthsPage data={fixture()} onSelectRef={vi.fn()} />)

    expect(screen.getByRole('heading', { name: '你最该练', level: 1 })).toBeInTheDocument()
    const list = screen.getByLabelText('你最该练清单')
    const headings = within(list).getAllByRole('heading', { level: 2 })
    expect(headings.map((heading) => heading.textContent)).toEqual(['1. Par 5 易失分', '2. 开球偏右', '3. 三推太多'])
    // 4th weakness (severity 0.4) is cut at top-3
    expect(within(list).queryByText('1D 距离在变短')).not.toBeInTheDocument()

    // English reasons stay readable as secondary lines
    expect(within(list).getByText('dominant tee miss is right with 62% recorded misses')).toBeInTheDocument()
    expect(within(list).getByText('Par 5 averages +1.2 to par')).toBeInTheDocument()

    // value + phase chips in zh
    expect(within(list).getByText('62%')).toBeInTheDocument()
    expect(within(list).getByText('3次')).toBeInTheDocument()
    expect(within(list).getByText('平均+1.2杆')).toBeInTheDocument()
    expect(within(list).getByText('开球')).toBeInTheDocument()
    expect(within(list).getByText('得分')).toBeInTheDocument()

    // source chips drill down
    expect(within(list).getByRole('button', { name: 'Open source 900001:5' })).toBeInTheDocument()
  })

  it('falls back to top issues when the player profile has no weaknesses', () => {
    const data = fixture({
      playerProfile: { weaknesses: [], strengths: [] },
      issues: [
        { issue: 'approach_short', count: 6, phase: 'Approach', refs: ['900001:7'] },
        { issue: 'three_putt', count: 2, phase: 'Putting', refs: ['900001:8'] },
      ],
    })
    render(<StrengthsPage data={data} />)

    const list = screen.getByLabelText('你最该练清单')
    const headings = within(list).getAllByRole('heading', { level: 2 })
    expect(headings.map((heading) => heading.textContent)).toEqual(['1. 攻果岭偏短', '2. 三推'])
    expect(within(list).getByText('6次')).toBeInTheDocument()
  })

  it('shows the 样本不足 empty state when there are no weaknesses and no issues', () => {
    const data = fixture({ playerProfile: undefined, issues: [] })
    render(<StrengthsPage data={data} />)

    expect(screen.getByText('样本不足，先多打几场')).toBeInTheDocument()
  })
})

describe('StrengthsPage 总体数字', () => {
  it('computes fairway hit %, GIR and average putts from phaseStats', () => {
    render(<StrengthsPage data={fixture()} />)

    const metrics = screen.getByLabelText('总体数字')
    const fairway = within(metrics).getByText('球道命中率').closest('article') as HTMLElement
    expect(within(fairway).getByText('60%')).toBeInTheDocument()
    expect(within(fairway).getByText('6/10 个开球洞')).toBeInTheDocument()

    const gir = within(metrics).getByText('GIR 上果岭率').closest('article') as HTMLElement
    expect(within(gir).getByText('44%')).toBeInTheDocument()

    const putts = within(metrics).getByText('平均推杆').closest('article') as HTMLElement
    expect(within(putts).getByText('1.9')).toBeInTheDocument()
    expect(within(putts).getByText(/估算/)).toBeInTheDocument()
  })

  it('hides cards with missing inputs and the whole row when phaseStats is absent', () => {
    const onlyPutting = fixture({
      scoring: { phaseStats: [{ phase: 'Putting', averagePutts: 2.1, sampleCount: 9 }] },
    })
    const { unmount } = render(<StrengthsPage data={onlyPutting} />)
    expect(screen.queryByText('球道命中率')).not.toBeInTheDocument()
    expect(screen.queryByText('GIR 上果岭率')).not.toBeInTheDocument()
    expect(screen.getByText('平均推杆')).toBeInTheDocument()
    unmount()

    render(<StrengthsPage data={fixture({ scoring: {} })} />)
    expect(screen.queryByLabelText('总体数字')).not.toBeInTheDocument()
  })
})

describe('StrengthsPage 按洞', () => {
  it('renders hole rows with zh facts, distribution, repeated issues and drilldown refs', async () => {
    const onSelectRef = vi.fn()
    render(<StrengthsPage data={fixture()} onSelectRef={onSelectRef} />)

    expect(screen.getByRole('heading', { name: '按洞' })).toBeInTheDocument()
    const section = screen.getByLabelText('按洞')
    expect(within(section).getByRole('heading', { name: '第7洞' })).toBeInTheDocument()
    // courseKey resolves to the course name via data.courses
    expect(within(section).getByText('Black Knight B')).toBeInTheDocument()
    expect(within(section).getByText('打过2次')).toBeInTheDocument()
    expect(within(section).getByText('平均+1.5')).toBeInTheDocument()
    expect(within(section).getByText('最差+3')).toBeInTheDocument()
    expect(within(section).getByText('几何缺失')).toHaveClass('quality-missing')

    // zero-count buckets are filtered; remaining buckets are zh-labelled
    expect(within(section).queryByText('帕')).not.toBeInTheDocument()
    expect(within(section).getByText('柏忌')).toBeInTheDocument()
    expect(within(section).getByText('双+')).toBeInTheDocument()
    expect(within(section).getAllByText('50%')).toHaveLength(2)

    // repeated issues in zh
    expect(within(section).getByText('双柏忌或更差')).toBeInTheDocument()
    expect(within(section).getByText('攻略')).toBeInTheDocument()

    await userEvent.click(within(section).getAllByRole('button', { name: 'Open source 900001:7' })[0])
    expect(onSelectRef).toHaveBeenCalledWith('900001:7')
  })

  it('renders an empty state when no hole aggregates exist', () => {
    render(<StrengthsPage data={fixture({ holes: [] })} />)
    expect(screen.getByText('暂无逐洞数据')).toBeInTheDocument()
  })
})

describe('StrengthsPage 按杆', () => {
  it('renders club rows with all distances in yards and zh confidence', async () => {
    const onSelectRef = vi.fn()
    render(<StrengthsPage data={fixture()} onSelectRef={onSelectRef} />)

    expect(screen.getByRole('heading', { name: '按杆' })).toBeInTheDocument()
    const section = screen.getByLabelText('按杆')
    expect(within(section).getByRole('heading', { name: '1D' })).toBeInTheDocument()
    // 240m → 262码, 225m → 246码, 255m → 279码, 270m → 295码
    expect(within(section).getByText('常用距离 262码')).toBeInTheDocument()
    expect(within(section).getByText('波动 246码–279码')).toBeInTheDocument()
    expect(within(section).getByText('最远 295码')).toBeInTheDocument()
    expect(within(section).getByText('样本 2')).toBeInTheDocument()
    expect(within(section).getByText('风险率 25%')).toBeInTheDocument()
    expect(within(section).getByText('信心低')).toHaveClass('confidence-low')

    await userEvent.click(within(section).getByRole('button', { name: 'Open source 900001:1:0' }))
    expect(onSelectRef).toHaveBeenCalledWith('900001:1:0')
    // risk shots stay drillable
    expect(within(section).getByRole('button', { name: 'Open source 900005:7:1' })).toBeInTheDocument()
  })

  it('renders an empty state when no club samples exist', () => {
    render(<StrengthsPage data={fixture({ clubs: [] })} />)
    expect(screen.getByText('暂无球杆样本')).toBeInTheDocument()
  })
})

describe('StrengthsPage 问题', () => {
  it('renders issue rows with zh labels, counts and trend diagnosis', async () => {
    const onSelectRef = vi.fn()
    render(<StrengthsPage data={fixture()} onSelectRef={onSelectRef} />)

    expect(screen.getByRole('heading', { name: '问题' })).toBeInTheDocument()
    const section = screen.getByLabelText('问题')
    expect(within(section).getByText('缺少击球数据')).toBeInTheDocument()
    expect(within(section).getByText('数据质量')).toBeInTheDocument()
    expect(within(section).getByText('信心高')).toHaveClass('confidence-high')
    expect(within(section).getByText('2')).toBeInTheDocument()

    // recent cost trend in zh
    expect(within(section).getByText('三推')).toBeInTheDocument()
    expect(within(section).getByText('估损 3.0杆')).toBeInTheDocument()
    expect(within(section).getByText('+3')).toBeInTheDocument()

    await userEvent.click(within(section).getByRole('button', { name: 'Open source 900003' }))
    expect(onSelectRef).toHaveBeenCalledWith('900003')
    await userEvent.click(within(section).getByRole('button', { name: 'Open source 900004:7' }))
    expect(onSelectRef).toHaveBeenCalledWith('900004:7')
  })

  it('renders an empty state when no recurring issues exist', () => {
    render(<StrengthsPage data={fixture({ issues: [] })} />)
    expect(screen.getByText('暂无重复问题')).toBeInTheDocument()
  })
})

describe('StrengthsPage 引擎自检', () => {
  it('keeps the decision-audit content inside a closed details block at the page bottom', () => {
    render(<StrengthsPage data={fixture()} onSelectRef={vi.fn()} />)

    expect(screen.getByText('引擎自检（高级）')).toBeInTheDocument()
    const details = screen.getByText('引擎自检（高级）').closest('details') as HTMLDetailsElement
    expect(details.open).toBe(false)
    expect(within(details).getByText('execution')).toBeInTheDocument()
    expect(within(details).getByText('66.7%')).toBeInTheDocument()
    expect(within(details).getByText('avoid_zones')).toBeInTheDocument()
    expect(within(details).getByText('fail')).toHaveClass('status-fail')
    expect(within(details).getByText('66.7% audits')).toBeInTheDocument()
    expect(within(details).getByText('safe -> attack')).toBeInTheDocument()
    expect(within(details).getByText('33.3% audits')).toBeInTheDocument()
    expect(within(details).getByText('1.2 est. strokes')).toBeInTheDocument()
    expect(within(details).getAllByRole('button', { name: 'Open source 900002:7' }).length).toBeGreaterThan(0)
  })

  it('omits the details block when there is no audit content', () => {
    render(<StrengthsPage data={fixture({ diagnosis: { issueTrends: [] } })} />)
    expect(screen.queryByText('引擎自检（高级）')).not.toBeInTheDocument()
  })
})
