import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { MobileStatsResponse } from '../types'
import { StatsDashboard } from './StatsDashboard'

function statsFixture(overrides: Partial<MobileStatsResponse> = {}): MobileStatsResponse {
  return {
    schema: 'ai-caddie-mobile-stats-v1',
    dataMode: 'fixture',
    summary: {
      totalRounds: 10,
      average18: 86.4,
      bestScore: 79,
      worstScore: 96,
      handicapEstimate: 14.2,
      handicapTrend: -0.8,
    },
    time: {
      byMonth: [
        { key: '2026-05', roundCount: 2, average18: 85, averageDifferential: 14.1 },
        { key: '2026-04', roundCount: 3, average18: 88, averageDifferential: 15.6 },
        { key: '2026-03', roundCount: 2, average18: 90, averageDifferential: 16.2 },
      ],
    },
    scoring: {
      outcomes: { eagleOrBetter: 0, birdie: 12, par: 76, bogey: 82, doubleOrWorse: 30 },
      teeDirection: { hitPct: 57, leftPct: 20, rightPct: 18, recorded: 60, dominantMiss: 'left' },
      approachMiss: {
        girPct: 42,
        shortPct: 30,
        longPct: 12,
        leftPct: 10,
        rightPct: 24,
        recorded: 60,
        dominantMiss: 'short',
      },
      putting: { averagePuttsPerRound: 33.1, averagePutts: 1.9, threePutts: 4, roundsWithPutts: 10 },
    },
    records: {},
    courses: [
      { courseKey: 'pine', courseName: '松山高尔夫', roundCount: 8, average18: 85.1, bestScore: 79 },
      { courseKey: 'mission', courseName: '观澜湖', roundCount: 5, average18: 88.4, bestScore: 83 },
    ],
    clubs: [],
    diagnosis: {
      issueTrends: [
        { issue: 'approach_short', phase: 'Approach', estimatedStrokesLost: 2.1, estimatedStrokesImpact: 2.1 },
        { issue: 'three_putt', phase: 'Putting', estimatedStrokesLost: 0.7, estimatedStrokesImpact: 0.7 },
        { issue: 'tee_left', phase: 'Tee', estimatedStrokesLost: 0, estimatedStrokesImpact: -0.5 },
      ],
    },
    dataQuality: [],
    ...overrides,
  }
}

function allStatsFixture(): MobileStatsResponse {
  return statsFixture({
    summary: { totalRounds: 40, average18: 88, bestScore: 76, worstScore: 101, handicapEstimate: 15.0, handicapTrend: 0 },
    scoring: {
      outcomes: { eagleOrBetter: 1, birdie: 20, par: 300, bogey: 340, doubleOrWorse: 140 },
      teeDirection: { hitPct: 52, recorded: 240 },
      approachMiss: { girPct: 37, shortPct: 28, longPct: 14, leftPct: 12, rightPct: 20, recorded: 240, dominantMiss: 'short' },
      putting: { averagePuttsPerRound: 34.0 },
    },
  })
}

function renderDashboard(overrides: Partial<Parameters<typeof StatsDashboard>[0]> = {}) {
  const onWindowChange = vi.fn()
  render(<StatsDashboard stats={statsFixture()} allStats={null} window="last10" onWindowChange={onWindowChange} {...overrides} />)
  return { onWindowChange }
}

