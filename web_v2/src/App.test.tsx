import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'

function overviewPayload() {
  return {
    schema: 'ai-caddie-history-overview-v2',
    metrics: {
      totalRounds: 1,
      eighteenHoleRounds: 1,
      nineHoleRounds: 0,
      courseCount: 1,
      shotCount: 18,
      average18: 82,
      recent10Average: 82,
      bestScore: 82,
    },
    recentRounds: [],
    distribution: {
      total: 1,
      average: 82,
      best: 82,
      worst: 82,
      families: [],
      histogram: [],
    },
    dataQuality: [],
    emptyState: null,
  }
}

function roundsPayload() {
  return {
    schema: 'ai-caddie-history-rounds-v2',
    total: 1,
    groups: [
      {
        key: '2026-05',
        label: 'May 2026',
        count: 1,
        average18: 82,
        bestScore: 82,
        rounds: [
          {
            id: '1',
            date: '2026-05-20T08:00:00',
            courseName: 'Black Knight B',
            courseKey: 'c_black',
            holesCompleted: 18,
            score: 82,
            par: 72,
            toPar: 10,
            primaryIssue: null,
            badges: [{ label: 'shots', state: 'good', value: 'ready', reason: 'ready' }],
            scoreStrip: [{ hole: 1, par: 4, score: 4, toPar: 0, className: 'par' }],
          },
        ],
      },
    ],
    emptyState: null,
  }
}

function statsPayload() {
  return {
    schema: 'ai-caddie-history-stats-v1',
    dataMode: 'fixture',
    summary: { totalRounds: 3, average18: 82, bestScore: 77, shotCount: 6 },
    time: { byMonth: [{ key: '2026-05', roundCount: 1, average18: 77, bestScore: 77 }] },
    scoring: { scoreBands: [{ label: '70s', count: 1, roundIds: ['900001'] }] },
    courses: [
      {
        courseKey: 'black_knight',
        courseName: 'Black Knight B',
        roundCount: 2,
        average18: 82,
        bestScore: 77,
        worstScore: 87,
        roundIds: ['900001', '900002'],
      },
    ],
    holes: [{ courseKey: 'black_knight', hole: 7, sampleCount: 2, averageToPar: 1.5, worstToPar: 3, refs: ['900001:7'] }],
    clubs: [
      {
        club: '1D',
        sampleCount: 2,
        median: 240,
        p10: 225,
        p90: 255,
        max: 270,
        confidence: 'medium',
        shotRefs: ['900001:1:0', '900002:5:4'],
      },
    ],
    issues: [{ issue: 'missing_shots', count: 1, refs: ['900003'] }],
    dataQuality: [{ label: 'shots', state: 'partial', ready: 2, total: 3, refs: ['900003'] }],
    drillDown: { roundIds: ['900001', '900002', '900003'], roundRefs: ['900001', '900002', '900003'] },
  }
}

function syncStatusPayload() {
  return {
    schema: 'ai-caddie-sync-status-v2',
    connector: {
      name: 'garmin_cn_web_session',
      state: 'ready',
      detail: 'Local Garmin snapshots are available.',
      canSync: false,
      reauthRequired: false,
    },
    snapshot: {
      dataMode: 'fixture',
      scorecardCount: 3,
      shotFileCount: 2,
      summaryPresent: true,
      lastSuccessfulSyncAt: null,
    },
    lastRun: null,
  }
}

function readinessPayload() {
  return {
    schema: 'ai-caddie-readiness-v1',
    status: 'degraded',
    checks: [
      { label: 'service', state: 'ready', detail: 'API process is responding.', evidence: {} },
      {
        label: 'history',
        state: 'degraded',
        detail: 'No rounds are loaded for history review.',
        evidence: { dataMode: 'fixture', totalRounds: 0 },
      },
      {
        label: 'sync',
        state: 'degraded',
        detail: 'Garmin connector status is available.',
        evidence: { connectorState: 'ready', scorecardCount: 3 },
      },
    ],
  }
}

