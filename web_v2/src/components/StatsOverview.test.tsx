import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { HistoryStatsResponse } from '../types'
import { StatsOverview } from './StatsOverview'

const statsFixture: HistoryStatsResponse = {
  schema: 'ai-caddie-history-stats-v1',
  dataMode: 'fixture',
  summary: {
    totalRounds: 3,
    eighteenHoleRounds: 2,
    average18: 82,
    median18: 82,
    recent5Average: 82,
    recent10Average: 83,
    recent20Average: 84,
    bestScore: 77,
    worstScore: 95,
    shotCount: 6,
  },
  time: {
    byQuarter: [
      { key: '2026-Q2', roundCount: 2, average18: 82, bestScore: 77, roundIds: ['900001', '900002'] },
      { key: '2026-Q1', roundCount: 1, average18: null, bestScore: null, roundIds: ['900003'] },
    ],
    byMonth: [
      { key: '2026-05', roundCount: 1, average18: 77, bestScore: 77 },
      { key: '2026-04', roundCount: 1, average18: 87, bestScore: 87 },
    ],
    playFrequency: { totalMonths: 3, roundsPerMonth: 1, mostActiveMonth: { key: '2026-05', roundCount: 1 } },
    improvement: {
      direction: 'improving',
      confidence: 'high',
      windowSize: 3,
      baselineAverage18: 92,
      recentAverage18: 82,
      deltaAverage18: -10,
      strokesPerRoundTrend: -3.03,
      baselineRoundRefs: ['900004', '900005', '900006'],
      recentRoundRefs: ['900001', '900002', '900003'],
    },
  },
  scoring: {
    scoreBands: [
      { label: '70s', count: 1, roundIds: ['900001'] },
      { label: '80s', count: 1, roundIds: ['900002'] },
    ],
    phaseStats: [
      { phase: 'Approach', girPct: 42.2, missedGir: 26, holeRefs: ['900001:1'] },
      { phase: 'Putting', averagePutts: 2.1, threePutts: 5, holeRefs: ['900002:5'] },
    ],
  },
  courses: [
    {
      courseKey: 'black_knight',
      courseName: 'Black Knight B/C',
      roundCount: 2,
      average18: 82,
      roundIds: ['900001', '900002'],
    },
  ],
  holes: [],
  clubs: [],
  issues: [],
  dataQuality: [],
  drillDown: { roundIds: ['900001', '900002', '900003'] },
}

describe('StatsOverview', () => {
  it('renders summary, score bands, and recent months from history stats', () => {
    render(<StatsOverview data={statsFixture} />)

    expect(screen.getByRole('heading', { name: 'Statistics Overview' })).toBeInTheDocument()
    expect(screen.getByText('fixture mode')).toBeInTheDocument()
    expect(screen.getByText('Total rounds')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByText('18H average')).toBeInTheDocument()
    expect(screen.getAllByText('82').length).toBeGreaterThan(0)
    expect(screen.getByText('Best score')).toBeInTheDocument()
    expect(screen.getByText('77')).toBeInTheDocument()
    expect(screen.getByText('70s')).toBeInTheDocument()
    expect(screen.getAllByText('2026-05').length).toBeGreaterThan(0)
    expect(screen.getByText('avg 77')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Recent Form' })).toBeInTheDocument()
    expect(screen.getByText('Recent 5')).toBeInTheDocument()
    expect(screen.getByText('Recent 10')).toBeInTheDocument()
    expect(screen.getByText('Recent 20')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Improvement Pace' })).toBeInTheDocument()
    expect(screen.getByText('improving')).toBeInTheDocument()
    expect(screen.getByText('-10 strokes')).toBeInTheDocument()
    expect(screen.getByText('-3.03/round')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Quarter Trend' })).toBeInTheDocument()
    expect(screen.getByText('2026-Q2')).toBeInTheDocument()
    expect(screen.getAllByText('2 rounds').length).toBeGreaterThan(0)
    expect(screen.getByRole('heading', { name: 'Play Frequency' })).toBeInTheDocument()
    expect(screen.getByText('1 rounds/mo')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Phase Stats' })).toBeInTheDocument()
    expect(screen.getByText('Approach')).toBeInTheDocument()
    expect(screen.getByText('GIR 42.2%')).toBeInTheDocument()
    expect(screen.getByText('Putting')).toBeInTheDocument()
    expect(screen.getByText('avg putts 2.1')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Course Mix' })).toBeInTheDocument()
    expect(screen.getByText('Black Knight B/C')).toBeInTheDocument()
  })
})
