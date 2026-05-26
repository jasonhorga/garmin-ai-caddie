import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ReportsPage } from './ReportsPage'
import type { HistoryStatsResponse, ReviewReportResponse } from '../types'

const stats: HistoryStatsResponse = {
  schema: 'ai-caddie-history-stats-v1',
  dataMode: 'fixture',
  summary: { totalRounds: 3 },
  time: {
    byQuarter: [{ key: '2026-Q2', roundCount: 2, average18: 86 }],
    byYear: [{ key: '2026', roundCount: 3, average18: 86 }],
  },
  scoring: {},
  courseDistribution: [],
  records: {},
  courses: [],
  holes: [],
  clubs: [],
  issues: [],
  dataQuality: [],
  drillDown: { roundRefs: ['900001', '900002'] },
}

const report: ReviewReportResponse = {
  schema: 'ai-caddie-review-report-v1',
  kind: 'trend',
  provider: 'StaticProvider',
  model: 'static',
  factsUsed: [{ label: 'summary_trend', source: 'summary', value: { totalRounds: 3 } }],
  missingData: [{ label: 'weather', state: 'partial' }],
  narrative: 'Recent scoring improved, but weather coverage is partial.',
  confidence: 'medium',
}

describe('ReportsPage', () => {
  it('renders trend and round report controls and displayed evidence', async () => {
    const onLoadTrend = vi.fn()
    const onGenerateTrend = vi.fn()
    const onLoadRound = vi.fn()
    const onGenerateRound = vi.fn()

    render(
      <ReportsPage
        stats={stats}
        reportState={{ status: 'ready', data: report }}
        onLoadTrend={onLoadTrend}
        onGenerateTrend={onGenerateTrend}
        onLoadRound={onLoadRound}
        onGenerateRound={onGenerateRound}
      />,
    )

    expect(screen.getByRole('heading', { name: 'Reports' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Recent 10' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Q 2026-Q2' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Year 2026' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: '900001' })).toBeInTheDocument()
    expect(screen.getByText('Recent scoring improved, but weather coverage is partial.')).toBeInTheDocument()
    expect(screen.getByText('summary_trend')).toBeInTheDocument()
    expect(screen.getByText('weather')).toBeInTheDocument()
    expect(screen.getByText('medium confidence')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Load trend report' }))
    await userEvent.click(screen.getByRole('button', { name: 'Generate trend report' }))
    await userEvent.click(screen.getByRole('button', { name: 'Load round report' }))
    await userEvent.click(screen.getByRole('button', { name: 'Generate round report' }))

    expect(onLoadTrend).toHaveBeenCalledWith('recent_10')
    expect(onGenerateTrend).toHaveBeenCalledWith('recent_10')
    expect(onLoadRound).toHaveBeenCalledWith('900001')
    expect(onGenerateRound).toHaveBeenCalledWith('900001')

    const facts = screen.getByLabelText('Report facts')
    expect(within(facts).getByText('summary')).toBeInTheDocument()
  })
})
