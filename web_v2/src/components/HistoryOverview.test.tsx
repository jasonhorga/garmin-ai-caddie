import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { HistoryOverview } from './HistoryOverview'
import type { HistoryOverviewResponse } from '../types'

const payload: HistoryOverviewResponse = {
  schema: 'ai-caddie-history-overview-v2',
  metrics: {
    totalRounds: 2,
    eighteenHoleRounds: 2,
    nineHoleRounds: 0,
    courseCount: 2,
    shotCount: 42,
    average18: 89,
    recent10Average: 89,
    bestScore: 82,
  },
  recentRounds: [
    {
      id: '1',
      date: '2026-05-20',
      courseName: 'Black Knight B',
      courseKey: 'c_black',
      holesCompleted: 18,
      score: 82,
      par: 72,
      toPar: 10,
      primaryIssue: null,
      badges: [{ label: 'shots', state: 'good', value: 'ready', reason: 'ready' }],
      scoreStrip: [
        { hole: 1, par: 4, score: 4, toPar: 0, className: 'par' },
        { hole: 2, par: 5, score: 4, toPar: -1, className: 'birdie' },
      ],
    },
  ],
  distribution: {
    total: 2,
    average: 89,
    best: 82,
    worst: 96,
    families: [
      { label: '70s', count: 0, pct: 0, className: 'eagle' },
      { label: '80s', count: 1, pct: 50, className: 'birdie' },
      { label: '90s', count: 1, pct: 50, className: 'bogey' },
      { label: '100+', count: 0, pct: 0, className: 'double' },
    ],
    histogram: [
      { label: '80-84', start: 80, count: 1 },
      { label: '95-99', start: 95, count: 1 },
    ],
  },
  dataQuality: [{ label: 'shots', state: 'partial', value: '50%', reason: '1/2 scorecards have usable shot files' }],
  emptyState: null,
}

describe('HistoryOverview', () => {
  it('renders metrics, recent rounds, score strip, distribution, and quality chips', () => {
    const { container } = render(<HistoryOverview data={payload} />)

    expect(screen.getByText('History Overview')).toBeInTheDocument()
    expect(screen.getByText('Total rounds')).toBeInTheDocument()
    expect(screen.getAllByText('2').length).toBeGreaterThan(0)
    expect(screen.getByText('Black Knight B')).toBeInTheDocument()
    expect(screen.getByLabelText('Hole 2: birdie, par 5, score 4')).toBeInTheDocument()
    expect(screen.getByText('80s')).toBeInTheDocument()
    expect(screen.getAllByText('shots').length).toBeGreaterThan(0)
    expect(container.querySelectorAll('.topbar nav a')).toHaveLength(0)
    expect(screen.getByLabelText('shots: 50%, partial - 1/2 scorecards have usable shot files')).toBeInTheDocument()
  })

  it('renders the empty state without round cards', () => {
    render(
      <HistoryOverview
        data={{
          ...payload,
          metrics: { ...payload.metrics, totalRounds: 0 },
          recentRounds: [],
          emptyState: {
            kind: 'no_rounds',
            title: 'No Garmin rounds loaded',
            detail: 'Fetch Garmin scorecards locally, then refresh this view.',
          },
        }}
      />,
    )

    expect(screen.getByText('No Garmin rounds loaded')).toBeInTheDocument()
    expect(screen.getByText('No recent Garmin rounds')).toBeInTheDocument()
    expect(screen.queryByText('Black Knight B')).not.toBeInTheDocument()
  })
})
