import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { HistoryStatsResponse } from '../types'
import { CourseStats } from './CourseStats'

const statsFixture: HistoryStatsResponse = {
  schema: 'ai-caddie-history-stats-v1',
  dataMode: 'fixture',
  summary: {},
  time: {},
  scoring: {},
  courses: [
    {
      courseKey: 'black_knight',
      courseName: 'Black Knight B',
      roundCount: 2,
      average18: 82,
      bestScore: 77,
      worstScore: 87,
      roundIds: ['900001', '900002'],
    },
  ],
  holes: [],
  clubs: [],
  issues: [],
  dataQuality: [],
  drillDown: {},
}

describe('CourseStats', () => {
  it('renders course aggregates and source round refs', () => {
    render(<CourseStats data={statsFixture} />)

    expect(screen.getByRole('heading', { name: 'Course Stats' })).toBeInTheDocument()
    expect(screen.getByText('Black Knight B')).toBeInTheDocument()
    expect(screen.getByText('2 rounds')).toBeInTheDocument()
    expect(screen.getByText('avg 82')).toBeInTheDocument()
    expect(screen.getByText('best 77')).toBeInTheDocument()
    expect(screen.getByText('worst 87')).toBeInTheDocument()
    expect(screen.getByText('900001, 900002')).toBeInTheDocument()
  })
})
