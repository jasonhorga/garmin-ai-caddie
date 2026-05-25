import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { HistoryStatsResponse } from '../types'
import { ClubStats } from './ClubStats'

const statsFixture: HistoryStatsResponse = {
  schema: 'ai-caddie-history-stats-v1',
  dataMode: 'fixture',
  summary: {},
  time: {},
  scoring: {},
  courses: [],
  holes: [],
  clubs: [
    {
      club: '1D',
      sampleCount: 2,
      median: 240,
      p10: 225,
      p90: 255,
      max: 270,
      confidence: 'medium',
      roundIds: ['900001', '900002'],
    },
  ],
  issues: [],
  dataQuality: [],
  drillDown: {},
}

describe('ClubStats', () => {
  it('renders club dispersion and confidence', () => {
    render(<ClubStats data={statsFixture} />)

    expect(screen.getByRole('heading', { name: 'Club Stats' })).toBeInTheDocument()
    expect(screen.getByText('1D')).toBeInTheDocument()
    expect(screen.getByText('2 samples')).toBeInTheDocument()
    expect(screen.getByText('median 240')).toBeInTheDocument()
    expect(screen.getByText('p10 225')).toBeInTheDocument()
    expect(screen.getByText('p90 255')).toBeInTheDocument()
    expect(screen.getByText('max 270')).toBeInTheDocument()
    expect(screen.getByText('medium confidence')).toBeInTheDocument()
  })
})
