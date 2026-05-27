import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { HistoryStatsResponse } from '../types'
import { DataQualityPage } from './DataQualityPage'

const statsFixture: HistoryStatsResponse = {
  schema: 'ai-caddie-history-stats-v1',
  dataMode: 'fixture',
  summary: {},
  time: {},
  scoring: {},
  courseDistribution: [],
  records: {},
  courses: [],
  holes: [],
  clubs: [],
  issues: [],
  dataQuality: [
    {
      label: 'shots',
      state: 'partial',
      ready: 1,
      total: 3,
      refs: ['900003'],
      coverage: { ready: 1, total: 3, pct: 33.3 },
      confidence: 'low',
      reason: '1 of 3 scorecards have shot data',
      rowCount: 6,
    },
    { label: 'geometry', state: 'missing', ready: 0, total: 45, refs: ['900001:1'] },
    {
      label: 'reports',
      state: 'partial',
      ready: 1,
      total: 7,
      refs: ['900002', '900003'],
      roundReports: { ready: 1, total: 3, missingRefs: ['900002', '900003'] },
      trendReports: { ready: 0, total: 4, missingRefs: ['trend:recent_10', 'trend:year:2026'] },
    },
  ],
  drillDown: {},
}

describe('DataQualityPage', () => {
  it('renders data quality state and affected refs', () => {
    render(<DataQualityPage data={statsFixture} onSelectRef={vi.fn()} />)

    expect(screen.getByRole('heading', { name: 'Data Quality' })).toBeInTheDocument()
    expect(screen.getByText('shots')).toBeInTheDocument()
    expect(screen.getAllByText('partial')[0]).toHaveClass('quality-partial')
    expect(screen.getAllByText('1/3').length).toBeGreaterThan(0)
    expect(screen.getByText('coverage 1/3 33.3%')).toBeInTheDocument()
    expect(screen.getByText('low confidence')).toBeInTheDocument()
    expect(screen.getByText('1 of 3 scorecards have shot data')).toBeInTheDocument()
    expect(screen.getByText('rows 6')).toBeInTheDocument()
    expect(screen.getByText('geometry')).toBeInTheDocument()
    expect(screen.getByText('missing')).toHaveClass('quality-missing')
    expect(screen.getByText('0/45')).toBeInTheDocument()
    expect(screen.getByText('reports')).toBeInTheDocument()
    expect(screen.getByText('round reports 1/3')).toBeInTheDocument()
    expect(screen.getByText('trend reports 0/4')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Open source 900003' }).length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: 'Open source trend:recent_10' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open source 900001:1' })).toBeInTheDocument()
  })

  it('renders an empty state when no quality findings exist', () => {
    render(<DataQualityPage data={{ ...statsFixture, dataQuality: [] }} />)

    expect(screen.getByText('No data quality findings yet')).toBeInTheDocument()
    expect(screen.getByText('Coverage findings will appear after history, shot, geometry, weather, or report data is loaded.')).toBeInTheDocument()
  })
})
