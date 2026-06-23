import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { MobileStatsResponse, RoundCard as RoundCardType } from '../types'
import { TrendsOverview } from './TrendsOverview'

function statsFixture(overrides: Partial<MobileStatsResponse> = {}): MobileStatsResponse {
  return {
    schema: 'ai-caddie-mobile-stats-v1',
    dataMode: 'fixture',
    summary: {
      totalRounds: 10,
      average18: 90,
      bestScore: 82,
      worstScore: 98,
      handicapEstimate: 16.4,
      handicapTrend: -0.8,
    },
    time: {
      byMonth: [
        { key: '2026-05', roundCount: 2, average18: 88, averageDifferential: 15.2 },
        { key: '2026-04', roundCount: 3, average18: 91, averageDifferential: null },
      ],
    },
    scoring: {
      outcomes: { eagleOrBetter: 0, birdie: 2, par: 7, bogey: 8, doubleOrWorse: 3, parOrBetter: 9 },
      // 20 outcome holes: birdie 2→10%, par 7→35%, bogey 8→40%, double 2→10%, triple 1→5%
      outcomeDistribution: [
        { key: 'eagleOrBetter', label: 'Eagle+', count: 0, pct: 0 },
        { key: 'birdie', label: 'Birdie', count: 2, pct: 10 },
        { key: 'par', label: 'Par', count: 7, pct: 35 },
        { key: 'bogey', label: 'Bogey', count: 8, pct: 40 },
        { key: 'double', label: 'Double', count: 2, pct: 10 },
        { key: 'triple', label: 'Triple', count: 1, pct: 5 },
        { key: 'quadPlus', label: '+4 or worse', count: 0, pct: 0 },
      ],
    },
    records: {},
    courses: [],
    clubs: [],
    // real shape: diagnosis.topIssue is a row object {issue, phase, ...}, not a bare string
    diagnosis: { topIssue: { issue: 'tee_right', phase: 'Tee' } },
    dataQuality: [],
    ...overrides,
  }
}

function allStatsFixture(): MobileStatsResponse {
  return statsFixture({
    summary: { totalRounds: 40, average18: 92, bestScore: 78, worstScore: 103 },
    scoring: {
      outcomes: { eagleOrBetter: 1, birdie: 5, par: 35, bogey: 40, doubleOrWorse: 19, parOrBetter: 41 },
    },
  })
}

function roundsFixture(): RoundCardType[] {
  return [
    {
      id: '900010',
      date: '2026-06-05T08:00:00',
      courseName: '棕榈泉乡村俱乐部',
      courseKey: 'palm_springs',
      holesCompleted: 18,
      score: 88,
      par: 72,
      toPar: 16,
      scoreStrip: [],
      badges: [],
      primaryIssue: null,
    },
    {
      id: '900009',
      date: '2026-05-28T08:00:00',
      courseName: '观澜湖·奥拉沙宝场',
      courseKey: 'mission_hills',
      holesCompleted: 18,
      score: 91,
      par: 72,
      toPar: 19,
      scoreStrip: [],
      badges: [],
      primaryIssue: null,
    },
  ]
}

function renderTrends(overrides: Partial<Parameters<typeof TrendsOverview>[0]> = {}) {
  const onWindowChange = vi.fn()
  const onOpenRoundDetail = vi.fn()
  render(
    <TrendsOverview
      stats={statsFixture()}
      allStats={null}
      window="last10"
      onWindowChange={onWindowChange}
      recentRounds={roundsFixture()}
      onOpenRoundDetail={onOpenRoundDetail}
      {...overrides}
    />,
  )
  return { onWindowChange, onOpenRoundDetail }
}

