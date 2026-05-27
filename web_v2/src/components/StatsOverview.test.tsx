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
    byYear: [
      {
        key: '2026',
        year: '2026',
        roundCount: 3,
        eighteenHoleRounds: 2,
        nineHoleRounds: 1,
        average18: 82,
        median18: 82,
        bestScore: 77,
        worstScore: 95,
        roundIds: ['900001', '900002', '900003'],
        scoreBands: [
          { label: '70s', count: 1, pct: 50, className: 'eagle', roundRefs: ['900001'] },
          { label: '80s', count: 1, pct: 50, className: 'birdie', roundRefs: ['900002'] },
        ],
        scoreHistogram: [{ label: '80-84', count: 1, roundRefs: ['900002'] }],
        outcomeRows: [{ key: 'par', label: 'Par', className: 'par', count: 20, pct: 44.4, holeRefs: ['900003:3'] }],
      },
    ],
    byQuarter: [
      {
        key: '2026-Q2',
        roundCount: 2,
        eighteenHoleRounds: 1,
        nineHoleRounds: 1,
        average18: 82,
        median18: 82,
        bestScore: 77,
        worstScore: 87,
        roundIds: ['900001', '900002'],
        scoreBands: [{ label: '80s', count: 1, pct: 100, className: 'birdie', roundRefs: ['900002'] }],
        scoreHistogram: [{ label: '80-84', count: 1, roundRefs: ['900002'] }],
        outcomeRows: [{ key: 'birdie', label: 'Birdie', className: 'birdie', count: 4, pct: 8.9, holeRefs: ['900002:2'] }],
      },
      { key: '2026-Q1', roundCount: 1, average18: null, bestScore: null, roundIds: ['900003'] },
    ],
    byMonth: [
      {
        key: '2026-05',
        roundCount: 1,
        eighteenHoleRounds: 1,
        nineHoleRounds: 0,
        average18: 77,
        median18: 77,
        bestScore: 77,
        worstScore: 77,
        roundRefs: ['900001'],
        scoreBands: [{ label: '70s', count: 1, pct: 100, className: 'eagle', roundRefs: ['900001'] }],
        scoreHistogram: [{ label: '75-79', count: 1, roundRefs: ['900001'] }],
        outcomeRows: [{ key: 'eagleOrBetter', label: 'Eagle+', className: 'eagle', count: 1, pct: 2.2, holeRefs: ['900001:9'] }],
      },
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
    byPar: [
      {
        key: 'par3',
        label: 'Par 3',
        holeCount: 2,
        averageScore: 3.5,
        averageToPar: 0.5,
        parOrBetterPct: 50,
        bogeyOrWorsePct: 50,
        holeRefs: ['900001:2', '900001:4'],
      },
      {
        key: 'par4',
        label: 'Par 4',
        holeCount: 2,
        averageScore: 4.5,
        averageToPar: 0.5,
        parOrBetterPct: 50,
        bogeyOrWorsePct: 50,
        holeRefs: ['900001:1', '900001:3'],
      },
      {
        key: 'par5',
        label: 'Par 5',
        holeCount: 1,
        averageScore: 4,
        averageToPar: -1,
        parOrBetterPct: 100,
        bogeyOrWorsePct: 0,
        holeRefs: ['900001:5'],
      },
    ],
    teeDirection: {
      recorded: 4,
      total: 5,
      hit: 1,
      left: 1,
      right: 2,
      miss: 3,
      hitPct: 25,
      rightPct: 50,
      missPct: 75,
      dominantMiss: 'right',
      sourceRefs: ['900001:1', '900001:2', '900001:3', '900001:4'],
      hitRefs: ['900001:1'],
      rightRefs: ['900001:3', '900001:4'],
    },
    approachMiss: {
      recorded: 4,
      total: 5,
      gir: 1,
      missed: 3,
      short: 2,
      left: 1,
      girPct: 25,
      missPct: 75,
      shortPct: 50,
      dominantMiss: 'short',
      sourceRefs: ['900001:1', '900001:2', '900001:3', '900001:4'],
      girRefs: ['900001:1'],
      shortRefs: ['900001:2', '900001:4'],
    },
    phaseStats: [
      { phase: 'Approach', girPct: 42.2, missedGir: 26, holeRefs: ['900001:1'] },
      { phase: 'Putting', averagePutts: 2.1, threePutts: 5, holeRefs: ['900002:5'] },
    ],
    putting: {
      totalPutts: 94,
      holesWithPutts: 45,
      averagePutts: 2.1,
      threePutts: 5,
      holeRefs: ['900001:1', '900002:5'],
      threePuttRefs: ['900002:5'],
      correctedRefs: ['900001:7'],
      sourceRefs: ['900001:1', '900002:5'],
      coverage: { ready: 45, total: 45, pct: 100 },
      confidence: 'high',
    },
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
  playerProfile: {
    schema: 'ai-caddie-player-profile-v1',
    roundCount: 3,
    confidence: 'high',
    weaknesses: [
      {
        key: 'approach_short_miss',
        label: 'Approach short miss',
        phase: 'Approach',
        value: 50,
        unit: 'pct',
        severityScore: 1.5,
        sourceRefs: ['900001:2', '900001:4'],
      },
    ],
    caddieBiases: [
      {
        key: 'bias_against_approach_short',
        label: 'Bias against approach short',
        phase: 'Approach',
        value: 50,
        unit: 'pct',
        severityScore: 1.5,
        sourceRefs: ['900001:2'],
      },
    ],
    strengths: [
      {
        key: 'par5_scoring_strength',
        label: 'Par 5 scoring strength',
        phase: 'Scoring',
        value: -1,
        unit: 'to_par',
        severityScore: 1.5,
        sourceRefs: ['900001:5'],
      },
    ],
  },
  dataQuality: [
    { label: 'shots', state: 'partial', ready: 2, total: 3, sourceRefs: ['900003'] },
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
    const yearSummary = screen.getByLabelText('Year summary')
    expect(within(yearSummary).getByText('18H 2')).toBeInTheDocument()
    expect(within(yearSummary).getByText('9H 1')).toBeInTheDocument()
    expect(within(yearSummary).getByText('median 82')).toBeInTheDocument()
    expect(within(yearSummary).getByText('worst 95')).toBeInTheDocument()
    expect(within(yearSummary).getByText('70s 1')).toHaveClass('score-eagle')
    expect(within(yearSummary).getByText('80-84 1')).toBeInTheDocument()
    expect(within(yearSummary).getByText('Par 20')).toHaveClass('score-par')
    expect(screen.getByRole('heading', { name: 'Score Outcomes' })).toBeInTheDocument()
    expect(screen.getByText('Eagle+')).toBeInTheDocument()
    expect(screen.getByText('Birdie')).toBeInTheDocument()
    expect(screen.getByText('Par')).toBeInTheDocument()
    expect(screen.getByText('Bogey')).toBeInTheDocument()
    expect(screen.getByText('Double+')).toBeInTheDocument()
    expect(within(screen.getByLabelText('Score outcomes')).getByRole('button', { name: 'Open source 900001:9' })).toBeInTheDocument()
    expect(screen.getByText('70s')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Par Type Scoring' })).toBeInTheDocument()
    expect(screen.getByText('Par 3')).toBeInTheDocument()
    expect(screen.getAllByText('avg +0.5').length).toBeGreaterThan(0)
    expect(screen.getAllByText('par+ 50%').length).toBeGreaterThan(0)
    expect(screen.getAllByText('bogey+ 50%').length).toBeGreaterThan(0)
    expect(within(screen.getByLabelText('Par type scoring')).getByRole('button', { name: 'Open source 900001:2' })).toBeInTheDocument()
    expect(screen.getAllByText('2026-05').length).toBeGreaterThan(0)
    expect(screen.getByText('avg 77')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Recent Form' })).toBeInTheDocument()
    expect(screen.getByText('Recent 5')).toBeInTheDocument()
    expect(screen.getByText('Recent 10')).toBeInTheDocument()
    expect(screen.getByText('Recent 20')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Player Profile' })).toBeInTheDocument()
    expect(within(screen.getByLabelText('Player profile')).getByText('Approach short miss')).toBeInTheDocument()
    expect(within(screen.getByLabelText('Player profile')).getByText('Bias against approach short')).toBeInTheDocument()
    expect(within(screen.getByLabelText('Player profile')).getByText('Par 5 scoring strength')).toBeInTheDocument()
    expect(within(screen.getByLabelText('Player profile')).getAllByText('severity 1.5').length).toBeGreaterThan(0)
    expect(within(screen.getByLabelText('Player profile')).getAllByRole('button', { name: 'Open source 900001:2' }).length).toBeGreaterThan(0)
    expect(screen.getByRole('heading', { name: 'Improvement Pace' })).toBeInTheDocument()
    expect(screen.getByText('improving')).toBeInTheDocument()
    expect(screen.getByText('-10 strokes')).toBeInTheDocument()
    expect(screen.getByText('-3.03/round')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Quarter Trend' })).toBeInTheDocument()
    expect(screen.getByText('2026-Q2')).toBeInTheDocument()
    expect(screen.getAllByText('2 rounds').length).toBeGreaterThan(0)
    const quarterTrend = screen.getByLabelText('Quarter trend')
    expect(within(quarterTrend).getByText('median 82')).toBeInTheDocument()
    expect(within(quarterTrend).getByText('80s 1')).toHaveClass('score-birdie')
    expect(within(quarterTrend).getByText('Birdie 4')).toHaveClass('score-birdie')
    expect(screen.getByRole('heading', { name: 'Play Frequency' })).toBeInTheDocument()
    expect(screen.getByText('1 rounds/mo')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Phase Stats' })).toBeInTheDocument()
    expect(within(screen.getByLabelText('Phase stats')).getByText('Approach')).toBeInTheDocument()
    expect(screen.getByText('GIR 42.2%')).toBeInTheDocument()
    expect(within(screen.getByLabelText('Phase stats')).getByText('Putting')).toBeInTheDocument()
    expect(screen.getByText('avg putts 2.1')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Putting Detail' })).toBeInTheDocument()
    expect(screen.getByText('94 putts')).toBeInTheDocument()
    expect(screen.getByText('5 three-putts')).toBeInTheDocument()
    expect(screen.getByText('1 corrected')).toBeInTheDocument()
    expect(within(screen.getByLabelText('Putting detail')).getByText('coverage 45/45 100%')).toBeInTheDocument()
    expect(within(screen.getByLabelText('Putting detail')).getByText('high confidence')).toBeInTheDocument()
    expect(within(screen.getByLabelText('Putting detail')).getAllByRole('button', { name: 'Open source 900002:5' }).length).toBeGreaterThan(0)
    expect(within(screen.getByLabelText('Putting detail')).getByRole('button', { name: 'Open source 900001:7' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Tee Direction' })).toBeInTheDocument()
    expect(screen.getByText('FIR 25%')).toBeInTheDocument()
    expect(screen.getByText('miss 75%')).toBeInTheDocument()
    expect(screen.getByText('dominant right')).toHaveClass('tee-right')
    expect(within(screen.getByLabelText('Tee direction')).getByRole('button', { name: 'Open source 900001:3' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Approach Miss' })).toBeInTheDocument()
    expect(screen.getAllByText('GIR 25%').length).toBeGreaterThan(0)
    expect(screen.getByText('dominant short')).toHaveClass('approach-short')
    expect(within(screen.getByLabelText('Approach miss')).getByRole('button', { name: 'Open source 900001:2' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Course Mix' })).toBeInTheDocument()
    expect(screen.getAllByText('Black Knight B/C').length).toBeGreaterThan(0)
    expect(screen.getByRole('heading', { name: 'Course Distribution Map' })).toBeInTheDocument()
    const courseMap = screen.getByRole('img', { name: 'Course distribution geography' })
    expect(courseMap).toHaveAttribute('data-plotted-count', '1')
    expect(screen.getByTestId('course-map-pin-black_knight')).toHaveAttribute('cx', '241.2')
    expect(screen.getByText('66.7% / 2 rounds')).toBeInTheDocument()
    expect(screen.getByText('22.2790, 114.1620')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Data Coverage' })).toBeInTheDocument()
    expect(screen.getByText('shots partial 2/3')).toHaveClass('quality-partial')
    const shotsCoverageRow = screen.getByText('shots').closest('.stat-row')
    expect(shotsCoverageRow).not.toBeNull()
    expect(within(shotsCoverageRow as HTMLElement).getByRole('button', { name: 'Open source 900003' })).toBeInTheDocument()
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
