import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { HistoryStatsResponse } from '../types'
import { StatsOverview } from './StatsOverview'

const statsFixture: HistoryStatsResponse = {
  schema: 'ai-caddie-history-stats-v1',
  dataMode: 'fixture',
  summary: {
    totalRounds: 3,
    eighteenHoleRounds: 2,
    average18: 82,
    bestScore: 77,
    shotCount: 6,
  },
  time: {
    byMonth: [
      { key: '2026-05', roundCount: 1, average18: 77, bestScore: 77 },
      { key: '2026-04', roundCount: 1, average18: 87, bestScore: 87 },
    ],
  },
  scoring: {
    scoreBands: [
      { label: '70s', count: 1, roundIds: ['900001'] },
      { label: '80s', count: 1, roundIds: ['900002'] },
    ],
  },
  courses: [],
  holes: [],
  clubs: [],
  issues: [],
  dataQuality: [],
  drillDown: { roundIds: ['900001', '900002', '900003'] },
}

describe('StatsOverview', () => {
  it('renders summary, score bands, and recent months from history stats', () => {
    render(<StatsOverview data={statsFixture} />)

    expect(screen.getByRole('heading', { name: 'Statistics Overview' })).toBeInTheDocument()
    expect(screen.getByText('fixture mode')).toBeInTheDocument()
    expect(screen.getByText('Total rounds')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByText('18H average')).toBeInTheDocument()
    expect(screen.getByText('82')).toBeInTheDocument()
    expect(screen.getByText('Best score')).toBeInTheDocument()
    expect(screen.getByText('77')).toBeInTheDocument()
    expect(screen.getByText('70s')).toBeInTheDocument()
    expect(screen.getByText('2026-05')).toBeInTheDocument()
    expect(screen.getByText('avg 77')).toBeInTheDocument()
  })
})
