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
//
// Declared-dropped coverage (round-3 ledger):
// - 近期变化 trend rows deliberately drop the old baseline/recent/rate/actual/
//   confidence numeric facts (conclusions-first redesign); the full numbers
//   remain on the 引擎自检 cost drivers via TrendContextFacts and are asserted
//   in the 引擎自检 suite below.
// - club usableRate chip dropped (风险率 retained, asserted in 按杆).
// - issue source chip ('deterministic') dropped — source only keys React rows.

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
      distanceTrend: { direction: 'shorter', deltaMedian: -16, sampleCount: 8 },
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
          baselineCount: 0,
          recentCount: 1,
          baselineRatePerRound: 0,
          recentRatePerRound: 0.33,
          actualToParImpact: 2,
          actualImpactCoverage: { ready: 3, total: 3 },
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
  it('shows the top-3 weaknesses sorted by severity with zh labels and zh reasons built from structured fields', () => {
    render(<StrengthsPage data={fixture()} onSelectRef={vi.fn()} />)

    expect(screen.getByRole('heading', { name: '你最该练', level: 1 })).toBeInTheDocument()
    const list = screen.getByLabelText('你最该练清单')
    const headings = within(list).getAllByRole('heading', { level: 2 })
    expect(headings.map((heading) => heading.textContent)).toEqual(['1. Par 5 易失分', '2. 开球偏右', '3. 三推太多'])
    // 4th weakness (severity 0.4) is cut at top-3
    expect(within(list).queryByText('1D 距离在变短')).not.toBeInTheDocument()

    // reasons rebuilt in zh from the structured fields (direction/value/unit),
    // not echoed from the backend English sentences
    expect(within(list).getByText('开球失误主要偏右,占已记录失误的 62%')).toBeInTheDocument()
    expect(within(list).getByText('Par 5 洞平均比标准杆多 1.2 杆')).toBeInTheDocument()
    expect(within(list).getByText('有推杆记录的洞中三推 3 次')).toBeInTheDocument()
    expect(within(list).queryByText(/recorded misses/)).not.toBeInTheDocument()
    expect(within(list).queryByText(/to par$/)).not.toBeInTheDocument()

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

  it('maps known English reason sentences to zh templates when only the sentence exists', () => {
    const data = fixture({
      playerProfile: {
        weaknesses: [
          {
            key: 'three_putt_pressure',
            label: 'Three-putt pressure',
            kind: 'weakness',
            phase: 'Putting',
            reason: '364 three-putt holes in recorded putting data',
            severityScore: 3,
            sourceRefs: ['900001:8'],
          },
          {
            key: 'club_distance_shorter_pw',
            label: 'PW trending shorter',
            kind: 'weakness',
            phase: 'Club Confidence',
            reason: 'PW recent median is 27.0m shorter',
            severityScore: 2.5,
            sourceRefs: ['900002:5:4'],
          },
          {
            key: 'mystery_signal',
            label: 'Mystery signal',
            kind: 'weakness',
            phase: 'Scoring',
            reason: 'a bespoke sentence with no known pattern',
            severityScore: 2,
            sourceRefs: ['900003:1'],
          },
        ],
        strengths: [],
      },
    })
    render(<StrengthsPage data={data} />)

    const list = screen.getByLabelText('你最该练清单')
    expect(within(list).getByText('有推杆记录的洞中三推 364 次')).toBeInTheDocument()
    // 27.0m → 30码 via fmtYd
    expect(within(list).getByText('近期常用距离比基准短 30码')).toBeInTheDocument()
    // unknown sentences stay raw rather than vanish
    expect(within(list).getByText('a bespoke sentence with no known pattern')).toBeInTheDocument()
  })

  it('renders retired Garmin club nicknames as 「48°(已退役)」 in weakness labels', () => {
    const data = fixture({
      playerProfile: {
        weaknesses: [
          {
            key: 'club_distance_shorter_48° 退役',
            label: '48° 退役 trending shorter',
            kind: 'weakness',
            phase: 'Club Confidence',
            reason: '48° 退役 recent median is 16.0m shorter',
            value: 16,
            unit: 'meters',
            severityScore: 2,
            sourceRefs: ['900002:5:4'],
          },
        ],
        strengths: [],
      },
    })
    render(<StrengthsPage data={data} />)

    const list = screen.getByLabelText('你最该练清单')
    expect(within(list).getByRole('heading', { name: '1. 48°(已退役) 距离在变短' })).toBeInTheDocument()
    expect(within(list).queryByText(/48° 退役/)).not.toBeInTheDocument()
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
    // (bucket labels repeat in the below-bar refs row, hence getAllByText)
    expect(within(section).queryByText('帕')).not.toBeInTheDocument()
    expect(within(section).getAllByText('柏忌').length).toBeGreaterThan(0)
    expect(within(section).getAllByText('双+').length).toBeGreaterThan(0)
    expect(within(section).getAllByText('50%')).toHaveLength(2)

    // repeated issues in zh — Course Management is 场上决策, never 攻略
    expect(within(section).getByText('双柏忌或更差')).toBeInTheDocument()
    expect(within(section).getByText('场上决策')).toBeInTheDocument()

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
    // distanceTrend deltaMedian -16m → 17码 via fmtYd, semantic trend class kept
    expect(within(section).getByText('近期短 17码')).toHaveClass('semantic-chip', 'trend-shorter')
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

  it('renders 近期长 for longer trends and skips the chip for stable/insufficient/missing trends', () => {
    const data = fixture({
      clubs: [
        { ...baseFixture.clubs[0], club: '5I', distanceTrend: { direction: 'longer', deltaMedian: 8 } },
        { ...baseFixture.clubs[0], club: '7I', distanceTrend: { direction: 'stable', deltaMedian: 1 } },
        { ...baseFixture.clubs[0], club: '9I', distanceTrend: { direction: 'insufficient_data', deltaMedian: null } },
        { ...baseFixture.clubs[0], club: 'PW', distanceTrend: undefined },
      ],
    })
    render(<StrengthsPage data={data} />)

    const section = screen.getByLabelText('按杆')
    // +8m → 9码
    expect(within(section).getByText('近期长 9码')).toHaveClass('semantic-chip', 'trend-longer')
    // stable / insufficient_data / missing all render no trend chip
    expect(within(section).getAllByText(/近期[短长]/)).toHaveLength(1)
  })

  it('renders retired club nicknames as 「48°(已退役)」', () => {
    const data = fixture({ clubs: [{ ...baseFixture.clubs[0], club: '48° 退役' }] })
    render(<StrengthsPage data={data} />)

    const section = screen.getByLabelText('按杆')
    expect(within(section).getByRole('heading', { name: '48°(已退役)' })).toBeInTheDocument()
    expect(within(section).queryByRole('heading', { name: '48° 退役' })).not.toBeInTheDocument()
  })
})

describe('StrengthsPage 出处筹码', () => {
  it('caps visible ref chips at 2 with a 等 N 处 expander and keeps every ref drillable', async () => {
    const onSelectRef = vi.fn()
    const data = fixture({
      holes: [
        {
          ...baseFixture.holes[0],
          refs: ['900001:7', '900002:7', '900003:7', '900004:7'],
        },
      ],
    })
    render(<StrengthsPage data={data} onSelectRef={onSelectRef} />)

    const section = screen.getByLabelText('按洞')
    expect(within(section).getAllByRole('button', { name: 'Open source 900001:7' }).length).toBeGreaterThan(0)
    expect(within(section).queryByRole('button', { name: 'Open source 900004:7' })).not.toBeInTheDocument()

    await userEvent.click(within(section).getByRole('button', { name: '展开其余 2 处来源' }))
    await userEvent.click(within(section).getByRole('button', { name: 'Open source 900004:7' }))
    expect(onSelectRef).toHaveBeenCalledWith('900004:7')
  })

  it('moves distribution evidence chips out of the bar buckets into a row below the bar', () => {
    const data = fixture({
      holes: [
        {
          ...baseFixture.holes[0],
          scoreDistribution: [
            { key: 'bogey', label: 'Bogey', className: 'bogey', count: 1, pct: 50, holeRefs: ['900001:7', '900002:7', '900003:7'] },
            { key: 'doubleOrWorse', label: 'Double+', className: 'double', count: 1, pct: 50, holeRefs: ['900002:7'] },
          ],
        },
      ],
    })
    const { container } = render(<StrengthsPage data={data} onSelectRef={vi.fn()} />)

    // bar buckets carry only the outcome facts — no ref chips inside
    // (guarded against a class rename making the loop pass vacuously)
    const buckets = Array.from(container.querySelectorAll('.hole-distribution-bucket'))
    expect(buckets.length).toBeGreaterThan(0)
    for (const bucket of buckets) {
      expect(within(bucket as HTMLElement).queryByRole('button', { name: /Open source/ })).not.toBeInTheDocument()
    }

    // the refs live in the dedicated row below the bar, capped at 2 per bucket
    const refsRow = container.querySelector('.w4-distribution-refs') as HTMLElement
    expect(refsRow).not.toBeNull()
    expect(within(refsRow).getAllByText('柏忌').length).toBe(1)
    expect(within(refsRow).getByRole('button', { name: 'Open source 900001:7' })).toBeInTheDocument()
    expect(within(refsRow).queryByRole('button', { name: 'Open source 900003:7' })).not.toBeInTheDocument()
    expect(within(refsRow).getByRole('button', { name: '展开其余 1 处来源' })).toHaveTextContent('等 1 处')
  })
})

describe('StrengthsPage 问题', () => {
  it('renders issue rows with zh labels, counts and trend diagnosis', async () => {
    const onSelectRef = vi.fn()
    render(<StrengthsPage data={fixture()} onSelectRef={onSelectRef} />)

    expect(screen.getByRole('heading', { name: '问题' })).toBeInTheDocument()
    const section = screen.getByLabelText('问题')
    // trends vs totals each get a visible sub-heading so the numbers read
    // as 「近期变化 +3 次」 / 「全部问题 2 次」 instead of bare +3 / 2
    expect(within(section).getByRole('heading', { name: '近期变化' })).toBeInTheDocument()
    expect(within(section).getByRole('heading', { name: '全部问题' })).toBeInTheDocument()
    expect(within(section).getByText('缺少击球数据')).toBeInTheDocument()
    expect(within(section).getByText('数据质量')).toBeInTheDocument()
    expect(within(section).getByText('信心高')).toHaveClass('confidence-high')
    expect(within(section).getByText('2 次')).toBeInTheDocument()

    // recent cost trend in zh, with the delta labeled as a signed count
    expect(within(section).getByText('三推')).toBeInTheDocument()
    expect(within(section).getByText('估损 3.0杆')).toBeInTheDocument()
    expect(within(section).getByText('+3 次')).toBeInTheDocument()

    await userEvent.click(within(section).getByRole('button', { name: 'Open source 900003' }))
    expect(onSelectRef).toHaveBeenCalledWith('900003')
    await userEvent.click(within(section).getByRole('button', { name: 'Open source 900004:7' }))
    expect(onSelectRef).toHaveBeenCalledWith('900004:7')
  })

  it('renders an empty state when no recurring issues exist', () => {
    render(<StrengthsPage data={fixture({ issues: [] })} />)
    expect(screen.getByText('暂无重复问题')).toBeInTheDocument()
    // no totals list → no 全部问题 sub-heading above the empty state
    expect(screen.queryByRole('heading', { name: '全部问题' })).not.toBeInTheDocument()
  })
})

// Real data: 1200+ hole rows / dozens of clubs and issues rendered all at once
// froze the page. Sections cap their rows and expand on demand; data unchanged.
describe('StrengthsPage 大数据截断', () => {
  function manyHoles(count: number) {
    return Array.from({ length: count }, (_, index) => ({
      courseKey: 'black_knight',
      hole: index + 1,
      sampleCount: 2,
      averageToPar: 1,
      worstToPar: 2,
      refs: [`9000${index}:1`],
    }))
  }

  function manyClubs(count: number) {
    return Array.from({ length: count }, (_, index) => ({
      club: `C${index + 1}`,
      sampleCount: 3,
      median: 100 + index,
      p10: 90,
      p90: 110,
      max: 120,
      shotRefs: [`9000${index}:1:0`],
    }))
  }

  function manyIssues(count: number) {
    return Array.from({ length: count }, (_, index) => ({
      issue: `issue_${index + 1}`,
      count: index + 1,
      refs: [`9000${index}`],
    }))
  }

  it('按洞 caps at 24 rows with an aria-expanded 展开全部 toggle', async () => {
    const data = fixture({ holes: manyHoles(25), diagnosis: {} })
    const { container } = render(<StrengthsPage data={data} />)

    expect(container.querySelectorAll('.hole-stats-item')).toHaveLength(24)
    const section = screen.getByLabelText('按洞')
    const toggle = within(section).getByRole('button', { name: '展开全部(共 25)' })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')

    await userEvent.click(toggle)

    expect(container.querySelectorAll('.hole-stats-item')).toHaveLength(25)
    expect(within(section).getByRole('button', { name: '收起' })).toHaveAttribute('aria-expanded', 'true')
  })

  it('按杆 and 问题 cap at 30 rows with the same expand affordance', async () => {
    const data = fixture({ clubs: manyClubs(31), issues: manyIssues(31), diagnosis: {} })
    render(<StrengthsPage data={data} />)

    const clubSection = screen.getByLabelText('按杆')
    expect(clubSection.querySelectorAll('article.stats-item')).toHaveLength(30)
    await userEvent.click(within(clubSection).getByRole('button', { name: '展开全部(共 31)' }))
    expect(clubSection.querySelectorAll('article.stats-item')).toHaveLength(31)

    const issueSection = screen.getByLabelText('问题')
    expect(issueSection.querySelectorAll('article.stats-item')).toHaveLength(30)
    await userEvent.click(within(issueSection).getByRole('button', { name: '展开全部(共 31)' }))
    expect(issueSection.querySelectorAll('article.stats-item')).toHaveLength(31)
  })

  it('renders no expand toggle when a section is under its cap', () => {
    render(<StrengthsPage data={fixture()} />)
    expect(screen.queryByRole('button', { name: /展开全部/ })).not.toBeInTheDocument()
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

    // TrendContextFacts on the cost drivers — intentionally English (engine
    // vocabulary inside the advanced details block), including the restored
    // actual {ready}/{total} coverage span from the old IssueStats
    expect(within(details).getByText('baseline 0')).toBeInTheDocument()
    expect(within(details).getByText('recent 1')).toBeInTheDocument()
    expect(within(details).getByText('rate 0 -> 0.33/round')).toBeInTheDocument()
    expect(within(details).getByText('+2 actual to-par')).toBeInTheDocument()
    expect(within(details).getByText('actual 3/3')).toBeInTheDocument()
  })

  it('omits the details block when there is no audit content', () => {
    render(<StrengthsPage data={fixture({ diagnosis: { issueTrends: [] } })} />)
    expect(screen.queryByText('引擎自检（高级）')).not.toBeInTheDocument()
  })
})
