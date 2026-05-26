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
  dataQuality: [{ label: 'reports', state: 'partial', ready: 1, total: 3, refs: ['900002', '900003'] }],
  drillDown: { roundRefs: ['900001', '900002'] },
}

const report: ReviewReportResponse = {
  schema: 'ai-caddie-review-report-v1',
  kind: 'trend',
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
  narrative: 'Recent scoring improved, but weather coverage is partial.',
  confidence: 'medium',
}

describe('ReportsPage', () => {
  it('renders trend and round report controls and displayed evidence', async () => {
    const onLoadTrend = vi.fn()
    const onGenerateTrend = vi.fn()
    const onLoadRound = vi.fn()
    const onGenerateRound = vi.fn()
    const onSelectRef = vi.fn()

    render(
      <ReportsPage
        stats={stats}
        reportState={{ status: 'ready', data: report }}
        onLoadTrend={onLoadTrend}
        onGenerateTrend={onGenerateTrend}
        onLoadRound={onLoadRound}
        onGenerateRound={onGenerateRound}
        onSelectRef={onSelectRef}
      />,
    )

    expect(screen.getByRole('heading', { name: 'Reports' })).toBeInTheDocument()
    expect(screen.getByText('reports partial 1/3')).toHaveClass('quality-partial')
    expect(screen.getByRole('option', { name: 'Recent 10' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Q 2026-Q2' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Year 2026' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: '900001' })).toBeInTheDocument()
    expect(screen.getByText('Recent scoring improved, but weather coverage is partial.')).toBeInTheDocument()
    expect(screen.getByText('summary_trend')).toBeInTheDocument()
    expect(screen.getByText('Black Knight B/C')).toBeInTheDocument()
    expect(screen.getByText('score 77')).toBeInTheDocument()
    expect(screen.getByText('toPar +5')).toBeInTheDocument()
    expect(screen.getByText('holeRef 900001:2')).toBeInTheDocument()
    expect(screen.getByText('toPar -1')).toBeInTheDocument()
    expect(screen.getByText('club 1D')).toBeInTheDocument()
    expect(screen.getByText('distance 238')).toBeInTheDocument()
    expect(screen.getByText('weather')).toBeInTheDocument()
    expect(screen.getByText('coverage 2/3 66.7%')).toBeInTheDocument()
    expect(screen.getByText('medium fact confidence')).toBeInTheDocument()
    expect(screen.getByText('coverage 1/3 33.3%')).toBeInTheDocument()
    expect(screen.getByText('low missing confidence')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Open source 900001' }).length).toBeGreaterThan(0)
    expect(screen.getAllByRole('button', { name: 'Open source 900002' }).length).toBeGreaterThan(0)
    expect(screen.getByText('medium confidence')).toBeInTheDocument()

    await userEvent.click(screen.getAllByRole('button', { name: 'Open source 900002' })[0])
    await userEvent.click(screen.getByRole('button', { name: 'Load trend report' }))
    await userEvent.click(screen.getByRole('button', { name: 'Generate trend report' }))
    await userEvent.click(screen.getByRole('button', { name: 'Load round report' }))
    await userEvent.click(screen.getByRole('button', { name: 'Generate round report' }))

    expect(onLoadTrend).toHaveBeenCalledWith('recent_10')
    expect(onGenerateTrend).toHaveBeenCalledWith('recent_10')
    expect(onSelectRef).toHaveBeenCalledWith('900002')
    expect(onLoadRound).toHaveBeenCalledWith('900001')
    expect(onGenerateRound).toHaveBeenCalledWith('900001')

    const facts = screen.getByLabelText('Report facts')
    expect(within(facts).getByText('summary')).toBeInTheDocument()
  })
})
