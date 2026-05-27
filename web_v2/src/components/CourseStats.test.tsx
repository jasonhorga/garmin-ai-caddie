import { render, screen, within } from '@testing-library/react'
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
  courseDistribution: [
    {
      courseKey: 'black_knight',
      courseName: 'Black Knight B',
      roundCount: 2,
      pct: 66.7,
      roundRefs: ['900001', '900002'],
      location: { latitude: 22.279, longitude: 114.162 },
    },
    {
      courseKey: 'bay_course',
      courseName: 'Bay Course',
      roundCount: 1,
      pct: 33.3,
      roundRefs: ['900003'],
      location: null,
    },
    {
      courseKey: 'island_club',
      courseName: 'Island Club',
      roundCount: 1,
      pct: 33.3,
      roundRefs: ['900004'],
      location: { latitude: 35.315, longitude: 130.21 },
    },
  ],
  records: {},
  courses: [
    {
      courseKey: 'black_knight',
      courseName: 'Black Knight B',
      roundCount: 2,
      average18: 82,
      bestScore: 77,
      worstScore: 87,
      recentForm: {
        baselineAverage18: 87,
        recentAverage18: 77,
        deltaAverage18: -10,
        direction: 'improving',
        baselineRoundRefs: ['900002'],
        recentRoundRefs: ['900001'],
      },
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
      },
      issueProfile: [
        {
          issue: 'double_or_worse',
          phase: 'Course Management',
          count: 5,
          affectedHoleCount: 5,
          samplePct: 13.9,
          estimatedStrokesRisk: 7.5,
          sourceRefs: ['900002:5', '900002:7'],
          confidence: 'medium',
        },
        {
          issue: 'fairway_missed_right',
          phase: 'Tee',
          count: 12,
          affectedHoleCount: 12,
          samplePct: 33.3,
          estimatedStrokesRisk: 3.6,
          sourceRefs: ['900001:1', '900001:4'],
          confidence: 'high',
        },
      ],
      toughestHoles: [
        {
          hole: 7,
          sampleCount: 2,
          averageToPar: 1.5,
          worstToPar: 2,
          issueScore: 4.5,
          holeRefs: ['900001:7', '900002:7'],
          confidence: 'medium',
        },
      ],
      geometryCoverage: 'missing',
      roundIds: ['900001', '900002'],
      coverage: { ready: 2, total: 3, pct: 66.7 },
      confidence: 'medium',
    },
  ],
  holes: [],
  clubs: [],
  issues: [],
  dataQuality: [{ label: 'geometry', state: 'missing', ready: 0, partial: 0, total: 2, refs: ['900001:1', '900002:1'] }],
  drillDown: {},
}

