import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { HistoryStatsResponse } from '../types'
import { ClubStats } from './ClubStats'

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
  clubs: [
    {
      club: '1D',
      sampleCount: 2,
      rawSampleCount: 4,
      validSampleCount: 2,
      invalidSampleCount: 1,
      outlierCount: 1,
      median: 240,
      p10: 225,
      p90: 255,
      dispersionRange: 30,
      consistency: 'volatile',
      distanceTrend: {
        sampleCount: 6,
        windowSize: 3,
        baselineMedian: 250,
        recentMedian: 234,
        deltaMedian: -16,
        direction: 'shorter',
        baselineShotRefs: ['900001:1:0'],
        recentShotRefs: ['900002:5:4'],
      },
      max: 270,
      confidence: 'low',
      shotRefs: ['900001:1:0', '900002:5:4'],
      validShotRefs: ['900001:1:0', '900002:5:4'],
      invalidShotRefs: ['900003:6:5'],
      outlierShotRefs: ['900004:7:6'],
      sampleQuality: {
        rawSampleCount: 4,
        validSampleCount: 2,
        invalidSampleCount: 1,
        outlierCount: 1,
        coverage: { ready: 2, total: 4, pct: 50 },
        confidence: 'medium',
        validShotRefs: ['900001:1:0', '900002:5:4'],
        invalidShotRefs: ['900003:6:5'],
        outlierShotRefs: ['900004:7:6'],
      },
    },
  ],
  issues: [],
  dataQuality: [
    { label: 'shots', state: 'partial', ready: 1, total: 2, refs: ['900002'] },
    { label: 'shot_rows', state: 'good', ready: 6, total: 6, refs: [] },
  ],
  drillDown: {},
}

describe('ClubStats', () => {
  it('renders club dispersion and confidence', () => {
    render(<ClubStats data={statsFixture} onSelectRef={vi.fn()} />)

    expect(screen.getByRole('heading', { name: 'Club Stats' })).toBeInTheDocument()
    expect(screen.getByText('1D')).toBeInTheDocument()
    expect(screen.getByText('2 samples')).toBeInTheDocument()
    expect(screen.getByText('median 240')).toBeInTheDocument()
    expect(screen.getByText('p10 225')).toBeInTheDocument()
    expect(screen.getByText('p90 255')).toBeInTheDocument()
    expect(screen.getByText('dispersion 30')).toBeInTheDocument()
    expect(screen.getByText('max 270')).toBeInTheDocument()
    expect(screen.getByText('valid 2/4')).toBeInTheDocument()
    expect(screen.getByText('invalid 1')).toHaveClass('quality-partial')
    expect(screen.getByText('outlier 1')).toHaveClass('quality-partial')
    expect(screen.getByText('sample medium')).toHaveClass('confidence-medium')
    expect(screen.getByText('volatile consistency')).toHaveClass('consistency-volatile')
    expect(screen.getByText('trend -16 shorter')).toHaveClass('trend-shorter')
    expect(screen.getByText('low confidence')).toHaveClass('confidence-low')
    expect(screen.getByText('shots partial 1/2')).toHaveClass('quality-partial')
    expect(screen.getByText('shot_rows good 6/6')).toHaveClass('quality-good')
    expect(screen.getByRole('button', { name: 'Open source 900001:1:0' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open source 900003:6:5' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open source 900004:7:6' })).toBeInTheDocument()
  })

  it('renders an empty state when no club samples exist', () => {
    render(<ClubStats data={{ ...statsFixture, clubs: [] }} />)

    expect(screen.getByText('No club samples yet')).toBeInTheDocument()
    expect(screen.getByText('Shot data or manual club input is required before the club model is useful.')).toBeInTheDocument()
  })
})
