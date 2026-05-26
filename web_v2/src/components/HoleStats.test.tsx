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
  courseDistribution: [],
  records: {},
  courses: [],
  holes: [
    {
      courseKey: 'black_knight',
      hole: 7,
      sampleCount: 2,
      averageToPar: 1.5,
      worstToPar: 3,
      geometryCoverage: 'missing',
      scoreDistribution: [
        { key: 'par', label: 'Par', className: 'par', count: 0, pct: 0, holeRefs: [] },
        { key: 'bogey', label: 'Bogey', className: 'bogey', count: 1, pct: 50, holeRefs: ['900001:7'] },
        { key: 'doubleOrWorse', label: 'Double+', className: 'double', count: 1, pct: 50, holeRefs: ['900002:7'] },
      ],
      repeatedIssues: [
        {
          issue: 'double_or_worse',
          count: 1,
          refs: ['900002:7'],
          sourceRefs: ['900002:7'],
          phase: 'Course Management',
          source: 'deterministic',
          confidence: 'high',
        },
      ],
      refs: ['900001:7', '900002:7'],
    },
  ],
  clubs: [],
  issues: [],
  dataQuality: [{ label: 'geometry', state: 'missing', ready: 0, partial: 0, total: 2, refs: ['900001:7', '900002:7'] }],
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
    expect(screen.getByText('geometry missing 0/2')).toHaveClass('quality-missing')
    expect(screen.getByText('geometry missing')).toHaveClass('quality-missing')
    expect(screen.getByText('Bogey')).toBeInTheDocument()
    expect(screen.getByText('Double+')).toBeInTheDocument()
    expect(screen.getAllByText('1')[0]).toBeInTheDocument()
    expect(screen.getAllByText('50%')).toHaveLength(2)
    expect(screen.getByText('double_or_worse')).toBeInTheDocument()
    expect(screen.getByText('Course Management')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open source 900001:7' })).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Open source 900002:7' })).toHaveLength(2)
  })

  it('renders an empty state when no hole aggregates exist', () => {
    render(<HoleStats data={{ ...statsFixture, holes: [] }} />)

    expect(screen.getByText('No hole stats yet')).toBeInTheDocument()
    expect(screen.getByText('Hole-level scorecards are required before repeated patterns can be shown.')).toBeInTheDocument()
  })
})
