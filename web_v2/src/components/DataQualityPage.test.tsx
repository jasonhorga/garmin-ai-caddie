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
    expect(screen.getByText('partial')).toBeInTheDocument()
    expect(screen.getByText('1/3')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open source 900003' })).toBeInTheDocument()
  })
})
