import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { HistoryStatsResponse, MobileCourseOptionsResponse } from '../types'
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
      averageDifferential: 9.8,
      bestDifferential: 6.1,
      difficultyAdjusted: {
        eligibleRoundCount: 3,
        ratedRoundCount: 2,
        averageDifferential: 9.8,
        medianDifferential: 9.8,
        bestDifferential: 6.1,
        worstDifferential: 13.5,
        recent5AverageDifferential: 8.2,
        recent10AverageDifferential: 9.8,
        roundRefs: ['900001', '900002'],
        missingRoundRefs: ['900003'],
        coverage: { ready: 2, total: 3, pct: 66.7 },
        confidence: 'medium',
      },
      recentForm: {
        baselineAverage18: 87,
        recentAverage18: 77,
        deltaAverage18: -10,
        direction: 'improving',
        baselineAverageDifferential: 13.5,
        recentAverageDifferential: 8.2,
        deltaAverageDifferential: -5.3,
        differentialPerRoundTrend: -1.7,
        differentialDirection: 'improving',
        difficultyAdjustedCoverage: { ready: 2, total: 3, pct: 66.7 },
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

const courseOptionsFixture: MobileCourseOptionsResponse = {
  schema: 'ai-caddie-mobile-course-options-v1',
  dataMode: 'fixture',
  total: 1,
  courses: [
    {
      globalId: 31795,
      courseKey: 'black_knight',
      name: 'Black Knight B/C',
      roundCount: 2,
      holes: 18,
      geometryCoverage: 'missing',
      sourceRefs: ['900001', '900002'],
    },
  ],
  emptyState: null,
  generatedAt: '2026-06-01T08:00:00Z',
}

describe('CourseStats', () => {
  it('renders course aggregates and source round refs', () => {
    const onSelectRef = vi.fn()
    render(<CourseStats data={statsFixture} onSelectRef={onSelectRef} />)

    expect(screen.getByRole('heading', { name: '球场表现' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Black Knight B' })).toBeInTheDocument()
    const facts = screen.getByLabelText('Black Knight B 数据')
    expect(within(facts).getByText('2 场次')).toBeInTheDocument()
    expect(within(facts).getByText('平均 82')).toBeInTheDocument()
    expect(within(facts).getByText('最好 77')).toBeInTheDocument()
    expect(within(facts).getByText('最差 87')).toBeInTheDocument()
    expect(within(facts).getByText('均差 9.8')).toBeInTheDocument()
    expect(within(facts).getByText('最好差 6.1')).toBeInTheDocument()
    expect(screen.getByText('近期 77')).toBeInTheDocument()
    expect(screen.getByText('FIR 25%')).toBeInTheDocument()
    expect(screen.getByText('开球 right 50%')).toHaveClass('tee-right')
    expect(screen.getByText('GIR 25%')).toBeInTheDocument()
    expect(screen.getByText('攻果岭 short 50%')).toHaveClass('approach-short')
    expect(screen.getByText('进步中 -10')).toHaveClass('trend-improving')
    expect(screen.getByText('差分 进步中 -5.3')).toHaveClass('trend-improving')
    expect(screen.getByText('几何 缺失')).toHaveClass('quality-missing')
    expect(screen.getAllByText('coverage 2/3 66.7%').length).toBeGreaterThan(0)
    expect(screen.getByText('medium confidence')).toBeInTheDocument()
    expect(screen.getByText('难度调整')).toBeInTheDocument()
    const difficultyAdjusted = screen.getByLabelText('Black Knight B 难度调整')
    expect(within(difficultyAdjusted).getByText('评级/坡度覆盖')).toBeInTheDocument()
    expect(within(difficultyAdjusted).getByText('2 / 3 场次')).toBeInTheDocument()
    expect(within(difficultyAdjusted).getByText('覆盖 2/3 66.7%')).toBeInTheDocument()
    expect(within(difficultyAdjusted).getByText('缺失评级/坡度')).toBeInTheDocument()
    expect(within(difficultyAdjusted).getByText('1 场次')).toBeInTheDocument()
    expect(within(difficultyAdjusted).getByRole('button', { name: 'Open source 900003' })).toBeInTheDocument()
    expect(screen.getByText('球场问题分布')).toBeInTheDocument()
    expect(screen.getByText('double_or_worse')).toBeInTheDocument()
    expect(screen.getByText('5 洞')).toBeInTheDocument()
    expect(screen.getByText('风险 7.5')).toBeInTheDocument()
    expect(screen.getByText('33.3% 样本')).toBeInTheDocument()
    expect(screen.getByText('最难球洞')).toBeInTheDocument()
    expect(screen.getByText('第7洞')).toBeInTheDocument()
    expect(screen.getByText('+1.5 均')).toBeInTheDocument()
    expect(screen.getByText('风险 4.5')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Open source 900001' }).length).toBeGreaterThan(0)
    expect(screen.getAllByRole('button', { name: 'Open source 900002' }).length).toBeGreaterThan(0)
  })

  it('renders course distribution with location evidence and drill-down refs', () => {
    const onSelectRef = vi.fn()
    render(<CourseStats data={statsFixture} onSelectRef={onSelectRef} />)

    expect(screen.getByRole('heading', { name: '球场分布' })).toBeInTheDocument()
    const distribution = screen.getByLabelText('球场分布')
    const map = within(distribution).getByRole('img', { name: '球场地理分布' })
    expect(map).toHaveAttribute('data-plotted-count', '2')
    expect(within(distribution).getByText('2 已标注')).toBeInTheDocument()
    expect(within(distribution).getByText('1 无位置信息')).toHaveClass('quality-missing')

    const blackKnightPin = within(distribution).getByTestId('course-map-pin-black_knight')
    const islandClubPin = within(distribution).getByTestId('course-map-pin-island_club')
    expect(Number(blackKnightPin.getAttribute('cx'))).toBeLessThan(Number(islandClubPin.getAttribute('cx')))
    expect(Number(blackKnightPin.getAttribute('cy'))).toBeGreaterThan(Number(islandClubPin.getAttribute('cy')))

    expect(within(distribution).getByText('Black Knight B')).toBeInTheDocument()
    expect(within(distribution).getByText('66.7%')).toBeInTheDocument()
    expect(within(distribution).getByText('22.2790, 114.1620')).toBeInTheDocument()
    expect(within(distribution).getByText('Bay Course')).toBeInTheDocument()
    expect(within(distribution).getByText('无位置信息')).toHaveClass('quality-missing')
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

    expect(screen.getByText('暂无球场表现数据')).toBeInTheDocument()
    expect(screen.getByText('同步 Garmin 球局或切换到 fixture 模式以填充球场分布。')).toBeInTheDocument()
  })

  it('shows 去备战 button when courseOptions maps the courseKey to a globalId', async () => {
    const onPrepCourse = vi.fn()
    render(<CourseStats data={statsFixture} courseOptions={courseOptionsFixture} onPrepCourse={onPrepCourse} />)

    const prepBtn = screen.getByRole('button', { name: '去备战 Black Knight B' })
    expect(prepBtn).toBeInTheDocument()

    await userEvent.click(prepBtn)

    expect(onPrepCourse).toHaveBeenCalledWith(31795)
  })

  it('omits 去备战 button when no courseOptions mapping exists for the course', () => {
    const onPrepCourse = vi.fn()
    // courseOptions contains a different courseKey → no match for black_knight
    const differentOptions: MobileCourseOptionsResponse = {
      ...courseOptionsFixture,
      courses: [{ ...courseOptionsFixture.courses[0], courseKey: 'other_course' }],
    }
    render(<CourseStats data={statsFixture} courseOptions={differentOptions} onPrepCourse={onPrepCourse} />)

    expect(screen.queryByRole('button', { name: /去备战/ })).not.toBeInTheDocument()
  })

  it('omits 去备战 button when courseOptions is not provided', () => {
    render(<CourseStats data={statsFixture} />)

    expect(screen.queryByRole('button', { name: /去备战/ })).not.toBeInTheDocument()
  })
})
