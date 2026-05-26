import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { HistoryStatsResponse } from '../types'
import { CourseStats } from './CourseStats'

const statsFixture: HistoryStatsResponse = {
  schema: 'ai-caddie-history-stats-v1',
  dataMode: 'fixture',
  summary: {},
  time: {},
  scoring: {},
  courseDistribution: [{ courseKey: 'black_knight', roundCount: 2, pct: 100, roundRefs: ['900001', '900002'] }],
  records: {},
  courses: [
    {
      courseKey: 'black_knight',
      courseName: 'Black Knight B',
      roundCount: 2,
      average18: 82,
      bestScore: 77,
      worstScore: 87,
      geometryCoverage: 'missing',
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
    const onSelectRef = vi.fn()
    render(<CourseStats data={statsFixture} onSelectRef={onSelectRef} />)

    expect(screen.getByRole('heading', { name: 'Course Stats' })).toBeInTheDocument()
    expect(screen.getByText('Black Knight B')).toBeInTheDocument()
    expect(screen.getByText('2 rounds')).toBeInTheDocument()
    expect(screen.getByText('avg 82')).toBeInTheDocument()
    expect(screen.getByText('best 77')).toBeInTheDocument()
    expect(screen.getByText('worst 87')).toBeInTheDocument()
    expect(screen.getByText('geometry missing')).toHaveClass('quality-missing')
    expect(screen.getByRole('button', { name: 'Open source 900001' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open source 900002' })).toBeInTheDocument()
  })

  it('selects source refs for drill-down', async () => {
    const onSelectRef = vi.fn()
    render(<CourseStats data={statsFixture} onSelectRef={onSelectRef} />)

    await userEvent.click(screen.getByRole('button', { name: 'Open source 900001' }))

    expect(onSelectRef).toHaveBeenCalledWith('900001')
  })

  it('renders an empty state when no course aggregates exist', () => {
    render(<CourseStats data={{ ...statsFixture, courses: [] }} />)

    expect(screen.getByText('No course stats yet')).toBeInTheDocument()
    expect(screen.getByText('Sync Garmin rounds or switch to fixture mode to populate course distribution.')).toBeInTheDocument()
  })
})