describe('TrendsOverview', () => {
  it('window buttons reflect the active window and call onWindowChange', async () => {
    const { onWindowChange } = renderTrends()

    expect(screen.getByRole('button', { name: '近10场' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: '全部' })).toHaveAttribute('aria-pressed', 'false')

    await userEvent.click(screen.getByRole('button', { name: '全部' }))
    expect(onWindowChange).toHaveBeenCalledWith('all')

    await userEvent.click(screen.getByRole('button', { name: '近12个月' }))
    expect(onWindowChange).toHaveBeenCalledWith('12m')
  })

  it('renders the four KPI cards from the windowed stats', () => {
    renderTrends()

    const average = screen.getByText('均杆(18洞)').closest('article') as HTMLElement
    expect(within(average).getByText('90')).toBeInTheDocument()

    const handicap = screen.getByText('差点(估算)').closest('article') as HTMLElement
    expect(within(handicap).getByText('16.4')).toBeInTheDocument()
    expect(within(handicap).getByText(/▼ 0.8/)).toBeInTheDocument()

    const range = screen.getByText('得分区间').closest('article') as HTMLElement
    expect(within(range).getByText('82–98')).toBeInTheDocument()

    // parOrBetter 9 / 20 outcome holes = 45%
    const parOrBetter = screen.getByText('帕或更好率').closest('article') as HTMLElement
    expect(within(parOrBetter).getByText('45%')).toBeInTheDocument()
  })

  it('shows — for a null handicap estimate', () => {
    renderTrends({
      stats: statsFixture({
        summary: { totalRounds: 3, average18: 90, bestScore: 82, worstScore: 98, handicapEstimate: null, handicapTrend: null },
      }),
    })

    const handicap = screen.getByText('差点(估算)').closest('article') as HTMLElement
    expect(within(handicap).getByText('—')).toBeInTheDocument()
    expect(within(handicap).queryByText(/▼|▲/)).not.toBeInTheDocument()
  })

  it('falls back to the all-window 差点 when the windowed estimate is null', () => {
    // Real-data case: last10 often has <5 differential-bearing rounds → windowed
    // handicapEstimate is null while the all-window estimate exists.
    renderTrends({
      stats: statsFixture({
        summary: { totalRounds: 3, average18: 90, bestScore: 82, worstScore: 98, handicapEstimate: null, handicapTrend: null },
      }),
      allStats: statsFixture({
        summary: { totalRounds: 40, average18: 92, bestScore: 78, worstScore: 103, handicapEstimate: 17.2, handicapTrend: -0.3 },
      }),
    })

    const handicap = screen.getByText('差点(估算)').closest('article') as HTMLElement
    expect(within(handicap).getByText('17.2')).toBeInTheDocument()
    expect(within(handicap).queryByText('—')).not.toBeInTheDocument()
    // The delta/trend sub stays suppressed — it would compare a value against itself.
    expect(within(handicap).queryByText(/▼|▲/)).not.toBeInTheDocument()
  })

  it('shows vs-全部 deltas only when allStats is present', () => {
    renderTrends({ allStats: allStatsFixture() })

    const average = screen.getByText('均杆(18洞)').closest('article') as HTMLElement
    expect(within(average).getByText(/▼ 2/)).toBeInTheDocument()
    expect(within(average).getByText(/vs 全部\(92\)/)).toBeInTheDocument()

    // windowed 45% vs all 41% = +4 percentage points (higher is better → ▲)
    const parOrBetter = screen.getByText('帕或更好率').closest('article') as HTMLElement
    expect(within(parOrBetter).getByText(/▲ 4%/)).toBeInTheDocument()
    expect(within(parOrBetter).getByText(/vs 全部/)).toBeInTheDocument()
  })

  it('hides vs-全部 deltas when allStats is null', () => {
    renderTrends({ allStats: null })
    expect(screen.queryByText(/vs 全部/)).not.toBeInTheDocument()
  })

  it('renders 成绩构成 percentage bars from the outcome buckets', () => {
    renderTrends()

    const panel = screen.getByLabelText('成绩构成')
    // GolfLive 7-bucket spread from scoring.outcomeDistribution (pct comes straight from the contract)
    const birdie = within(panel).getByText('小鸟').closest('div') as HTMLElement
    expect(within(birdie).getByText('10%')).toBeInTheDocument()
    const par = within(panel).getByText('标准杆').closest('div') as HTMLElement
    expect(within(par).getByText('35%')).toBeInTheDocument()
    const bogey = within(panel).getByText('柏忌').closest('div') as HTMLElement
    expect(within(bogey).getByText('40%')).toBeInTheDocument()
    const double = within(panel).getByText('双柏忌').closest('div') as HTMLElement
    expect(within(double).getByText('10%')).toBeInTheDocument()
    const triple = within(panel).getByText('+3').closest('div') as HTMLElement
    expect(within(triple).getByText('5%')).toBeInTheDocument()
  })

  it('labels the top issue in Chinese and falls back to the raw token', () => {
    const { unmount } = render(
      <TrendsOverview
        stats={statsFixture()}
        allStats={null}
        window="last10"
        onWindowChange={vi.fn()}
        recentRounds={[]}
      />,
    )
    expect(screen.getByText(/最吃杆/)).toBeInTheDocument()
    expect(screen.getByText('开球偏右')).toBeInTheDocument()
    unmount()

    render(
      <TrendsOverview
        stats={statsFixture({ diagnosis: { topIssue: { issue: 'mystery_token' } } })}
        allStats={null}
        window="last10"
        onWindowChange={vi.fn()}
        recentRounds={[]}
      />,
    )
    expect(screen.getByText('mystery_token')).toBeInTheDocument()
  })

  it('hides the 最吃杆 callout when there is no top issue', () => {
    renderTrends({ stats: statsFixture({ diagnosis: {} }) })
    expect(screen.queryByText(/最吃杆/)).not.toBeInTheDocument()
  })

  it('clicking a 最近球局 row opens the round detail', async () => {
    const { onOpenRoundDetail } = renderTrends()

    const panel = screen.getByLabelText('最近球局')
    expect(within(panel).getByText('06-05')).toBeInTheDocument()
    expect(within(panel).getByText('+16')).toBeInTheDocument()

    await userEvent.click(within(panel).getByRole('button', { name: /棕榈泉乡村俱乐部/ }))
    expect(onOpenRoundDetail).toHaveBeenCalledWith('900010')
  })

  it('toggles the trend series between 杆数 and 差点', async () => {
    renderTrends()

    const chart = screen.getByLabelText('成绩走势')
    expect(within(chart).getByRole('button', { name: '杆数' })).toHaveAttribute('aria-pressed', 'true')
    expect(within(chart).getByRole('button', { name: '差点' })).toHaveAttribute('aria-pressed', 'false')

    await userEvent.click(within(chart).getByRole('button', { name: '差点' }))
    expect(within(chart).getByRole('button', { name: '差点' })).toHaveAttribute('aria-pressed', 'true')
  })
})