function annotationsPayload() {
  return {
    schema: 'ai-caddie-annotations-v1',
    total: 2,
    target: null,
    annotations: [
      {
        id: 'ann-1',
        createdAt: '2026-05-25T10:30:00Z',
        targetType: 'shot',
        targetId: 'round-1:7:shot-3',
        kind: 'club_correction',
        payload: { from: '7I', to: '8I', note: 'mis-tagged iron' },
        source: 'manual',
      },
      {
        id: 'ann-2',
        createdAt: '2026-05-25T10:32:00Z',
        targetType: 'hole',
        targetId: 'round-1:7',
        kind: 'issue_tag',
        payload: { tag: 'approach_short' },
        source: 'manual',
      },
    ],
  }
}

function createdAnnotationPayload() {
  return {
    schema: 'ai-caddie-annotation-create-v1',
    annotation: {
      id: 'ann-3',
      createdAt: '2026-05-25T10:40:00Z',
      targetType: 'shot',
      targetId: 'round-1:8:shot-1',
      kind: 'club_correction',
      payload: { from: '7I', to: '8I', note: 'Trackman confirmed the club' },
      source: 'manual',
    },
  }
}

function trendReportPayload() {
  return {
    schema: 'ai-caddie-review-report-v1',
    kind: 'trend',
    provider: 'StaticProvider',
    model: 'static',
    factsUsed: [{ label: 'summary_trend', source: 'summary', value: { totalRounds: 3 } }],
    missingData: [{ label: 'weather', state: 'partial' }],
    narrative: 'Trend review from stored facts.',
    confidence: 'medium',
  }
}

function caddieDecisionPayload() {
  return {
    schema: 'ai-caddie-decision-v2',
    shotType: 'approach',
    phase: 'Approach',
    context: { courseName: 'Fixture Links', hole: 4, distanceToPin_m: 142 },
    options: [
      { id: 'safe', label: 'Safe', recommendedClub: '9I' },
      { id: 'stock', label: 'Stock', recommendedClub: '8I' },
      { id: 'attack', label: 'Attack', recommendedClub: '7I' },
    ],
    selected: { id: 'stock' },
    selectedOptionId: 'stock',
    selectedOption: { id: 'stock' },
    avoidZones: [{ kind: 'water', id: 'water_front' }],
    forbiddenZones: [],
    acceptableMiss: { side: 'long' },
    evidence: [{ label: 'water_front', value: 'carry 126m' }],
    confidence: { level: 'medium' },
    missingData: [],
    auditCriteria: [],
  }
}

function caddieAuditPayload() {
  return {
    schema: 'ai-caddie-decision-audit-store-v1',
    record: {
      id: 'audit-1',
      storedAt: '2026-05-25T00:00:00Z',
      decisionId: 'fixture-links-4-approach',
      audit: {
        schema: 'ai-caddie-decision-audit-v1',
        phase: 'Approach',
        plannedOptionId: 'stock',
        actualOptionId: 'stock',
        classification: 'execution',
        executionMatch: { hasFirstShot: true, clubMatch: true, distanceDelta_m: -1 },
        result: { clubName: '8I', meters: 143, surface: 'green' },
        modelUpdateSuggestion: { kind: 'none' },
      },
    },
  }
}

function drilldownPayload() {
  return {
    schema: 'ai-caddie-history-drilldown-v1',
    ref: '900001:1:0',
    refType: 'shot',
    found: true,
    title: '1D on H1',
    round: { id: '900001', score: 77 },
    hole: { number: 1, par: 4, strokes: 4, toPar: 0 },
    shot: { club: '1D', distance: 242, surface: 'fairway' },
    relatedRefs: { roundRefs: ['900001'], holeRefs: ['900001:1'], shotRefs: ['900001:1:0'] },
    sourceFields: { clubName: '1D', meters: 242 },
    missingData: [{ label: 'geometry', state: 'partial' }],
  }
}