describe('CourseStats', () => {
  it('renders course aggregates and source round refs', () => {
    const onSelectRef = vi.fn()
    render(<CourseStats data={statsFixture} onSelectRef={onSelectRef} />)

    expect(screen.getByRole('heading', { name: 'Course Stats' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Black Knight B' })).toBeInTheDocument()
    expect(screen.getAllByText('2 rounds').length).toBeGreaterThan(0)
    expect(screen.getByText('avg 82')).toBeInTheDocument()
    expect(screen.getByText('best 77')).toBeInTheDocument()
    expect(screen.getByText('worst 87')).toBeInTheDocument()
    expect(screen.getByText('recent 77')).toBeInTheDocument()
    expect(screen.getByText('FIR 25%')).toBeInTheDocument()
    expect(screen.getByText('tee right 50%')).toHaveClass('tee-right')
    expect(screen.getByText('GIR 25%')).toBeInTheDocument()
    expect(screen.getByText('approach short 50%')).toHaveClass('approach-short')
    expect(screen.getByText('improving -10')).toHaveClass('trend-improving')
    expect(screen.getByText('geometry missing 0/2')).toHaveClass('quality-missing')
    expect(screen.getByText('geometry missing')).toHaveClass('quality-missing')
    expect(screen.getByText('coverage 2/3 66.7%')).toBeInTheDocument()
    expect(screen.getByText('medium confidence')).toBeInTheDocument()
    expect(screen.getByText('Course Issue Profile')).toBeInTheDocument()
    expect(screen.getByText('double_or_worse')).toBeInTheDocument()
    expect(screen.getByText('5 holes')).toBeInTheDocument()
    expect(screen.getByText('risk 7.5')).toBeInTheDocument()
    expect(screen.getByText('33.3% sample')).toBeInTheDocument()
    expect(screen.getByText('Toughest Holes')).toBeInTheDocument()
    expect(screen.getByText('Hole 7')).toBeInTheDocument()
    expect(screen.getByText('+1.5 avg')).toBeInTheDocument()
    expect(screen.getByText('risk 4.5')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Open source 900001' }).length).toBeGreaterThan(0)
    expect(screen.getAllByRole('button', { name: 'Open source 900002' }).length).toBeGreaterThan(0)
  })

  it('renders course distribution with location evidence and drill-down refs', () => {
    const onSelectRef = vi.fn()
    render(<CourseStats data={statsFixture} onSelectRef={onSelectRef} />)

    expect(screen.getByRole('heading', { name: 'Course Distribution' })).toBeInTheDocument()
    const distribution = screen.getByLabelText('Course distribution')
    const map = within(distribution).getByRole('img', { name: 'Course distribution geography' })
    expect(map).toHaveAttribute('data-plotted-count', '2')
    expect(within(distribution).getByText('2 plotted')).toBeInTheDocument()
    expect(within(distribution).getByText('1 missing location')).toHaveClass('quality-missing')

    const blackKnightPin = within(distribution).getByTestId('course-map-pin-black_knight')
    const islandClubPin = within(distribution).getByTestId('course-map-pin-island_club')
    expect(Number(blackKnightPin.getAttribute('cx'))).toBeLessThan(Number(islandClubPin.getAttribute('cx')))
    expect(Number(blackKnightPin.getAttribute('cy'))).toBeGreaterThan(Number(islandClubPin.getAttribute('cy')))

    expect(within(distribution).getByText('Black Knight B')).toBeInTheDocument()
    expect(within(distribution).getByText('66.7%')).toBeInTheDocument()
    expect(within(distribution).getByText('22.2790, 114.1620')).toBeInTheDocument()
    expect(within(distribution).getByText('Bay Course')).toBeInTheDocument()
    expect(within(distribution).getByText('location missing')).toHaveClass('quality-missing')
    expect(within(distribution).getAllByRole('button', { name: 'Open source 900003' }).length).toBeGreaterThan(0)
  })

  it('keeps coordinate-backed pins stable when the visible course set changes', () => {
    const { rerender } = render(<CourseStats data={statsFixture} />)
    const fullPin = screen.getByTestId('course-map-pin-black_knight')
    const fullPosition = {
      cx: fullPin.getAttribute('cx'),
      cy: fullPin.getAttribute('cy'),
    }

    rerender(
      <CourseStats
        data={{
          ...statsFixture,
          courseDistribution: [statsFixture.courseDistribution[0]],
        }}
      />,
    )

    const subsetPin = screen.getByTestId('course-map-pin-black_knight')
    expect(subsetPin).toHaveAttribute('cx', fullPosition.cx)
    expect(subsetPin).toHaveAttribute('cy', fullPosition.cy)
  })

  it('selects source refs for drill-down', async () => {
    const onSelectRef = vi.fn()
    render(<CourseStats data={statsFixture} onSelectRef={onSelectRef} />)

    await userEvent.click(screen.getAllByRole('button', { name: 'Open source 900001' })[0])

    expect(onSelectRef).toHaveBeenCalledWith('900001')
  })

  it('renders an empty state when no course aggregates exist', () => {
    render(<CourseStats data={{ ...statsFixture, courses: [] }} />)

    expect(screen.getByText('No course stats yet')).toBeInTheDocument()
    expect(screen.getByText('Sync Garmin rounds or switch to fixture mode to populate course distribution.')).toBeInTheDocument()
  })
})
