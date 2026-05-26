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

function overviewPayloadWithRoundRefs() {
  return {
    ...overviewPayload(),
    recentRounds: [
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
    distribution: {
      total: 1,
      average: 82,
      best: 82,
      worst: 82,
      families: [{ label: '80s', count: 1, pct: 100, className: 'birdie', roundRefs: ['1'] }],
      histogram: [{ label: '80-84', start: 80, count: 1, roundRefs: ['1'] }],
    },
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
    courseDistribution: [{ courseKey: 'black_knight', roundCount: 2, pct: 66.7, roundRefs: ['900001', '900002'] }],
    records: {},
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

function mobileReconciliationPayload() {
  return {
    schema: 'ai-caddie-mobile-reconciliation-v1',
    roundId: '900001',
    summary: {
      eventCount: 1,
      matchedCount: 0,
      localOnlyCount: 0,
      garminOnlyCount: 0,
      conflictCount: 1,
      candidateDecisionAuditCount: 0,
      annotationSuggestionCount: 1,
    },
    matched: [],
    localOnly: [],
    garminOnly: [],
    conflicts: [{ eventId: 'score-conflict', kind: 'score', hole: 1, localValue: 5, garminValue: 4, ref: '900001:1' }],
    candidateDecisionAudits: [],
    annotationSuggestions: [
      {
        id: 'score-conflict:score-correction',
        targetType: 'hole',
        targetId: '900001:1',
        kind: 'score_correction',
        payload: { from: 4, to: 5, sourceEventId: 'score-conflict' },
        reason: 'Local score input can correct the derived score for this hole.',
        confidence: 'medium',
      },
    ],
  }
}

function mobileReconciliationApplyPayload() {
  return {
    schema: 'ai-caddie-mobile-reconciliation-apply-v1',
    roundId: '900001',
    appliedCount: 1,
    skippedCount: 0,
    missingSuggestionIds: [],
    skippedSuggestionIds: [],
    annotations: [
      {
        id: 'ann-mobile-1',
        createdAt: '2026-05-25T11:00:00Z',
        targetType: 'hole',
        targetId: '900001:1',
        kind: 'score_correction',
        payload: { from: 4, to: 5, sourceSuggestionId: 'score-conflict:score-correction' },
        source: 'manual',
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

function caddieContextPayload() {
  return {
    schema: 'ai-caddie-context-v1',
    sourceRef: '900001:7',
    shotType: 'approach',
    context: {
      source: 'history_drilldown',
      sourceRef: '900001:7',
      roundId: '900001',
      courseName: 'Black Knight B',
      hole: 7,
      globalId: 31795,
      localHole: 7,
      distanceToPin_m: 142,
      lie: 'fairway',
      geometry: { coverage: 'partial', hasHazards: true, hasMeshes: false, hazardCount: 1 },
      hazards: [{ kind: 'water', id: 'water-left' }],
      clubProfiles: { '8I': { clubName: '8I', sampleSize: 4, median: 144, p10: 132, p90: 153 } },
    },
    evidence: [{ label: 'history_ref', value: '900001:7' }],
    missingData: [{ label: 'meshes', reason: 'prodgeometry mesh file missing' }],
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

function weatherPayload() {
  return {
    schema: 'ai-caddie-weather-snapshot-v1',
    state: 'ready',
    source: 'manual',
    roundId: 'fixture-round',
    hole: 4,
    capturedAt: '2026-05-25T08:00:00Z',
    location: { latitude: 22.279, longitude: 114.162 },
    windSpeedMps: 5.4,
    windDirectionDeg: 110,
    temperatureC: 28.5,
    precipitationMm: 0,
    confidence: 'medium',
    missingData: [],
  }
}

function mediaListPayload() {
  return {
    schema: 'ai-caddie-media-list-v1',
    total: 1,
    target: { targetType: 'shot', targetId: 'fixture-round:4:approach' },
    media: [
      {
        id: 'media-1',
        createdAt: '2026-05-25T00:00:00Z',
        targetType: 'shot',
        targetId: 'fixture-round:4:approach',
        mediaKind: 'photo',
        localPath: 'data/media/uploads/lie.jpg',
        capturedAt: '2026-05-25T08:00:00Z',
        privacyState: 'private_local',
        source: 'manual',
      },
    ],
  }
}

function createdMediaPayload() {
  return {
    schema: 'ai-caddie-media-create-v1',
    media: {
      id: 'media-2',
      createdAt: '2026-05-25T00:02:00Z',
      targetType: 'shot',
      targetId: 'fixture-round:4:approach',
      mediaKind: 'photo',
      localPath: 'data/media/uploads/new-lie.jpg',
      capturedAt: '2026-05-25T08:02:00Z',
      privacyState: 'private_local',
      source: 'manual',
    },
  }
}

function visionFindingsPayload() {
  return {
    schema: 'ai-caddie-vision-findings-list-v1',
    total: 1,
    target: { targetType: 'shot', targetId: 'fixture-round:4:approach' },
    findings: [
      {
        id: 'finding-1',
        createdAt: '2026-05-25T00:01:00Z',
        targetType: 'shot',
        targetId: 'fixture-round:4:approach',
        mediaId: 'media-1',
        mediaKind: 'photo',
        findingType: 'visible_bunker',
        evidenceText: 'front bunker visible',
        confidence: 'medium',
        missingInfo: [],
        provider: 'static',
        model: 'static',
        source: 'vision_model',
      },
    ],
  }
}

function visionAnalysisPayload() {
  return {
    schema: 'ai-caddie-vision-context-v1',
    mediaId: 'media-1',
    targetType: 'shot',
    targetId: 'fixture-round:4:approach',
    mediaKind: 'photo',
    provider: 'static',
    model: 'static',
    findings: [
      {
        findingType: 'visible_bunker',
        evidenceText: 'front bunker visible',
        confidence: 'medium',
        missingInfo: [],
        provider: 'static',
        model: 'static',
        source: 'vision_model',
      },
    ],
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

function roundDrilldownPayload() {
  return {
    schema: 'ai-caddie-history-drilldown-v1',
    ref: '900001',
    refType: 'round',
    found: true,
    title: 'Black Knight B - 2026-05-18',
    round: { id: '900001', score: 77 },
    hole: null,
    shot: null,
    relatedRefs: { roundRefs: ['900001'], holeRefs: ['900001:1'], shotRefs: ['900001:1:0'] },
    sourceFields: { id: '900001', strokes: 77 },
    missingData: [],
  }
}

function overviewRoundDrilldownPayload() {
  return {
    schema: 'ai-caddie-history-drilldown-v1',
    ref: '1',
    refType: 'round',
    found: true,
    title: 'Black Knight B',
    round: { id: '1', score: 82 },
    hole: null,
    shot: null,
    relatedRefs: { roundRefs: ['1'], holeRefs: ['1:1'], shotRefs: ['1:1:0'] },
    sourceFields: { id: '1', strokes: 82 },
    missingData: [],
  }
}

function overviewHoleDrilldownPayload() {
  return {
    schema: 'ai-caddie-history-drilldown-v1',
    ref: '1:1',
    refType: 'hole',
    found: true,
    title: 'Black Knight B H1',
    round: { id: '1', score: 82 },
    hole: { number: 1, par: 4, strokes: 4 },
    shot: null,
    relatedRefs: { roundRefs: ['1'], holeRefs: ['1:1'], shotRefs: ['1:1:0'] },
    sourceFields: { number: 1, strokes: 4 },
    missingData: [],
  }
}

function holeDrilldownPayload() {
  return {
    schema: 'ai-caddie-history-drilldown-v1',
    ref: '900001:7',
    refType: 'hole',
    found: true,
    title: 'Black Knight B H7',
    round: { id: '900001', score: 77, globalId: 31795, courseName: 'Black Knight B' },
    hole: { number: 7, par: 4, strokes: 5, toPar: 1 },
    shot: null,
    relatedRefs: { roundRefs: ['900001'], holeRefs: ['900001:7'], shotRefs: ['900001:7:0'] },
    sourceFields: { number: 7, strokes: 5 },
    missingData: [],
  }
}

function holeGeometryEvidencePayload() {
  return {
    schema: 'ai-caddie-geometry-evidence-v1',
    globalId: 31795,
    localHole: 7,
    coverage: 'ready',
    hasHazards: true,
    hasMeshes: true,
    evidence: [{ label: 'hazards', ref: 'output/prodgeometry_hazards/gid31795_h07_hazards.json' }],
    missingData: [],
  }
}

function holeMapPayload() {
  return {
    schema: 'ai-caddie-hole-map-v1',
    globalId: 31795,
    localHole: 7,
    provider: { name: 'esri_world_imagery', label: 'Esri World Imagery', coordinateSystem: 'WGS84' },
    coverage: 'ready',
    layers: ['hazard', 'target'],
    featureCollection: {
      type: 'FeatureCollection',
      features: [
        {
          type: 'Feature',
          geometry: { type: 'Point', coordinates: [114.164, 22.281] },
          properties: { layer: 'target', id: 'pin' },
        },
      ],
    },
    missingData: [],
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
        if (path === '/api/v2/history/drilldown/900001') return roundDrilldownPayload()
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
    await userEvent.click(screen.getByRole('button', { name: 'Open source 900001' }))

    expect(await screen.findByText('Black Knight B - 2026-05-18')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/history/drilldown/900001')

    await userEvent.click(screen.getByRole('button', { name: 'Issues' }))

    expect(await screen.findByRole('heading', { name: 'Issue Stats' })).toBeInTheDocument()
    expect(screen.getByText('missing_shots')).toBeInTheDocument()
    expect(fetchMock.mock.calls.filter(([path]) => path === '/api/v2/history/stats')).toHaveLength(1)
  })

  it('opens source detail directly from overview and rounds cards', async () => {
    const fetchMock = vi.fn(async (path: string) => ({
      ok: true,
      json: async () => {
        if (path === '/api/v2/history/rounds') return roundsPayload()
        if (path === '/api/v2/history/drilldown/1%3A1') return overviewHoleDrilldownPayload()
        if (path === '/api/v2/history/drilldown/1') return overviewRoundDrilldownPayload()
        if (path === '/api/v2/sync/status') return syncStatusPayload()
        return overviewPayloadWithRoundRefs()
      },
    }))
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByText('History Overview')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Open round Black Knight B, 2026-05-20T08:00:00, score 82, ref 1' }))

    expect(await screen.findByRole('heading', { name: 'Source Detail' })).toBeInTheDocument()
    expect(screen.getAllByText('Black Knight B').length).toBeGreaterThan(1)
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/history/drilldown/1')
    await userEvent.click(screen.getByRole('button', { name: 'Open source 1:1' }))

    expect(await screen.findByText('Black Knight B H1')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/history/drilldown/1%3A1')

    await userEvent.click(screen.getByRole('button', { name: 'Rounds' }))
    expect(await screen.findByRole('heading', { name: 'Rounds' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Open round Black Knight B, 2026-05-20T08:00:00, score 82, ref 1' }))

    expect(fetchMock.mock.calls.filter(([path]) => path === '/api/v2/history/drilldown/1')).toHaveLength(2)
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

  it('opens the sync and data quality workspace and applies mobile reconciliation suggestions', async () => {
    const fetchMock = vi.fn(async (path: string, init?: RequestInit) => ({
      ok: true,
      json: async () => {
        if (path === '/api/v2/history/stats') return statsPayload()
        if (path === '/api/v2/sync/status') return syncStatusPayload()
        if (path === '/api/v2/readiness') return readinessPayload()
        if (path === '/api/v2/mobile/rounds/900001/reconciliation') return mobileReconciliationPayload()
        if (path === '/api/v2/mobile/rounds/900001/reconciliation/apply' && init?.method === 'POST') {
          return mobileReconciliationApplyPayload()
        }
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
    expect(screen.getByRole('heading', { name: 'Mobile Reconciliation' })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Review offline events' }))
    expect(await screen.findByText('Local score input can correct the derived score for this hole.')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Apply selected suggestions' }))
    expect(await screen.findByText('Applied 1 suggestions')).toBeInTheDocument()

    expect(fetchMock).toHaveBeenCalledWith('/api/v2/history/stats')
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/readiness')
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/mobile/rounds/900001/reconciliation')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v2/mobile/rounds/900001/reconciliation/apply',
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('loads hole geometry evidence after selecting a hole source ref', async () => {
    const fetchMock = vi.fn(async (path: string) => ({
      ok: true,
      json: async () => {
        if (path === '/api/v2/history/stats') return statsPayload()
        if (path === '/api/v2/history/drilldown/900001%3A7') return holeDrilldownPayload()
        if (path === '/api/v2/geometry/hole/31795/7') return holeGeometryEvidencePayload()
        if (path === '/api/v2/geometry/hole/31795/7/map?provider=esri_world_imagery') return holeMapPayload()
        if (path === '/api/v2/sync/status') return syncStatusPayload()
        return overviewPayload()
      },
    }))
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByText('History Overview')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Holes' }))
    expect(await screen.findByRole('heading', { name: 'Hole Stats' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Open source 900001:7' }))

    expect(await screen.findByRole('heading', { name: 'Source Detail' })).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: 'Hole Evidence' })).toBeInTheDocument()
    expect(screen.getByText('31795 H7')).toBeInTheDocument()
    expect(screen.getByText('Esri World Imagery')).toBeInTheDocument()
    expect(screen.getByText('WGS84')).toBeInTheDocument()
    expect(screen.getByText('pin')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/history/drilldown/900001%3A7')
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/geometry/hole/31795/7')
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/geometry/hole/31795/7/map?provider=esri_world_imagery')
  })

  it('opens the caddie workspace, attaches media context, and requests a decision', async () => {
    const fetchMock = vi.fn(async (path: string, init?: RequestInit) => ({
      ok: true,
      json: async () => {
        if (path === '/api/v2/media' && init?.method === 'POST') return createdMediaPayload()
        if (path === '/api/v2/media/target/shot/fixture-round%3A4%3Aapproach') return mediaListPayload()
        if (path === '/api/v2/media/media-1/analyze' && init?.method === 'POST') return visionAnalysisPayload()
        if (path === '/api/v2/media/target/shot/fixture-round%3A4%3Aapproach/findings') return visionFindingsPayload()
        if (String(path).startsWith('/api/v2/caddie/context')) return caddieContextPayload()
        if (path === '/api/v2/caddie/decision') return caddieDecisionPayload()
        if (path === '/api/v2/caddie/decisions/fixture-links-4-approach/audit') return caddieAuditPayload()
        if (String(path).startsWith('/api/v2/weather/snapshot')) return weatherPayload()
        if (path === '/api/v2/sync/status') return syncStatusPayload()
        return overviewPayload()
      },
    }))
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByText('History Overview')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Caddie' }))
    expect(await screen.findByRole('heading', { name: 'Caddie' })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Load weather' }))
    expect(await screen.findByText('5.4 m/s')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Load caddie context' }))
    expect(await screen.findByText('history_drilldown')).toBeInTheDocument()
    expect(screen.getByText('prodgeometry mesh file missing')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Load media context' }))
    expect(await screen.findByText('front bunker visible')).toBeInTheDocument()
    expect(screen.getByText('data/media/uploads/lie.jpg')).toBeInTheDocument()

    await userEvent.upload(screen.getByLabelText('Media file'), new File(['new-lie-bytes'], 'new-lie.jpg', { type: 'image/jpeg' }))
    await userEvent.click(screen.getByRole('button', { name: 'Attach media' }))
    expect(await screen.findByText('data/media/uploads/new-lie.jpg')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Analyze media media-1' }))
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/media/media-1/analyze', { method: 'POST' })

    await userEvent.click(screen.getByRole('button', { name: 'Request caddie plan' }))

    expect(await screen.findByText('8I')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/api/v2/weather/snapshot?source=manual'))
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v2/caddie/context?source_ref=900001%3A7&shot_type=approach&distance_to_pin_m=142&lie=fairway',
    )
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/media/target/shot/fixture-round%3A4%3Aapproach')
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/media/target/shot/fixture-round%3A4%3Aapproach/findings')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v2/media',
      expect.objectContaining({
        method: 'POST',
        body: expect.stringContaining('"contentBase64":"bmV3LWxpZS1ieXRlcw=="'),
      }),
    )
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/caddie/decision', expect.objectContaining({ method: 'POST' }))
    const decisionPost = fetchMock.mock.calls.find(([path]) => path === '/api/v2/caddie/decision')?.[1] as RequestInit
    const decisionBody = JSON.parse(String(decisionPost.body))
    expect(decisionBody.context.source).toBe('history_drilldown')
    expect(decisionBody.context.sourceRef).toBe('900001:7')
    expect(decisionBody.context.visionFindings[0].findingType).toBe('visible_bunker')

    expect(screen.queryByRole('button', { name: 'Audit with fixture outcome' })).not.toBeInTheDocument()
    await userEvent.clear(screen.getByLabelText('Actual club'))
    await userEvent.type(screen.getByLabelText('Actual club'), '9I')
    await userEvent.clear(screen.getByLabelText('Actual carry (m)'))
    await userEvent.type(screen.getByLabelText('Actual carry (m)'), '137')
    await userEvent.selectOptions(screen.getByLabelText('Result lie'), 'fringe')
    await userEvent.click(screen.getByRole('button', { name: 'Audit outcome' }))

    expect(await screen.findByText('execution')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v2/caddie/decisions/fixture-links-4-approach/audit',
      expect.objectContaining({ method: 'POST' }),
    )
    const auditPost = fetchMock.mock.calls.find(([path]) => path === '/api/v2/caddie/decisions/fixture-links-4-approach/audit')?.[1] as RequestInit
    const auditBody = JSON.parse(String(auditPost.body))
    expect(auditBody.actualShot).toEqual({
      shotOrder: 1,
      clubName: '9I',
      meters: 137,
      end: { lie: 'fringe', feature: { surface: { kind: 'fringe' }, nearRisks: [] } },
    })
  })
})
