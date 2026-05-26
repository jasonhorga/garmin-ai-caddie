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
  courses: [],
  holes: [],
  clubs: [],
  issues: [],
  dataQuality: [{ label: 'shots', state: 'partial', ready: 1, total: 3, refs: ['900003'] }],
  drillDown: {},
}

describe('DataQualityPage', () => {
  it('renders data quality state and affected refs', () => {
    render(<DataQualityPage data={statsFixture} onSelectRef={vi.fn()} />)

    expect(screen.getByRole('heading', { name: 'Data Quality' })).toBeInTheDocument()
    expect(screen.getByText('shots')).toBeInTheDocument()
    expect(screen.getByText('partial')).toHaveClass('quality-partial')
    expect(screen.getByText('1/3')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open source 900003' })).toBeInTheDocument()
  })

  it('renders an empty state when no quality findings exist', () => {
    render(<DataQualityPage data={{ ...statsFixture, dataQuality: [] }} />)

    expect(screen.getByText('No data quality findings yet')).toBeInTheDocument()
    expect(screen.getByText('Coverage findings will appear after history, shot, geometry, weather, or report data is loaded.')).toBeInTheDocument()
  })
})