describe('App navigation', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('exposes the master spec IA and opens the rounds timeline', async () => {
    const fetchMock = vi.fn(async (path: string) => ({
      ok: true,
      json: async () => {
        if (path === '/api/v2/history/rounds') return roundsPayload()
        if (path === '/api/v2/sync/status') return syncStatusPayload()
        return overviewPayload()
      },
    }))
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByText('History Overview')).toBeInTheDocument()
    expect(await screen.findByText('Garmin CN')).toBeInTheDocument()
    expect(screen.getAllByText('ready').length).toBeGreaterThan(0)
    expect(screen.getByText('Overview')).toBeInTheDocument()
    ;['History', 'Rounds', 'Courses', 'Holes', 'Clubs', 'Issues', 'Caddie', 'Sync & Data Quality', 'Reports', 'Settings'].forEach(
      (label) => expect(screen.getByRole('button', { name: label })).toBeEnabled(),
    )
    expect(screen.queryByRole('button', { name: 'Stats' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Quality' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Corrections' })).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Rounds' }))

    expect(await screen.findByRole('heading', { name: 'Rounds' })).toBeInTheDocument()
    expect(screen.getByText('May 2026')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/history/rounds')
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/sync/status')
    await waitFor(() => expect(screen.queryByText('History API unavailable')).not.toBeInTheDocument())
  })

  it('loads history stats once and navigates between stats-backed pages', async () => {
    const fetchMock = vi.fn(async (path: string) => ({
      ok: true,
      json: async () => {
        if (path === '/api/v2/history/stats') return statsPayload()
        if (path === '/api/v2/history/drilldown/900001%3A1%3A0') return drilldownPayload()
        if (path === '/api/v2/sync/status') return syncStatusPayload()
        return overviewPayload()
      },
    }))
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByText('History Overview')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'History' }))

    expect(await screen.findByRole('heading', { name: 'Statistics Overview' })).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/history/stats')

    await userEvent.click(screen.getByRole('button', { name: 'Clubs' }))

    expect(await screen.findByRole('heading', { name: 'Club Stats' })).toBeInTheDocument()
    expect(screen.getByText('1D')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Open source 900001:1:0' }))

    expect(await screen.findByRole('heading', { name: 'Source Detail' })).toBeInTheDocument()
    expect(screen.getByText('1D on H1')).toBeInTheDocument()
    expect(screen.getByText('geometry')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/history/drilldown/900001%3A1%3A0')

    await userEvent.click(screen.getByRole('button', { name: 'Issues' }))

    expect(await screen.findByRole('heading', { name: 'Issue Stats' })).toBeInTheDocument()
    expect(screen.getByText('missing_shots')).toBeInTheDocument()
    expect(fetchMock.mock.calls.filter(([path]) => path === '/api/v2/history/stats')).toHaveLength(1)
  })

  it('shows corrections history and adds a club correction from the response', async () => {
    const fetchMock = vi.fn(async (path: string, init?: RequestInit) => ({
      ok: true,
      json: async () => {
        if (path === '/api/v2/annotations' && init?.method === 'POST') return createdAnnotationPayload()
        if (path === '/api/v2/annotations') return annotationsPayload()
        if (path === '/api/v2/sync/status') return syncStatusPayload()
        return overviewPayload()
      },
    }))
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByText('History Overview')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Settings' }))
    expect(await screen.findByRole('heading', { name: 'Settings' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Open corrections' }))

    expect(await screen.findByRole('heading', { name: 'Corrections' })).toBeInTheDocument()
    const history = screen.getByLabelText('Annotation history')
    expect(within(history).getByText('round-1:7:shot-3')).toBeInTheDocument()
    expect(within(history).getByText('Club correction')).toBeInTheDocument()
    expect(within(history).getByText('7I -> 8I')).toBeInTheDocument()
    expect(within(history).getByText('approach_short')).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Club correction' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Putt correction' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Issue tag' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Note' })).toBeInTheDocument()

    await userEvent.selectOptions(screen.getByLabelText('Target type'), 'shot')
    await userEvent.clear(screen.getByLabelText('Target ID'))
    await userEvent.type(screen.getByLabelText('Target ID'), 'round-1:8:shot-1')
    await userEvent.selectOptions(screen.getByLabelText('Correction type'), 'club_correction')
    await userEvent.type(screen.getByLabelText('Recorded club'), '7I')
    await userEvent.type(screen.getByLabelText('Corrected club'), '8I')
    await userEvent.type(screen.getByLabelText('Note'), 'Trackman confirmed the club')
    await userEvent.click(screen.getByRole('button', { name: 'Save annotation' }))

    expect(fetchMock).toHaveBeenCalledWith('/api/v2/annotations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        targetType: 'shot',
        targetId: 'round-1:8:shot-1',
        kind: 'club_correction',
        payload: { from: '7I', to: '8I', note: 'Trackman confirmed the club' },
      }),
    })
    expect(await screen.findByText('round-1:8:shot-1')).toBeInTheDocument()
    expect(screen.getAllByText('7I -> 8I')).toHaveLength(2)
    expect(screen.getByText('Trackman confirmed the club')).toBeInTheDocument()
  })

  it('opens the reports workspace and loads a trend report', async () => {
    const fetchMock = vi.fn(async (path: string) => ({
      ok: true,
      json: async () => {
        if (path === '/api/v2/history/stats') return statsPayload()
        if (path === '/api/v2/reports/trend/recent_10') return trendReportPayload()
        if (path === '/api/v2/sync/status') return syncStatusPayload()
        return overviewPayload()
      },
    }))
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByText('History Overview')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Reports' }))

    expect(await screen.findByRole('heading', { name: 'Reports' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Load trend report' }))

    expect(await screen.findByText('Trend review from stored facts.')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/history/stats')
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/reports/trend/recent_10')
  })

  it('opens the sync and data quality workspace', async () => {
    const fetchMock = vi.fn(async (path: string) => ({
      ok: true,
      json: async () => {
        if (path === '/api/v2/history/stats') return statsPayload()
        if (path === '/api/v2/sync/status') return syncStatusPayload()
        if (path === '/api/v2/readiness') return readinessPayload()
        return overviewPayload()
      },
    }))
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByText('History Overview')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Sync & Data Quality' }))

    expect(await screen.findByRole('heading', { name: 'Sync & Data Quality' })).toBeInTheDocument()
    expect(screen.getByText('Garmin CN')).toBeInTheDocument()
    expect(screen.getAllByText('Local Garmin snapshots are available.').length).toBeGreaterThan(0)
    expect(screen.getByRole('heading', { name: 'Private Trial Readiness' })).toBeInTheDocument()
    expect(screen.getByText('dataMode: fixture')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Data Quality' })).toBeInTheDocument()
    expect(screen.getByText('shots')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/history/stats')
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/readiness')
  })

  it('opens the caddie workspace and requests a decision', async () => {
    const fetchMock = vi.fn(async (path: string) => ({
      ok: true,
      json: async () => {
        if (path === '/api/v2/caddie/decision') return caddieDecisionPayload()
        if (path === '/api/v2/caddie/decisions/fixture-links-4-approach/audit') return caddieAuditPayload()
        if (path === '/api/v2/sync/status') return syncStatusPayload()
        return overviewPayload()
      },
    }))
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByText('History Overview')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Caddie' }))
    expect(await screen.findByRole('heading', { name: 'Caddie' })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Request caddie plan' }))

    expect(await screen.findByText('8I')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/caddie/decision', expect.objectContaining({ method: 'POST' }))

    await userEvent.click(screen.getByRole('button', { name: 'Audit with fixture outcome' }))

    expect(await screen.findByText('execution')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v2/caddie/decisions/fixture-links-4-approach/audit',
      expect.objectContaining({ method: 'POST' }),
    )
  })
})
