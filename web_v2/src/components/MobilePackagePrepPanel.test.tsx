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
    { label: 'weather', reason: 'weather snapshot is missing for the prepared round time' },
  ],
  playerProfile: { playerId: 'player-1', displayName: 'Test Player', handedness: 'right' },
  course: { globalId: 31795, name: 'Fixture Links', teeBox: 'blue' },
  holes: [{ number: 1, par: 4, yards: 410, geometryCoverage: 'ready' }],
  geometryCoverage: { state: 'partial', readyHoles: 12, totalHoles: 18 },
  caddieContextSeeds: [{ hole: 1, sourceRef: 'live-black-knight:1', missingData: [{ label: 'current_location' }] }],
  weatherSnapshot: {
    schema: 'ai-caddie-weather-snapshot-v1',
    state: 'missing',
    source: 'missing',
    confidence: 'low',
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
    expect(within(panel).getByText('degraded')).toHaveClass('package-state-degraded')
    expect(within(panel).getByText('Fixture Links')).toBeInTheDocument()
    expect(within(panel).getByText('12/18 holes')).toBeInTheDocument()
    expect(within(panel).getByText('weather missing')).toBeInTheDocument()
    expect(within(panel).getByText('source ready')).toBeInTheDocument()
    expect(within(panel).getByText('fixture data')).toBeInTheDocument()
    expect(within(panel).getByText('template round 900001')).toBeInTheDocument()
    expect(within(panel).getByText('round found')).toBeInTheDocument()
    expect(within(panel).getByText('course found')).toBeInTheDocument()
    expect(within(panel).getByText('3 available rounds')).toBeInTheDocument()
    expect(within(panel).getByText('course 31795')).toBeInTheDocument()
    expect(within(panel).getByText('geometry')).toBeInTheDocument()
    expect(within(panel).getByText('weather')).toBeInTheDocument()
    expect(within(panel).getByText('3 recent scores')).toBeInTheDocument()
  })
})
