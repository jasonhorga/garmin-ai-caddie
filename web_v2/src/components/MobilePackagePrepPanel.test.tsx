import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { LiveRoundPackageResponse } from '../types'
import { MobilePackagePrepPanel } from './MobilePackagePrepPanel'

const packageFixture: LiveRoundPackageResponse = {
  schema: 'ai-caddie-live-round-package-v1',
  roundId: 'live-black-knight',
  dataMode: 'fixture',
  sourceCoverage: {
    state: 'ready',
    dataMode: 'fixture',
    requestedRoundId: 'live-black-knight',
    selectedRoundId: '900001',
    roundFound: true,
    availableRoundCount: 3,
    holeCount: 18,
    clubProfileCount: 12,
    preparationMode: 'course',
    requestedCourseGlobalId: 31795,
    courseFound: true,
  },
  missingData: [
    { label: 'geometry', reason: '12/18 holes have ready geometry for offline caddie evidence' },
    {
      label: 'weather',
      reason: '2/18 holes have cached weather snapshots for prepared hole time',
      coverage: { ready: 2, total: 18, pct: 11.1 },
      sourceRefs: ['live-black-knight:3'],
    },
  ],
  playerProfile: { playerId: 'player-1', displayName: 'Test Player', handedness: 'right' },
  course: { globalId: 31795, name: 'Fixture Links', teeBox: 'blue' },
  holes: [{ number: 1, par: 4, yards: 410, geometryCoverage: 'ready' }],
  geometryCoverage: { state: 'partial', readyHoles: 12, totalHoles: 18 },
  readinessChecks: [
    {
      label: 'source',
      state: 'ready',
      ready: 1,
      total: 1,
      reason: 'round source is available for offline package preparation',
      sourceRefs: ['live-black-knight'],
    },
    {
      label: 'geometry',
      state: 'degraded',
      ready: 12,
      total: 18,
      reason: '12/18 holes have ready geometry for offline caddie evidence',
      sourceRefs: [],
    },
    {
      label: 'weather',
      state: 'degraded',
      ready: 2,
      total: 18,
      reason: '2/18 holes have cached weather snapshots for prepared hole time',
      sourceRefs: ['live-black-knight:1', 'live-black-knight:2'],
    },
  ],
  caddieContextSeeds: [
    {
      hole: 1,
      sourceRef: 'live-black-knight:1',
      selectedOfflineOptionId: 'stock',
      offlineOptions: [
        {
          id: 'safe',
          label: 'Safe',
          clubName: '9I',
          carryM: 132,
          p10M: 120,
          p90M: 140,
          sampleSize: 24,
          confidence: 'high',
          coverage: { ready: 24, total: 24, pct: 100 },
          riskScore: 1,
          source: 'offline_package_seed',
          sourceRefs: ['live-black-knight:1'],
          sampleRefs: ['live-black-knight:1:2'],
          missingData: [],
        },
        {
          id: 'stock',
          label: 'Stock',
          clubName: '8I',
          carryM: 144,
          p10M: 132,
          p90M: 153,
          sampleSize: 24,
          confidence: 'high',
          coverage: { ready: 24, total: 24, pct: 100 },
          riskScore: 3,
          source: 'offline_package_seed',
          sourceRefs: ['live-black-knight:1'],
          sampleRefs: ['live-black-knight:1:1'],
          missingData: [],
        },
        {
          id: 'attack',
          label: 'Attack',
          clubName: '7I',
          carryM: 156,
          p10M: 142,
          p90M: 168,
          sampleSize: 4,
          confidence: 'medium',
          coverage: { ready: 4, total: 10, pct: 40 },
          riskScore: 5,
          source: 'offline_package_seed',
          sourceRefs: ['live-black-knight:1'],
          sampleRefs: ['live-black-knight:1:3'],
          missingData: [{ label: 'club_profile_sample' }],
        },
      ],
      missingData: [{ label: 'current_location' }],
    },
  ],
  weatherSnapshot: {
    schema: 'ai-caddie-weather-snapshot-v1',
    state: 'missing',
    source: 'missing',
    confidence: 'low',
    coverage: { ready: 2, total: 18, pct: 11.1 },
    holeCoverage: [
      { hole: 1, sourceRef: 'live-black-knight:1', state: 'ready', capturedAt: '2026-05-25T08:00:00Z' },
      { hole: 2, sourceRef: 'live-black-knight:2', state: 'ready', capturedAt: '2026-05-25T08:00:00Z' },
    ],
    missingData: [{ label: 'weather_values', reason: 'not cached' }],
  },
  clubProfiles: [{ clubName: '8I', sampleSize: 24, median_m: 144, p10_m: 132, p90_m: 153 }],
  caddieDecisionEndpoint: '/api/v2/caddie/decision',
  offlinePackageStatus: {
    state: 'degraded',
    preparedAt: '2026-05-25T08:00:00Z',
    expiresAt: '2026-05-26T08:00:00Z',
    cachePolicy: { staleAfterHours: 6, expiresAfterHours: 24 },
  },
  eventCursor: { serverSequence: 0, pendingEventCount: 0 },
  recentHistory: {
    course: { courseKey: 'fixture-links', roundCount: 3, recentScores: [81, 84, 83] },
    rounds: [],
    holes: [],
  },
  cachedCaddieRules: {
    decisionContract: 'ai-caddie-decision-v2',
    offlineCapable: true,
    requiredInputs: ['currentLocation', 'hole', 'clubProfiles'],
    degradeWhenMissing: ['geometry', 'weather', 'recentHistory'],
  },
  generatedAt: '2026-05-25T08:00:00Z',
}

