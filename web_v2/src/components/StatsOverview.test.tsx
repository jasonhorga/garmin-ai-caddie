import { render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { HistoryStatsResponse } from '../types'
import { StatsOverview } from './StatsOverview'

const statsFixture: HistoryStatsResponse = {
  schema: 'ai-caddie-history-stats-v1',
  dataMode: 'fixture',
  summary: {
    totalRounds: 3,
    eighteenHoleRounds: 2,
    nineHoleRounds: 1,
    mergedRounds: 1,
    courseCount: 2,
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
    byYear: [{ key: '2026', year: '2026', roundCount: 3, average18: 82, bestScore: 77, roundIds: ['900001', '900002', '900003'] }],
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
    outcomes: {
      eagleOrBetter: 1,
      birdie: 4,
      par: 20,
      bogey: 16,
      doubleOrWorse: 4,
      parOrBetter: 25,
      bogeyOrWorse: 20,
    },
    outcomeRows: [
      { key: 'eagleOrBetter', label: 'Eagle+', className: 'eagle', count: 1, pct: 2.2, holeRefs: ['900001:9'] },
      { key: 'birdie', label: 'Birdie', className: 'birdie', count: 4, pct: 8.9, holeRefs: ['900002:2'] },
      { key: 'par', label: 'Par', className: 'par', count: 20, pct: 44.4, holeRefs: ['900003:3'] },
      { key: 'bogey', label: 'Bogey', className: 'bogey', count: 16, pct: 35.6, holeRefs: ['900004:4'] },
      { key: 'doubleOrWorse', label: 'Double+', className: 'double', count: 4, pct: 8.9, holeRefs: ['900005:5'] },
    ],
    phaseStats: [
      { phase: 'Approach', girPct: 42.2, missedGir: 26, holeRefs: ['900001:1'] },
      { phase: 'Putting', averagePutts: 2.1, threePutts: 5, holeRefs: ['900002:5'] },
    ],
  },
  courseDistribution: [
    {
      courseKey: 'black_knight',
      courseName: 'Black Knight B/C',
      roundCount: 2,
      pct: 66.7,
      roundRefs: ['900001', '900002'],
      location: { latitude: 22.279, longitude: 114.162 },
    },
  ],
  records: {
    best18: { score: 77, toPar: 5, roundRef: '900001', sourceRefs: ['900001'], coverage: { ready: 1, total: 1, pct: 100 }, confidence: 'low' },
    worst18: { score: 95, toPar: 23, roundRef: '900002', sourceRefs: ['900002'], coverage: { ready: 1, total: 1, pct: 100 }, confidence: 'low' },
    bestNine: { score: 38, toPar: 2, roundRef: '900003', sourceRefs: ['900003'], coverage: { ready: 1, total: 1, pct: 100 }, confidence: 'low' },
    mostPlayedCourse: { courseKey: 'black_knight', courseName: 'Black Knight B/C', roundCount: 2, roundRefs: ['900001', '900002'] },
    longestShots: [{ club: '1D', distance: 238, shotRef: '900001:1:0', sourceRefs: ['900001:1:0'], coverage: { ready: 1, total: 1, pct: 100 }, confidence: 'low' }],
    bestHoleOutcomes: [{ holeRef: '900003:2', toPar: -1, score: 4, par: 5, sourceRefs: ['900003:2'], coverage: { ready: 1, total: 1, pct: 100 }, confidence: 'low' }],
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
  dataQuality: [
    { label: 'shots', state: 'partial', ready: 2, total: 3, refs: ['900003'] },
    { label: 'putts', state: 'good', ready: 45, total: 45, refs: [] },
    { label: 'club_samples', state: 'partial', ready: 1, total: 5, refs: ['900001:2:2'] },
    { label: 'annotations', state: 'good', ready: 2, total: 2, refs: ['ann-1', 'ann-2'] },
    { label: 'corrections', state: 'good', ready: 1, total: 2, refs: ['corr-1'] },
    { label: 'reports', state: 'partial', ready: 1, total: 3, refs: ['900002', '900003'] },
    { label: 'weather', state: 'missing', ready: 0, total: 45, refs: [] },
  ],
  drillDown: { roundIds: ['900001', '900002', '900003'] },
}

describe('StatsOverview', () => {
  it('renders summary, score bands, and recent months from history stats', () => {
    render(<StatsOverview data={statsFixture} onSelectRef={vi.fn()} />)

    expect(screen.getByRole('heading', { name: 'Statistics Overview' })).toBeInTheDocument()
    expect(screen.getByText('fixture mode')).toBeInTheDocument()
    expect(screen.getByText('Total rounds')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByText('18H average')).toBeInTheDocument()
    expect(screen.getAllByText('82').length).toBeGreaterThan(0)
    expect(screen.getByText('Best score')).toBeInTheDocument()
    expect(screen.getByText('77')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Round Format' })).toBeInTheDocument()
    expect(screen.getByText('18-hole rounds')).toBeInTheDocument()
    expect(screen.getByText('9-hole rounds')).toBeInTheDocument()
    expect(screen.getByText('Merged same-day rounds')).toBeInTheDocument()
    expect(screen.getByText('Courses played')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Year Summary' })).toBeInTheDocument()
    expect(screen.getByText('2026')).toBeInTheDocument()
    expect(screen.getAllByText('3 rounds').length).toBeGreaterThan(0)
    expect(screen.getByRole('heading', { name: 'Score Outcomes' })).toBeInTheDocument()
    expect(screen.getByText('Eagle+')).toBeInTheDocument()
    expect(screen.getByText('Birdie')).toBeInTheDocument()
    expect(screen.getByText('Par')).toBeInTheDocument()
    expect(screen.getByText('Bogey')).toBeInTheDocument()
    expect(screen.getByText('Double+')).toBeInTheDocument()
    expect(within(screen.getByLabelText('Score outcomes')).getByRole('button', { name: 'Open source 900001:9' })).toBeInTheDocument()
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
    expect(screen.getAllByText('Black Knight B/C').length).toBeGreaterThan(0)
    expect(screen.getByRole('heading', { name: 'Course Distribution Map' })).toBeInTheDocument()
    expect(screen.getByText('66.7% / 2 rounds')).toBeInTheDocument()
    expect(screen.getByText('22.279, 114.162')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Data Coverage' })).toBeInTheDocument()
    expect(screen.getByText('shots partial 2/3')).toHaveClass('quality-partial')
    expect(screen.getByText('putts good 45/45')).toHaveClass('quality-good')
    expect(screen.getByText('club_samples partial 1/5')).toHaveClass('quality-partial')
    expect(screen.getByText('annotations good 2/2')).toHaveClass('quality-good')
    expect(screen.getByText('corrections good 1/2')).toHaveClass('quality-good')
    expect(screen.getByText('reports partial 1/3')).toHaveClass('quality-partial')
    expect(screen.getByText('weather missing 0/45')).toHaveClass('quality-missing')
    expect(screen.getByRole('heading', { name: 'Record Book' })).toBeInTheDocument()
    expect(screen.getByText('Best 18')).toBeInTheDocument()
    expect(screen.getByText('77 / +5')).toBeInTheDocument()
    expect(screen.getByText('Best 9')).toBeInTheDocument()
    expect(screen.getByText('38 / +2')).toBeInTheDocument()
    expect(screen.getByText('Longest shot')).toBeInTheDocument()
    expect(screen.getByText('1D 238m')).toBeInTheDocument()
    const recordBook = screen.getByLabelText('Record book')
    expect(within(recordBook).getAllByText('coverage 1/1 100%').length).toBeGreaterThan(0)
    expect(within(recordBook).getAllByText('low confidence').length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: 'Open source 900001:1:0' })).toBeInTheDocument()
  })
})
