import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
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
      { label: '70s', count: 0, pct: 0, className: 'eagle', roundRefs: [] },
      { label: '80s', count: 1, pct: 50, className: 'birdie', roundRefs: ['1'] },
      { label: '90s', count: 1, pct: 50, className: 'bogey', roundRefs: ['2'] },
      { label: '100+', count: 0, pct: 0, className: 'double', roundRefs: [] },
    ],
    histogram: [
      { label: '80-84', start: 80, count: 1, roundRefs: ['1'] },
      { label: '95-99', start: 95, count: 1, roundRefs: ['2'] },
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
    expect(screen.queryByText('AI Caddie v2')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Stats' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Quality' })).not.toBeInTheDocument()
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
            title: 'No local Garmin data loaded',
            detail:
              'The v2 UI is connected, but this remote workspace has 0 rounds and 0 shot rows. Sync Garmin data into data/scorecards and data/shots, or run the fetch workflow, then refresh.',
          },
        }}
      />,
    )

    expect(screen.getByText('No local Garmin data loaded')).toBeInTheDocument()
    expect(screen.getByText(/this remote workspace has 0 rounds and 0 shot rows/i)).toBeInTheDocument()
    expect(screen.getByText('No recent Garmin rounds')).toBeInTheDocument()
    expect(screen.queryByText('Black Knight B')).not.toBeInTheDocument()
  })

  it('opens recent rounds and distribution source refs', async () => {
    const onSelectRef = vi.fn()
    const onOpenRoundDetail = vi.fn()

    render(<HistoryOverview data={payload} onSelectRef={onSelectRef} onOpenRoundDetail={onOpenRoundDetail} />)

    await userEvent.click(screen.getByRole('button', { name: 'Open round Black Knight B, 2026-05-20, score 82, ref 1' }))
    await userEvent.click(screen.getAllByRole('button', { name: 'Open source 1' })[0])

    expect(onOpenRoundDetail).toHaveBeenCalledWith('1')
    expect(onSelectRef).toHaveBeenCalledWith('1')
    expect(onSelectRef).toHaveBeenCalledTimes(1)
  })
})
