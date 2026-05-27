import { act, render, screen, waitFor, within } from '@testing-library/react'
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

function syncStatusCanSyncPayload() {
  const payload = syncStatusPayload()
  return {
    ...payload,
    connector: { ...payload.connector, canSync: true },
  }
}

function syncRunPayload() {
  return {
    schema: 'ai-caddie-sync-run-v2',
    connector: 'garmin_cn_web_session',
    state: 'ready',
    detail: 'Sync completed.',
    reauthRequired: false,
    errorCode: null,
    snapshot: {
      snapshotId: 'snap-test',
      scorecardCount: 3,
      shotFileCount: 2,
      summaryPresent: true,
      files: [],
    },
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

function productSettingsPayload() {
  return {
    schema: 'ai-caddie-product-settings-v1',
    dataSources: [
      { id: 'garmin_cn_web_session', label: 'Garmin CN Web Session', track: 'primary', state: 'available', capabilities: ['scorecards'] },
      { id: 'garmin_oauth', label: 'Official Garmin OAuth', track: 'feasibility', state: 'not_syncable', capabilities: [] },
    ],
    aiProviders: {
      activeProvider: 'gemini_api_key',
      factBindingRequired: true,
      providers: [
        { id: 'static', label: 'Static', state: 'ready' },
        { id: 'gemini_api_key', label: 'Gemini API', state: 'configured' },
      ],
    },
    liveApps: { ios: { state: 'contract_ready' }, watch: { state: 'contract_ready' }, vision: { state: 'bounded_context' } },
    privacy: {
      noGarminPasswordStorage: true,
      adminProtectedWrites: true,
      mediaRedaction: true,
      localSnapshotsSurviveReauth: true,
      secretFreeStatusResponses: true,
    },
    endpoints: { syncStatus: '/api/v2/sync/status' },
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

function mobilePackagePayload() {
  return {
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
    caddieContextSeeds: [{ hole: 1, sourceRef: 'live-black-knight:1', missingData: [] }],
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
    subjectId: 'recent_10',
    sourceRefs: ['900001'],
    provider: 'StaticProvider',
    model: 'static',
    factsUsed: [{ label: 'summary_trend', source: 'summary', value: { totalRounds: 3 } }],
    missingData: [{ label: 'weather', state: 'partial' }],
    narrative: 'Trend review from stored facts.',
    confidence: 'medium',
  }
}

function reportIndexPayload() {
  return {
    schema: 'ai-caddie-review-report-index-v1',
    total: 2,
    reports: [
      {
        id: 'trend-report',
        storedAt: '2026-05-26T00:00:00Z',
        kind: 'trend',
        subjectId: 'recent_10',
        confidence: 'medium',
        provider: 'StaticProvider',
        model: 'static',
        sourceRefs: ['900001'],
      },
      {
        id: 'round-report',
        storedAt: '2026-05-25T00:00:00Z',
        kind: 'round',
        subjectId: '900001',
        confidence: 'high',
        provider: 'StaticProvider',
        model: 'static',
        sourceRefs: ['900001'],
      },
    ],
  }
}

function caddieDecisionPayload() {
  return {
    schema: 'ai-caddie-decision-v2',
    decisionId: 'fixture-round:4:approach',
    sourceRef: 'fixture-round:4',
    evidenceRefs: ['fixture-round:4'],
    shotType: 'approach',
    phase: 'Approach',
    context: { courseName: 'Fixture Links', hole: 4, sourceRef: 'fixture-round:4', distanceToPin_m: 142 },
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
      decisionId: 'fixture-round:4:approach',
      sourceRef: 'fixture-round:4',
      selectedOptionId: 'stock',
      plannedOptionId: 'stock',
      actualOptionId: 'stock',
      actualShotRefs: ['fixture-round:4:1'],
      evidenceRefs: ['fixture-round:4'],
      classification: 'execution',
      audit: {
        schema: 'ai-caddie-decision-audit-v1',
        decisionId: 'fixture-round:4:approach',
        decisionSourceRef: 'fixture-round:4',
        phase: 'Approach',
        plannedOptionId: 'stock',
        selectedOptionId: 'stock',
        actualOptionId: 'stock',
        actualShotRefs: ['fixture-round:4:1'],
        evidenceRefs: ['fixture-round:4'],
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

function selectedShotDrilldownPayload() {
  return {
    schema: 'ai-caddie-history-drilldown-v1',
    ref: '900002:5:4',
    refType: 'shot',
    found: true,
    title: '1D on H5',
    round: { id: '900002', score: 87 },
    hole: { number: 5, par: 5, strokes: 6, toPar: 1 },
    shot: { club: '1D', distance: 255, surface: 'rough' },
    relatedRefs: { roundRefs: ['900002'], holeRefs: ['900002:5'], shotRefs: ['900002:5:4'] },
    sourceFields: { clubName: '1D', meters: 255 },
    missingData: [],
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

function partialHoleGeometryEvidencePayload() {
  return {
    ...holeGeometryEvidencePayload(),
    coverage: 'partial',
    hasMeshes: false,
    missingData: [{ label: 'meshes', reason: 'prodgeometry mesh file missing' }],
  }
}

function geometryEnsurePayload() {
  return {
    schema: 'ai-caddie-geometry-ensure-v1',
    status: 'downloaded',
    ok: true,
    globalId: 31795,
    localHole: 7,
    releaseSource: 'prodgeometry',
    steps: { hazards: 'ready', meshes: 'ready' },
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
    ;['History', 'Rounds', 'Courses', 'Holes', 'Clubs', 'Issues', 'Caddie', 'Corrections', 'Sync & Data Quality', 'Reports', 'Settings'].forEach(
      (label) => expect(screen.getByRole('button', { name: label })).toBeEnabled(),
    )
    expect(screen.queryByRole('button', { name: 'Stats' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Quality' })).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Rounds' }))

    expect(await screen.findByRole('heading', { name: 'Rounds' })).toBeInTheDocument()
    expect(screen.getByText('May 2026')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/history/rounds')
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/sync/status')
    await waitFor(() => expect(screen.queryByText('History API unavailable')).not.toBeInTheDocument())
  })

  it('can recover protected history overview after entering an admin token', async () => {
    const fetchMock = vi.fn(async (path: string, init?: RequestInit) => {
      if (path === '/api/v2/sync/status') {
        return {
          ok: true,
          json: async () => syncStatusPayload(),
        }
      }
      if (path === '/api/v2/history/overview' && init?.headers && (init.headers as Record<string, string>)['X-AI-Caddie-Admin-Token'] === 'admin-secret') {
        return {
          ok: true,
          json: async () => overviewPayload(),
        }
      }
      return {
        ok: false,
        status: 401,
        statusText: 'Unauthorized',
      }
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByRole('heading', { name: 'History API unavailable' })).toBeInTheDocument()
    await userEvent.type(await screen.findByLabelText('Admin token'), 'admin-secret')
    await userEvent.click(screen.getByRole('button', { name: 'Retry history' }))

    expect(await screen.findByText('History Overview')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/history/overview', {
      headers: { 'X-AI-Caddie-Admin-Token': 'admin-secret' },
    })
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

  it('renders loading and error states for deferred history stats', async () => {
    let rejectStats: (error: Error) => void = () => {}
    const statsPromise = new Promise<never>((_, reject) => {
      rejectStats = reject
    })
    const fetchMock = vi.fn((path: string) => {
      if (path === '/api/v2/history/stats') return statsPromise
      return Promise.resolve({
        ok: true,
        json: async () => {
          if (path === '/api/v2/sync/status') return syncStatusPayload()
          return overviewPayload()
        },
      })
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByText('History Overview')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'History' }))

    expect(await screen.findByRole('heading', { name: 'Loading history stats' })).toBeInTheDocument()

    await act(async () => {
      rejectStats(new Error('GET /api/v2/history/stats failed: 500 Internal Server Error'))
    })

    expect(await screen.findByRole('heading', { name: 'History stats unavailable' })).toBeInTheDocument()
    expect(screen.getByText('GET /api/v2/history/stats failed: 500 Internal Server Error')).toBeInTheDocument()
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
    await userEvent.click(screen.getByRole('button', { name: 'Corrections' }))

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

  it('opens contextual corrections from source drilldown with the target prefilled', async () => {
    const fetchMock = vi.fn(async (path: string, init?: RequestInit) => ({
      ok: true,
      json: async () => {
        if (path === '/api/v2/history/drilldown/1') return overviewRoundDrilldownPayload()
        if (path === '/api/v2/annotations') return annotationsPayload()
        if (path === '/api/v2/sync/status') return syncStatusPayload()
        if (path === '/api/v2/annotations' && init?.method === 'POST') return createdAnnotationPayload()
        return overviewPayloadWithRoundRefs()
      },
    }))
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByText('History Overview')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Open round Black Knight B, 2026-05-20T08:00:00, score 82, ref 1' }))
    expect(await screen.findByRole('heading', { name: 'Source Detail' })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Add correction for source 1' }))

    expect(await screen.findByRole('heading', { name: 'Corrections' })).toBeInTheDocument()
    expect(screen.getByLabelText('Target type')).toHaveValue('round')
    expect(screen.getByLabelText('Target ID')).toHaveValue('1')
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/annotations')
  })

  it('loads API-backed settings state when opening settings', async () => {
    const fetchMock = vi.fn(async (path: string) => ({
      ok: true,
      json: async () => {
        if (path === '/api/v2/settings/product') return productSettingsPayload()
        if (path === '/api/v2/sync/status') return syncStatusPayload()
        return overviewPayload()
      },
    }))
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByText('History Overview')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Settings' }))

    expect(await screen.findByRole('heading', { name: 'Settings' })).toBeInTheDocument()
    expect(await screen.findByText('active: Gemini API')).toHaveClass('setting-primary')
    expect(screen.getByText('available')).toHaveClass('setting-primary')
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/settings/product')
  })

  it('refreshes loaded history stats after creating a correction', async () => {
    const fetchMock = vi.fn(async (path: string, init?: RequestInit) => ({
      ok: true,
      json: async () => {
        if (path === '/api/v2/history/stats') return statsPayload()
        if (path === '/api/v2/annotations' && init?.method === 'POST') return createdAnnotationPayload()
        if (path === '/api/v2/annotations') return annotationsPayload()
        if (path === '/api/v2/sync/status') return syncStatusPayload()
        return overviewPayload()
      },
    }))
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByText('History Overview')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'History' }))
    expect(await screen.findByRole('heading', { name: 'Statistics Overview' })).toBeInTheDocument()
    expect(fetchMock.mock.calls.filter(([path]) => path === '/api/v2/history/stats')).toHaveLength(1)

    await userEvent.click(screen.getByRole('button', { name: 'Settings' }))
    await userEvent.click(screen.getByRole('button', { name: 'Open corrections' }))
    expect(await screen.findByRole('heading', { name: 'Corrections' })).toBeInTheDocument()

    await userEvent.selectOptions(screen.getByLabelText('Target type'), 'shot')
    await userEvent.clear(screen.getByLabelText('Target ID'))
    await userEvent.type(screen.getByLabelText('Target ID'), 'round-1:8:shot-1')
    await userEvent.selectOptions(screen.getByLabelText('Correction type'), 'club_correction')
    await userEvent.type(screen.getByLabelText('Recorded club'), '7I')
    await userEvent.type(screen.getByLabelText('Corrected club'), '8I')
    await userEvent.click(screen.getByRole('button', { name: 'Save annotation' }))

    await waitFor(() => expect(fetchMock.mock.calls.filter(([path]) => path === '/api/v2/history/stats')).toHaveLength(2))
  })

  it('opens the reports workspace and loads a trend report', async () => {
    const fetchMock = vi.fn(async (path: string) => ({
      ok: true,
      json: async () => {
        if (path === '/api/v2/history/stats') return statsPayload()
        if (path === '/api/v2/reports') return reportIndexPayload()
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
    expect(await screen.findByRole('heading', { name: 'Report inventory' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open stored trend recent_10' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Load trend report' }))
    await userEvent.click(screen.getByRole('button', { name: 'Open stored trend recent_10' }))

    expect(await screen.findByText('Trend review from stored facts.')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/history/stats')
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/reports')
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/reports/trend/recent_10')
  })

  it('drills from a loaded report source ref to source detail', async () => {
    const fetchMock = vi.fn(async (path: string) => ({
      ok: true,
      json: async () => {
        if (path === '/api/v2/history/stats') return statsPayload()
        if (path === '/api/v2/reports') return reportIndexPayload()
        if (path === '/api/v2/reports/trend/recent_10') return trendReportPayload()
        if (path === '/api/v2/history/drilldown/900001') return roundDrilldownPayload()
        if (path === '/api/v2/sync/status') return syncStatusPayload()
        return overviewPayload()
      },
    }))
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByText('History Overview')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Reports' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Load trend report' }))
    const identity = await screen.findByLabelText('Report identity')
    await userEvent.click(within(identity).getByRole('button', { name: 'Open source 900001' }))

    expect(await screen.findByRole('heading', { name: 'Source Detail' })).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/history/drilldown/900001')
  })

  it('opens the sync and data quality workspace, prepares a mobile package, and applies reconciliation suggestions', async () => {
    const fetchMock = vi.fn(async (path: string, init?: RequestInit) => ({
      ok: true,
      json: async () => {
        if (path === '/api/v2/history/stats') return statsPayload()
        if (path === '/api/v2/sync/status') return syncStatusPayload()
        if (path === '/api/v2/readiness') return readinessPayload()
        if (path === '/api/v2/mobile/courses/31795/package?round_id=live-black-knight&tee_box=blue') return mobilePackagePayload()
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
    expect(screen.getByRole('heading', { name: 'Mobile Package Prep' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Mobile Reconciliation' })).toBeInTheDocument()

    await userEvent.type(screen.getByLabelText('Admin token'), 'admin-secret')
    await userEvent.click(screen.getByRole('radio', { name: 'Course' }))
    await userEvent.clear(screen.getByLabelText('Course global ID'))
    await userEvent.type(screen.getByLabelText('Course global ID'), '31795')
    await userEvent.type(screen.getByLabelText('Live round ID'), 'live-black-knight')
    await userEvent.type(screen.getByLabelText('Tee box'), 'blue')
    await userEvent.click(screen.getByRole('button', { name: 'Prepare package' }))
    expect(await screen.findByText('Fixture Links')).toBeInTheDocument()
    expect(screen.getByText('12/18 holes')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Review offline events' }))
    expect(await screen.findByText('Local score input can correct the derived score for this hole.')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Apply selected suggestions' }))
    expect(await screen.findByText('Applied 1 suggestions')).toBeInTheDocument()

    await waitFor(() => expect(fetchMock.mock.calls.filter(([path]) => path === '/api/v2/history/stats')).toHaveLength(2))
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/readiness')
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/mobile/courses/31795/package?round_id=live-black-knight&tee_box=blue', {
      headers: { 'X-AI-Caddie-Admin-Token': 'admin-secret' },
    })
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/mobile/rounds/900001/reconciliation')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v2/mobile/rounds/900001/reconciliation/apply',
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('keeps mobile package admin token input available when sync status cannot load', async () => {
    const fetchMock = vi.fn(async (path: string) => {
      if (path === '/api/v2/sync/status') {
        return { ok: false, status: 503, statusText: 'Service Unavailable', json: async () => ({}) }
      }
      return {
        ok: true,
        json: async () => {
          if (path === '/api/v2/history/stats') return statsPayload()
          if (path === '/api/v2/readiness') return readinessPayload()
          if (path === '/api/v2/mobile/courses/31795/package?round_id=live-black-knight') return mobilePackagePayload()
          return overviewPayload()
        },
      }
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByText('History Overview')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Sync & Data Quality' }))

    expect(await screen.findByRole('heading', { name: 'Mobile Package Prep' })).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Admin token'), 'admin-secret')
    await userEvent.click(screen.getByRole('radio', { name: 'Course' }))
    await userEvent.clear(screen.getByLabelText('Course global ID'))
    await userEvent.type(screen.getByLabelText('Course global ID'), '31795')
    await userEvent.type(screen.getByLabelText('Live round ID'), 'live-black-knight')
    await userEvent.click(screen.getByRole('button', { name: 'Prepare package' }))

    expect(await screen.findByText('Fixture Links')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/mobile/courses/31795/package?round_id=live-black-knight', {
      headers: { 'X-AI-Caddie-Admin-Token': 'admin-secret' },
    })
  })

  it('refreshes loaded history stats after Garmin sync completes', async () => {
    const fetchMock = vi.fn(async (path: string, init?: RequestInit) => ({
      ok: true,
      json: async () => {
        if (path === '/api/v2/history/stats') return statsPayload()
        if (path === '/api/v2/sync/status') return syncStatusCanSyncPayload()
        if (String(path).startsWith('/api/v2/sync/garmin?') && init?.method === 'POST') return syncRunPayload()
        return overviewPayload()
      },
    }))
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByText('History Overview')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'History' }))
    expect(await screen.findByRole('heading', { name: 'Statistics Overview' })).toBeInTheDocument()
    expect(fetchMock.mock.calls.filter(([path]) => path === '/api/v2/history/stats')).toHaveLength(1)

    await userEvent.click(screen.getByRole('button', { name: 'Sync now' }))

    expect(fetchMock).toHaveBeenCalledWith('/api/v2/sync/garmin?with_shots=true&force_refresh_auth=false', { method: 'POST' })
    await waitFor(() => expect(fetchMock.mock.calls.filter(([path]) => path === '/api/v2/history/stats')).toHaveLength(2))
  })

  it('loads hole geometry evidence after selecting a hole source ref', async () => {
    const fetchMock = vi.fn(async (path: string) => ({
      ok: true,
      json: async () => {
        if (path === '/api/v2/history/stats') return statsPayload()
        if (path === '/api/v2/history/drilldown/900001%3A7') return holeDrilldownPayload()
        if (path === '/api/v2/geometry/hole/31795/7?source_ref=900001%3A7') return holeGeometryEvidencePayload()
        if (path === '/api/v2/geometry/hole/31795/7/map?provider=esri_world_imagery&source_ref=900001%3A7') return holeMapPayload()
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
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/geometry/hole/31795/7?source_ref=900001%3A7')
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/geometry/hole/31795/7/map?provider=esri_world_imagery&source_ref=900001%3A7')
  })

  it('ensures missing hole geometry and refreshes evidence', async () => {
    let ensured = false
    const fetchMock = vi.fn(async (path: string, init?: RequestInit) => ({
      ok: true,
      json: async () => {
        if (path === '/api/v2/history/stats') return statsPayload()
        if (path === '/api/v2/history/drilldown/900001%3A7') return holeDrilldownPayload()
        if (path === '/api/v2/geometry/hole/31795/7/ensure' && init?.method === 'POST') {
          ensured = true
          return geometryEnsurePayload()
        }
        if (path === '/api/v2/geometry/hole/31795/7?source_ref=900001%3A7') {
          return ensured ? holeGeometryEvidencePayload() : partialHoleGeometryEvidencePayload()
        }
        if (path === '/api/v2/geometry/hole/31795/7/map?provider=esri_world_imagery&source_ref=900001%3A7') return holeMapPayload()
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

    expect(await screen.findByText('partial coverage')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Fetch geometry for 31795 H7' }))

    expect(fetchMock).toHaveBeenCalledWith('/api/v2/geometry/hole/31795/7/ensure', { method: 'POST' })
    await waitFor(() =>
      expect(fetchMock.mock.calls.filter(([path]) => path === '/api/v2/geometry/hole/31795/7?source_ref=900001%3A7')).toHaveLength(2),
    )
    expect(await screen.findByText('ready coverage')).toBeInTheDocument()
  })

  it('does not let stale geometry ensure responses overwrite a newly selected source', async () => {
    let ensured = false
    let resolveEnsure!: () => void
    const ensureResponse = new Promise<{ ok: boolean; json: () => Promise<ReturnType<typeof geometryEnsurePayload>> }>((resolve) => {
      resolveEnsure = () => {
        ensured = true
        resolve({ ok: true, json: async () => geometryEnsurePayload() })
      }
    })
    const fetchMock = vi.fn(async (path: string, init?: RequestInit) => {
      if (path === '/api/v2/geometry/hole/31795/7/ensure' && init?.method === 'POST') {
        return ensureResponse
      }
      return {
        ok: true,
        json: async () => {
          if (path === '/api/v2/history/stats') return statsPayload()
          if (path === '/api/v2/history/drilldown/900001%3A7') return holeDrilldownPayload()
          if (path === '/api/v2/history/drilldown/900001') return roundDrilldownPayload()
          if (path === '/api/v2/geometry/hole/31795/7?source_ref=900001%3A7') {
            return ensured ? holeGeometryEvidencePayload() : partialHoleGeometryEvidencePayload()
          }
          if (path === '/api/v2/geometry/hole/31795/7/map?provider=esri_world_imagery&source_ref=900001%3A7') return holeMapPayload()
          if (path === '/api/v2/sync/status') return syncStatusPayload()
          return overviewPayload()
        },
      }
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByText('History Overview')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Holes' }))
    expect(await screen.findByRole('heading', { name: 'Hole Stats' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Open source 900001:7' }))
    expect(await screen.findByText('partial coverage')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Fetch geometry for 31795 H7' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/v2/geometry/hole/31795/7/ensure', { method: 'POST' }))
    await userEvent.click(screen.getByRole('button', { name: 'Open source 900001' }))
    expect(await screen.findByText('Black Knight B - 2026-05-18')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Hole Evidence' })).not.toBeInTheDocument()

    await act(async () => {
      resolveEnsure()
      await ensureResponse
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(fetchMock.mock.calls.filter(([path]) => path === '/api/v2/geometry/hole/31795/7?source_ref=900001%3A7')).toHaveLength(1)
    expect(screen.queryByRole('heading', { name: 'Hole Evidence' })).not.toBeInTheDocument()
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
        if (path === '/api/v2/caddie/decisions/fixture-round%3A4%3Aapproach/audit') return caddieAuditPayload()
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
      expect.stringMatching(
        /^\/api\/v2\/caddie\/context\?source_ref=900001%3A7&shot_type=approach&distance_to_pin_m=142&lie=fairway&captured_at=/,
      ),
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
      '/api/v2/caddie/decisions/fixture-round%3A4%3Aapproach/audit',
      expect.objectContaining({ method: 'POST' }),
    )
    const auditPost = fetchMock.mock.calls.find(([path]) => path === '/api/v2/caddie/decisions/fixture-round%3A4%3Aapproach/audit')?.[1] as RequestInit
    const auditBody = JSON.parse(String(auditPost.body))
    expect(auditBody.actualShot).toEqual({
      shotOrder: 1,
      clubName: '9I',
      meters: 137,
      end: { lie: 'fringe', feature: { surface: { kind: 'fringe' }, nearRisks: [] } },
    })
  })

  it('carries a selected history source ref into the caddie context request', async () => {
    const fetchMock = vi.fn(async (path: string) => ({
      ok: true,
      json: async () => {
        if (path === '/api/v2/history/stats') return statsPayload()
        if (path === '/api/v2/history/drilldown/900002%3A5%3A4') return selectedShotDrilldownPayload()
        if (String(path).startsWith('/api/v2/caddie/context')) return caddieContextPayload()
        if (path === '/api/v2/sync/status') return syncStatusPayload()
        return overviewPayload()
      },
    }))
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByText('History Overview')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Clubs' }))
    expect(await screen.findByRole('heading', { name: 'Club Stats' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Open source 900002:5:4' }))

    expect(await screen.findByText('1D on H5')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Caddie' }))
    expect(await screen.findByRole('heading', { name: 'Caddie' })).toBeInTheDocument()
    expect(screen.getByLabelText('Source ref')).toHaveValue('900002:5:4')

    await userEvent.click(screen.getByRole('button', { name: 'Load caddie context' }))

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringMatching(
        /^\/api\/v2\/caddie\/context\?source_ref=900002%3A5%3A4&shot_type=approach&distance_to_pin_m=142&lie=fairway&captured_at=/,
      ),
    )
  })
})
