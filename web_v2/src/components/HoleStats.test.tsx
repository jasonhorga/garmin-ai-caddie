import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { HistoryStatsResponse } from '../types'
import { HoleStats } from './HoleStats'

const statsFixture: HistoryStatsResponse = {
  schema: 'ai-caddie-history-stats-v1',
  dataMode: 'fixture',
  summary: {},
  time: {},
  scoring: {},
  courses: [],
  holes: [
    {
      courseKey: 'black_knight',
      hole: 7,
      sampleCount: 2,
      averageToPar: 1.5,
      worstToPar: 3,
      geometryCoverage: 'missing',
      refs: ['900001:7', '900002:7'],
    },
  ],
  clubs: [],
  issues: [],
  dataQuality: [],
  drillDown: {},
}

describe('HoleStats', () => {
  it('renders hole aggregates and source refs', () => {
    render(<HoleStats data={statsFixture} onSelectRef={vi.fn()} />)

    expect(screen.getByRole('heading', { name: 'Hole Stats' })).toBeInTheDocument()
    expect(screen.getByText('black_knight')).toBeInTheDocument()
    expect(screen.getByText('Hole 7')).toBeInTheDocument()
    expect(screen.getByText('2 samples')).toBeInTheDocument()
    expect(screen.getByText('+1.5 avg')).toBeInTheDocument()
    expect(screen.getByText('+3 worst')).toBeInTheDocument()
    expect(screen.getByText('geometry missing')).toHaveClass('quality-missing')
    expect(screen.getByRole('button', { name: 'Open source 900001:7' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open source 900002:7' })).toBeInTheDocument()
  })

  it('renders an empty state when no hole aggregates exist', () => {
    render(<HoleStats data={{ ...statsFixture, holes: [] }} />)

    expect(screen.getByText('No hole stats yet')).toBeInTheDocument()
    expect(screen.getByText('Hole-level scorecards are required before repeated patterns can be shown.')).toBeInTheDocument()
  })
})