describe('MobilePackagePrepPanel', () => {
  it('prepares a round package from round id and captured time', async () => {
    const onPrepareRound = vi.fn()

    render(
      <MobilePackagePrepPanel
        state={{ status: 'idle' }}
        onPrepareRound={onPrepareRound}
        onPrepareCourse={vi.fn()}
      />,
    )

    await userEvent.clear(screen.getByLabelText('Round ID'))
    await userEvent.type(screen.getByLabelText('Round ID'), 'round:1')
    await userEvent.type(screen.getByLabelText('Captured time'), '2026-05-25T08:00:00Z')
    await userEvent.click(screen.getByRole('button', { name: 'Prepare package' }))

    expect(onPrepareRound).toHaveBeenCalledWith('round:1', { capturedAt: '2026-05-25T08:00:00Z' })
  })

  it('prepares a course package before the Garmin round exists', async () => {
    const onPrepareCourse = vi.fn()

    render(
      <MobilePackagePrepPanel
        state={{ status: 'idle' }}
        onPrepareRound={vi.fn()}
        onPrepareCourse={onPrepareCourse}
      />,
    )

    await userEvent.click(screen.getByRole('radio', { name: 'Course' }))
    await userEvent.clear(screen.getByLabelText('Course global ID'))
    await userEvent.type(screen.getByLabelText('Course global ID'), '31795')
    await userEvent.type(screen.getByLabelText('Live round ID'), 'live-black-knight')
    await userEvent.type(screen.getByLabelText('Tee box'), 'blue')
    await userEvent.click(screen.getByRole('button', { name: 'Prepare package' }))

    expect(onPrepareCourse).toHaveBeenCalledWith(31795, {
      roundId: 'live-black-knight',
      teeBox: 'blue',
      capturedAt: undefined,
    })
  })

  it('fills course package inputs from recent course options', async () => {
    const onPrepareCourse = vi.fn()

    render(
      <MobilePackagePrepPanel
        state={{ status: 'idle' }}
        courseOptionsState={{
          status: 'ready',
          data: {
            schema: 'ai-caddie-mobile-course-options-v1',
            dataMode: 'fixture',
            total: 1,
            courses: [
              {
                globalId: 31795,
                courseKey: 'black_knight',
                name: 'Black Knight B/C',
                roundCount: 2,
                latestRoundId: '900001',
                latestRoundDate: '2026-05-18',
                templateRoundId: '900001',
                suggestedLiveRoundId: 'live-31795',
                holes: 18,
                teeBox: 'blue',
                geometryCoverage: 'missing',
                sourceRefs: ['900001', '900002'],
              },
            ],
            emptyState: null,
            generatedAt: '2026-05-25T08:00:00Z',
          },
        }}
        onPrepareRound={vi.fn()}
        onPrepareCourse={onPrepareCourse}
      />,
    )

    await userEvent.click(screen.getByRole('radio', { name: 'Course' }))
    await userEvent.selectOptions(screen.getByLabelText('Recent course'), '31795')
    await userEvent.click(screen.getByRole('button', { name: 'Prepare package' }))

    expect(screen.getByLabelText('Course global ID')).toHaveValue('31795')
    expect(screen.getByLabelText('Live round ID')).toHaveValue('live-31795')
    expect(screen.getByLabelText('Tee box')).toHaveValue('blue')
    expect(onPrepareCourse).toHaveBeenCalledWith(31795, {
      roundId: 'live-31795',
      teeBox: 'blue',
      capturedAt: undefined,
    })
  })

  it('renders package readiness, coverage, weather, and missing data labels', () => {
    render(
      <MobilePackagePrepPanel
        state={{ status: 'ready', data: packageFixture }}
        onPrepareRound={vi.fn()}
        onPrepareCourse={vi.fn()}
      />,
    )

    const panel = screen.getByLabelText('Mobile package preparation')
    expect(within(panel).getByRole('heading', { name: 'Mobile Package Prep' })).toBeInTheDocument()
    expect(within(panel).getAllByText('degraded')[0]).toHaveClass('package-state-degraded')
    expect(within(panel).getByText('Fixture Links')).toBeInTheDocument()
    expect(within(panel).getByText('12/18 holes')).toBeInTheDocument()
    expect(within(panel).getByText('2/18 holes')).toBeInTheDocument()
    expect(within(panel).getByText('weather missing')).toBeInTheDocument()
    expect(within(panel).getByText('source ready')).toBeInTheDocument()
    expect(within(panel).getByText('fixture data')).toBeInTheDocument()
    expect(within(panel).getByText('template round 900001')).toBeInTheDocument()
    expect(within(panel).getByText('round found')).toBeInTheDocument()
    expect(within(panel).getByText('course found')).toBeInTheDocument()
    expect(within(panel).getByText('3 available rounds')).toBeInTheDocument()
    expect(within(panel).getByText('course 31795')).toBeInTheDocument()
    expect(within(panel).getByText('3 recent scores')).toBeInTheDocument()
    const readiness = within(panel).getByLabelText('Package readiness checks')
    expect(within(readiness).getByText('source')).toBeInTheDocument()
    expect(within(readiness).getByText('geometry')).toBeInTheDocument()
    expect(within(readiness).getByText('weather')).toBeInTheDocument()
    expect(within(readiness).getByText('12/18')).toBeInTheDocument()
    expect(within(readiness).getByText('2/18')).toBeInTheDocument()
    expect(within(readiness).getAllByText('degraded')[0]).toHaveClass('package-state-degraded')
    const caddieSeeds = within(panel).getByLabelText('Offline caddie seed options')
    expect(within(caddieSeeds).getByText('H1 Stock')).toBeInTheDocument()
    expect(within(caddieSeeds).getByText('selected')).toHaveClass('package-state-ready')
    expect(within(caddieSeeds).getByText('8I / 144m')).toBeInTheDocument()
    expect(within(caddieSeeds).getAllByText('high confidence')).toHaveLength(2)
    expect(within(caddieSeeds).getAllByText('coverage 24/24')).toHaveLength(2)
    expect(within(caddieSeeds).getAllByText('src live-black-knight:1')).toHaveLength(3)
    expect(within(caddieSeeds).getAllByText('sample refs 1')).toHaveLength(3)
    expect(within(caddieSeeds).getByText('missing club_profile_sample')).toBeInTheDocument()
  })
})
