import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { HistoryStatsResponse, RoundCard as RoundCardType } from '../types'
import { TrendsOverview } from './TrendsOverview'

function statsFixture(overrides: Partial<HistoryStatsResponse> = {}): HistoryStatsResponse {
  return {
    schema: 'ai-caddie-history-stats-v1',
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
    },
    courseDistribution: [],
    records: {},
    courses: [],
    holes: [],
    clubs: [],
    issues: [{ issue: 'tee_right', count: 6, refs: ['900001:3'] }],
    dataQuality: [],
    drillDown: {},
    ...overrides,
  }
}

function allStatsFixture(): HistoryStatsResponse {
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
    // 20 outcome holes: birdie 2→10%, par 7→35%, bogey 8→40%, double+ 3→15%, eagle 0→0%
    const birdie = within(panel).getByText('小鸟').closest('div') as HTMLElement
    expect(within(birdie).getByText('10%')).toBeInTheDocument()
    const par = within(panel).getByText('帕').closest('div') as HTMLElement
    expect(within(par).getByText('35%')).toBeInTheDocument()
    const bogey = within(panel).getByText('柏忌').closest('div') as HTMLElement
    expect(within(bogey).getByText('40%')).toBeInTheDocument()
    const double = within(panel).getByText('双+').closest('div') as HTMLElement
    expect(within(double).getByText('15%')).toBeInTheDocument()
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
        stats={statsFixture({ issues: [{ issue: 'mystery_token', count: 1 }] })}
        allStats={null}
        window="last10"
        onWindowChange={vi.fn()}
        recentRounds={[]}
      />,
    )
    expect(screen.getByText('mystery_token')).toBeInTheDocument()
  })

  it('hides the 最吃杆 callout when there are no issues', () => {
    renderTrends({ stats: statsFixture({ issues: [] }) })
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
