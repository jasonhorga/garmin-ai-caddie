import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { HistoryTimeline } from './HistoryTimeline'
import type { HistoryRoundsResponse } from '../types'

const payload: HistoryRoundsResponse = {
  schema: 'ai-caddie-history-rounds-v2',
  total: 2,
  groups: [
    {
      key: '2026-05',
      label: 'May 2026',
      count: 2,
      average18: 82,
      bestScore: 82,
      rounds: [
        {
          id: '1',
          date: '2026-05-20T08:00:00',
          courseName: 'Black Knight B',
          courseKey: 'c_black',
          holesCompleted: 18,
          score: 82,
          par: 72,
          toPar: 10,
          primaryIssue: null,
          badges: [{ label: 'shots', state: 'good', value: 'ready', reason: 'ready' }],
          scoreStrip: [{ hole: 1, par: 4, score: 4, toPar: 0, className: 'par' }],
        },
      ],
    },
  ],
  emptyState: null,
}

describe('HistoryTimeline', () => {
  it('renders month-grouped round cards and month summary stats', () => {
    render(<HistoryTimeline data={payload} onNavigate={() => undefined} />)

    expect(screen.getByText('History Timeline')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Overview' })).toBeEnabled()
    expect(screen.getByText('May 2026')).toBeInTheDocument()
    expect(screen.getByText('2 rounds')).toBeInTheDocument()
    expect(screen.getByText('avg 82')).toBeInTheDocument()
    expect(screen.getByText('best 82')).toBeInTheDocument()
    expect(screen.getByText('Black Knight B')).toBeInTheDocument()
  })

  it('renders a clear empty state', () => {
    render(
      <HistoryTimeline
        data={{
          schema: 'ai-caddie-history-rounds-v2',
          total: 0,
          groups: [],
          emptyState: {
            kind: 'no_rounds',
            title: 'No local Garmin rounds loaded',
            detail: 'The History timeline is ready, but this remote workspace has 0 rounds.',
          },
        }}
        onNavigate={() => undefined}
      />,
    )

    expect(screen.getByText('No local Garmin rounds loaded')).toBeInTheDocument()
    expect(screen.getByText(/this remote workspace has 0 rounds/i)).toBeInTheDocument()
  })
})
