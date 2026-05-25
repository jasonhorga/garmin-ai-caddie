import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { HistoryStatsResponse } from '../types'
import { IssueStats } from './IssueStats'

const statsFixture: HistoryStatsResponse = {
  schema: 'ai-caddie-history-stats-v1',
  dataMode: 'fixture',
  summary: {},
  time: {},
  scoring: {},
  courses: [],
  holes: [],
  clubs: [],
  issues: [{ issue: 'missing_shots', count: 2, refs: ['900002', '900003'] }],
  dataQuality: [],
  drillDown: {},
}

describe('IssueStats', () => {
  it('renders issue counts and source refs', () => {
    render(<IssueStats data={statsFixture} />)

    expect(screen.getByRole('heading', { name: 'Issue Stats' })).toBeInTheDocument()
    expect(screen.getByText('missing_shots')).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
    expect(screen.getByText('900002, 900003')).toBeInTheDocument()
  })
})