describe('StatsDashboard', () => {
  it('range buttons reflect the active window and drive onWindowChange', async () => {
    const { onWindowChange } = renderDashboard()

    expect(screen.getByRole('button', { name: '近10场' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: '全部' })).toHaveAttribute('aria-pressed', 'false')

    await userEvent.click(screen.getByRole('button', { name: '全部' }))
    expect(onWindowChange).toHaveBeenCalledWith('all')
    await userEvent.click(screen.getByRole('button', { name: '近12个月' }))
    expect(onWindowChange).toHaveBeenCalledWith('12m')
  })

  it('renders the five KPI tiles from real summary/scoring fields', () => {
    renderDashboard()

    expect(within(screen.getByLabelText('差点指数')).getByText('14.2')).toBeInTheDocument()
    expect(within(screen.getByLabelText('平均杆')).getByText('86.4')).toBeInTheDocument()
    expect(within(screen.getByLabelText('标准杆上果岭')).getByText('42%')).toBeInTheDocument()
    expect(within(screen.getByLabelText('开球上球道')).getByText('57%')).toBeInTheDocument()
    expect(within(screen.getByLabelText('平均推杆')).getByText('33.1')).toBeInTheDocument()
  })

  it('shows the handicap 近月 trend from summary.handicapTrend', () => {
    renderDashboard()
    const handicap = screen.getByLabelText('差点指数')
    expect(within(handicap).getByText(/▼ 0.8 近月/)).toBeInTheDocument()
  })

  it('shows — for a missing KPI value and no trend', () => {
    renderDashboard({
      stats: statsFixture({
        summary: { totalRounds: 3, average18: 86.4, handicapEstimate: null, handicapTrend: null },
      }),
    })
    const handicap = screen.getByLabelText('差点指数')
    expect(within(handicap).getByText('—')).toBeInTheDocument()
    expect(within(handicap).queryByText(/近月/)).not.toBeInTheDocument()
  })

  it('shows vs-全部 KPI deltas only when a distinct baseline is present', () => {
    renderDashboard({ allStats: allStatsFixture() })
    // windowed avg 86.4 vs all 88 → improved 1.6 (lower better) → ▼ good
    const avg = screen.getByLabelText('平均杆')
    expect(within(avg).getByText(/▼ 1.6 vs 全部/)).toBeInTheDocument()
    // GIR 42% vs 37% → +5% (higher better) → ▲ good
    const gir = screen.getByLabelText('标准杆上果岭')
    expect(within(gir).getByText(/▲ 5% vs 全部/)).toBeInTheDocument()
  })

  it('hides vs-全部 deltas when allStats is null', () => {
    renderDashboard({ allStats: null })
    expect(screen.queryByText(/vs 全部/)).not.toBeInTheDocument()
  })

  it('renders 各环节失杆 from diagnosis.issueTrends grouped by phase with a total', () => {
    renderDashboard()
    const panel = screen.getByLabelText('各环节失杆')
    const approach = within(panel).getByText('攻果岭').closest('.statsx-sgrow') as HTMLElement
    expect(within(approach).getByText('−2.1')).toBeInTheDocument()
    const putting = within(panel).getByText('推杆').closest('.statsx-sgrow') as HTMLElement
    expect(within(putting).getByText('−0.7')).toBeInTheDocument()
    // Tee had estimatedStrokesLost 0 → no row.
    expect(within(panel).queryByText('开球')).not.toBeInTheDocument()
    const total = within(panel).getByText('总计').closest('.statsx-sgrow') as HTMLElement
    expect(within(total).getByText('−2.8')).toBeInTheDocument()
  })

  it('shows 数据不足 for 各环节失杆 when there are no issue trends', () => {
    renderDashboard({ stats: statsFixture({ diagnosis: {} }) })
    const panel = screen.getByLabelText('各环节失杆')
    expect(within(panel).getByText(/数据不足/)).toBeInTheDocument()
  })

  it('renders the 差点趋势 chart from time.byMonth differentials', () => {
    renderDashboard()
    const panel = screen.getByLabelText('差点趋势')
    expect(within(panel).getByRole('img', { name: '差点趋势图' })).toBeInTheDocument()
    // chronological axis: earliest → latest month
    expect(within(panel).getByText('2026-03')).toBeInTheDocument()
    expect(within(panel).getByText('2026-05')).toBeInTheDocument()
  })

  it('shows 数据不足 for the trend when fewer than two months exist', () => {
    renderDashboard({
      stats: statsFixture({ time: { byMonth: [{ key: '2026-05', averageDifferential: 14.1, average18: 85 }] } }),
    })
    const panel = screen.getByLabelText('差点趋势')
    expect(within(panel).getByText(/数据不足/)).toBeInTheDocument()
  })

  it('renders the 失误倾向 dispersion from approachMiss and captions the bias', () => {
    renderDashboard()
    const panel = screen.getByLabelText('失误倾向')
    expect(within(panel).getByRole('img', { name: '攻果岭失误分布图' })).toBeInTheDocument()
    // right 24 > left 10 and short 30 > long 12 → 偏右且偏短
    expect(within(panel).getByText(/偏右且偏短/)).toBeInTheDocument()
  })

  it('shows 数据不足 for 失误倾向 when nothing was recorded', () => {
    renderDashboard({
      stats: statsFixture({ scoring: { outcomes: { par: 1 }, approachMiss: { recorded: 0 } } }),
    })
    const panel = screen.getByLabelText('失误倾向')
    expect(within(panel).getByText(/数据不足/)).toBeInTheDocument()
  })

  it('renders the 按球场 table from stats.courses', () => {
    renderDashboard()
    const panel = screen.getByLabelText('按球场')
    const pine = within(panel).getByText('松山高尔夫').closest('tr') as HTMLElement
    expect(within(pine).getByText('8')).toBeInTheDocument()
    expect(within(pine).getByText('85.1')).toBeInTheDocument()
    expect(within(pine).getByText('79')).toBeInTheDocument()
  })

  it('renders the 成绩构成 four buckets as percentages', () => {
    renderDashboard()
    const panel = screen.getByLabelText('成绩构成')
    // total = 12 + 76 + 82 + 30 = 200
    const birdie = within(panel).getByText('小鸟及以下').closest('tr') as HTMLElement
    expect(within(birdie).getByText('6%')).toBeInTheDocument()
    const par = within(panel).getByText('标准杆').closest('tr') as HTMLElement
    expect(within(par).getByText('38%')).toBeInTheDocument()
    const bogey = within(panel).getByText('柏忌').closest('tr') as HTMLElement
    expect(within(bogey).getByText('41%')).toBeInTheDocument()
    const double = within(panel).getByText('双柏忌+').closest('tr') as HTMLElement
    expect(within(double).getByText('15%')).toBeInTheDocument()
  })
})
