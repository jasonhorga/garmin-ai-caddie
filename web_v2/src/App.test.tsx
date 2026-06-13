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

function mobileCourseOptionsPayload() {
  return {
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
  }
}

function coursePrepHolePayload(hole: number, par: number, blueYards: number) {
  return {
    hole,
    par,
    par_source: 'courseview',
    blue_yards: blueYards,
    route_len_m: 360,
    route: [],
    geometryCoverage: 'ready',
    sourceRefs: ['course:31795'],
    missingData: [],
    candidateRoutes: [],
    carryTargets: [],
    steps: [],
    cautions: [],
    landing_m: null,
    tee_club: null,
    hazards: { water_carry: [], bunkers: [] },
  }
}

function coursePrepPayload() {
  return {
    schema: 'ai-caddie-course-prep-v1',
    globalId: 31795,
    holeCount: 2,
    clubs: [],
    holes: [coursePrepHolePayload(1, 4, 410), coursePrepHolePayload(2, 5, 520)],
  }
}

function prepTipsPayload() {
  return {
    schema: 'ai-caddie-prep-tips-v1',
    courseKey: 'black_knight',
    tips: [],
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

function roundReportPayload(roundId = '1') {
  return {
    schema: 'ai-caddie-review-report-v1',
    kind: 'round',
    subjectId: roundId,
    sourceRefs: [roundId, `${roundId}:1`],
    provider: 'StaticProvider',
    model: 'static',
    factsUsed: [{ label: 'round_score', source: 'history.round', value: { score: 82 } }],
    missingData: [],
    inferencesMade: [],
    narrative: 'Round review from scorecard facts.',
    confidence: 'high',
  }
}

function courseReportPayload(courseKey = 'black_knight') {
  return {
    schema: 'ai-caddie-review-report-v1',
    kind: 'course',
    subjectId: courseKey,
    sourceRefs: ['900001', '900002'],
    provider: 'StaticProvider',
    model: 'static',
    factsUsed: [{ label: 'course_profile', source: 'history.courses', value: { roundCount: 2 } }],
    missingData: [],
    inferencesMade: [],
    narrative: 'Course review from stored facts.',
    confidence: 'medium',
  }
}

function holeReportPayload(courseKey = 'black_knight', hole = 7) {
  return {
    schema: 'ai-caddie-review-report-v1',
    kind: 'hole',
    subjectId: `${courseKey}:${hole}`,
    sourceRefs: ['900001:7', '900002:7'],
    provider: 'StaticProvider',
    model: 'static',
    factsUsed: [{ label: 'hole_pattern', source: 'history.holes', value: { sampleCount: 2 } }],
    missingData: [],
    inferencesMade: [],
    narrative: 'Hole review from stored facts.',
    confidence: 'medium',
  }
}

function clubReportPayload(clubName = '1D') {
  return {
    schema: 'ai-caddie-review-report-v1',
    kind: 'club',
    subjectId: clubName,
    sourceRefs: ['900001:1:0'],
    provider: 'StaticProvider',
    model: 'static',
    factsUsed: [{ label: 'club_profile', source: 'history.clubs', value: { median: 240 } }],
    missingData: [],
    inferencesMade: [],
    narrative: 'Club review from stored facts.',
    confidence: 'medium',
  }
}

function reportIndexPayload() {
  return {
    schema: 'ai-caddie-review-report-index-v1',
    total: 5,
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
      {
        id: 'course-report',
        storedAt: '2026-05-24T00:00:00Z',
        kind: 'course',
        subjectId: 'black_knight',
        confidence: 'medium',
        provider: 'StaticProvider',
        model: 'static',
        sourceRefs: ['900001', '900002'],
      },
      {
        id: 'hole-report',
        storedAt: '2026-05-23T00:00:00Z',
        kind: 'hole',
        subjectId: 'black_knight:7',
        confidence: 'medium',
        provider: 'StaticProvider',
        model: 'static',
        sourceRefs: ['900001:7', '900002:7'],
      },
      {
        id: 'club-report',
        storedAt: '2026-05-22T00:00:00Z',
        kind: 'club',
        subjectId: '1D',
        confidence: 'medium',
        provider: 'StaticProvider',
        model: 'static',
        sourceRefs: ['900001:1:0'],
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

function caddieAuditLatestPayload() {
  return {
    schema: 'ai-caddie-decision-audit-latest-v1',
    decisionId: 'fixture-round:4:approach',
    record: caddieAuditPayload().record,
  }
}

function weatherPayload() {
  return {
    schema: 'ai-caddie-weather-snapshot-v1',
    state: 'ready',
    source: 'manual',
    roundId: '900001',
    hole: 7,
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
    target: { targetType: 'hole', targetId: '900001:7' },
    media: [
      {
        id: 'media-1',
        createdAt: '2026-05-25T00:00:00Z',
        targetType: 'hole',
        targetId: '900001:7',
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
      targetType: 'hole',
      targetId: '900001:7',
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
    target: { targetType: 'hole', targetId: '900001:7' },
    findings: [
      {
        id: 'finding-1',
        createdAt: '2026-05-25T00:01:00Z',
        targetType: 'hole',
        targetId: '900001:7',
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
    targetType: 'hole',
    targetId: '900001:7',
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

function roundDetailPayload(roundRef = '1') {
  return {
    schema: 'ai-caddie-history-round-detail-v1',
    roundRef,
    requestedRef: roundRef,
    found: true,
    title: 'Black Knight B - 2026-05-20T08:00:00',
    round: {
      id: roundRef,
      courseName: 'Black Knight B',
      score: 82,
      toPar: 10,
      holesScored: 18,
      shotCount: 2,
      coverage: { scorecard: 'ready', shots: 'ready', putts: 'partial' },
      confidence: 'high',
    },
    scorecard: [
      {
        hole: 1,
        par: 4,
        score: 4,
        toPar: 0,
        className: 'par',
        putts: 2,
        gir: true,
        fairway: 'hit',
        holeRef: `${roundRef}:1`,
        shotRefs: [`${roundRef}:1:0`],
        sourceRefs: [`${roundRef}:1`],
        status: 'complete',
      },
    ],
    phaseSummary: [{ phase: 'Tee', state: 'ready', primary: '1/1 fairways', metrics: {} }],
    holeDetails: [{ hole: 1, score: 4, toPar: 0, putts: 2, gir: true, fairway: 'hit', holeRef: `${roundRef}:1`, shotRefs: [`${roundRef}:1:0`] }],
    relatedRefs: { roundRefs: [roundRef], holeRefs: [`${roundRef}:1`], shotRefs: [`${roundRef}:1:0`], sourceRefs: [] },
    sourceFields: { id: roundRef, strokes: 82 },
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
    hole: { number: 7, par: 4, strokes: 5, toPar: 1, globalId: 31795, localHole: 7 },
    shot: null,
    relatedRefs: { roundRefs: ['900001'], holeRefs: ['900001:7'], shotRefs: ['900001:7:0'] },
    sourceFields: { number: 7, strokes: 5 },
    missingData: [],
  }
}

function backNineHoleDrilldownPayload() {
  return {
    schema: 'ai-caddie-history-drilldown-v1',
    ref: '900001:10',
    refType: 'hole',
    found: true,
    title: 'Black Knight B H10',
    round: { id: '900001', score: 77, globalId: 111111, courseName: 'Black Knight B' },
    hole: { number: 10, par: 5, strokes: 5, toPar: 0, globalId: 222222, localHole: 1 },
    shot: null,
    relatedRefs: { roundRefs: ['900001'], holeRefs: ['900001:10'], shotRefs: ['900001:10:0'] },
    sourceFields: { number: 10, strokes: 5, globalId: 222222, localHole: 1 },
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
    vi.unstubAllEnvs()
    vi.restoreAllMocks()
  })

  it('shows the invalid-link page and sends no data requests when a link is required but none is present', async () => {
    vi.stubEnv('VITE_AI_CADDIE_REQUIRE_LINK', 'true')
    vi.stubGlobal('location', { pathname: '/', search: '' })
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByRole('heading', { name: '需要有效链接' })).toBeInTheDocument()
    // A locked-out visitor must leak nothing: no request fires and no player data shows.
    expect(fetchMock).not.toHaveBeenCalled()
    expect(screen.queryByText('想备哪场?')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '概览' })).not.toBeInTheDocument()
  })

  it('shows the invalid-link page when a player link is rejected', async () => {
    vi.stubGlobal('location', { pathname: '/p/bad-token', search: '' })
    const fetchMock = vi.fn(async () => ({ ok: false, status: 401, statusText: 'Unauthorized' }))
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByRole('heading', { name: '需要有效链接' })).toBeInTheDocument()
    // An invalid player link must not fall back to the owner admin-token recovery panel.
    expect(screen.queryByText('历史数据不可用')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('管理令牌')).not.toBeInTheDocument()
  })

  it('loads normally for a valid player link even when a link is required', async () => {
    vi.stubEnv('VITE_AI_CADDIE_REQUIRE_LINK', 'true')
    vi.stubGlobal('location', { pathname: '/p/good-token', search: '' })
    const fetchMock = vi.fn(async (path: string) => {
      if (path === '/api/v2/readiness') return { ok: false, status: 404, statusText: 'Not Found', json: async () => ({}) }
      return {
        ok: true,
        json: async () => {
          if (path === '/api/v2/history/stats' || path === '/api/v2/history/stats?window=last10') return statsPayload()
          if (path === '/api/v2/mobile/courses/options') return mobileCourseOptionsPayload()
          if (path === '/api/v2/sync/status') return syncStatusPayload()
          return overviewPayload()
        },
      }
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByText('想备哪场?')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: '需要有效链接' })).not.toBeInTheDocument()
    // The player token rides on every request as a bearer credential.
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/history/overview', {
      headers: { Authorization: 'Bearer good-token' },
    })
  })

  it('exposes the master spec IA and opens the rounds timeline', async () => {
    const fetchMock = vi.fn(async (path: string) => {
      if (path === '/api/v2/readiness') return { ok: false, status: 404, statusText: 'Not Found', json: async () => ({}) }
      return {
        ok: true,
        json: async () => {
          if (path === '/api/v2/history/rounds?limit=1000') return roundsPayload()
          if (path === '/api/v2/history/stats' || path === '/api/v2/history/stats?window=last10') return statsPayload()
          if (path === '/api/v2/mobile/courses/options') return mobileCourseOptionsPayload()
          if (path === '/api/v2/sync/status') return syncStatusPayload()
          return overviewPayload()
        },
      }
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByText('想备哪场?')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '概览' })).toHaveAttribute('aria-current', 'page')
    ;['概览', '历史', '备战', '实战', '设置'].forEach(
      (label) => expect(screen.getByRole('button', { name: label })).toBeEnabled(),
    )
    expect(screen.queryByRole('button', { name: 'Overview' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Sync & Data Quality' })).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '设置' }))
    expect(await screen.findByText('Garmin CN')).toBeInTheDocument()
    expect(screen.getAllByText('就绪').length).toBeGreaterThan(0)

    await userEvent.click(screen.getByRole('button', { name: '历史' }))
    expect(screen.getByRole('button', { name: '历史' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('button', { name: '概览' })).not.toHaveAttribute('aria-current')
    ;['趋势总览', '球局', '强弱分析', '球场', '报告'].forEach(
      (label) => expect(screen.getByRole('button', { name: label })).toBeEnabled(),
    )
    await userEvent.click(screen.getByRole('button', { name: '球局' }))

    expect(await screen.findByRole('heading', { name: '球局', level: 1 })).toBeInTheDocument()
    expect(screen.getByText('2026年5月')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/history/rounds?limit=1000')
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/sync/status')
    await waitFor(() => expect(screen.queryByText('历史数据不可用')).not.toBeInTheDocument())
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

    expect(await screen.findByRole('heading', { name: '历史数据不可用' })).toBeInTheDocument()
    await userEvent.type(await screen.findByLabelText('管理令牌'), 'admin-secret')
    await userEvent.click(screen.getByRole('button', { name: '重试' }))

    expect(await screen.findByText('想备哪场?')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/history/overview', {
      headers: { 'X-AI-Caddie-Admin-Token': 'admin-secret' },
    })
  })

  it('can retry protected source detail after entering an admin token', async () => {
    const fetchMock = vi.fn(async (path: string, init?: RequestInit) => {
      if (path === '/api/v2/readiness') return { ok: false, status: 404, statusText: 'Not Found', json: async () => ({}) }
      if (path === '/api/v2/history/drilldown/900001%3A1%3A0') {
        if (init?.headers && (init.headers as Record<string, string>)['X-AI-Caddie-Admin-Token'] === 'admin-secret') {
          return {
            ok: true,
            json: async () => drilldownPayload(),
          }
        }
        return {
          ok: false,
          status: 401,
          statusText: 'Unauthorized',
        }
      }
      return {
        ok: true,
        json: async () => {
          if (path === '/api/v2/history/stats' || path === '/api/v2/history/stats?window=last10') return statsPayload()
          if (path === '/api/v2/sync/status') return syncStatusPayload()
          return overviewPayload()
        },
      }
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByText('想备哪场?')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '历史' }))
    await userEvent.click(await screen.findByRole('button', { name: '强弱分析' }))
    await userEvent.click(screen.getByRole('button', { name: 'Open source 900001:1:0' }))

    expect(await screen.findByRole('button', { name: '重试' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '设置' }))
    await userEvent.type(await screen.findByLabelText('管理令牌'), 'admin-secret')
    await userEvent.click(screen.getByRole('button', { name: '重试' }))

    expect(await screen.findByText('1D on H1')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/history/drilldown/900001%3A1%3A0', {
      headers: { 'X-AI-Caddie-Admin-Token': 'admin-secret' },
    })
  })

  it('keeps pasted Garmin session material when the app-level save fails', async () => {
    const fetchMock = vi.fn(async (path: string, init?: RequestInit) => {
      if (path === '/api/v2/sync/garmin/session' && init?.method === 'POST') {
        return {
          ok: false,
          status: 401,
          statusText: 'Unauthorized',
        }
      }
      if (path === '/api/v2/readiness') return { ok: false, status: 404, statusText: 'Not Found', json: async () => ({}) }
      return {
        ok: true,
        json: async () => {
          if (path === '/api/v2/sync/status') return syncStatusPayload()
          return overviewPayload()
        },
      }
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByText('想备哪场?')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '设置' }))
    await userEvent.type(await screen.findByLabelText('网页会话头'), 'Cookie: JWT_WEB=abc123')
    await userEvent.type(screen.getByLabelText('防伪令牌'), 'connect-csrf-token: csrf-secret-value')
    await userEvent.click(screen.getByRole('button', { name: '保存会话' }))

    expect(await screen.findByText('POST /api/v2/sync/garmin/session failed: 401 Unauthorized')).toBeInTheDocument()
    expect(screen.getByLabelText('网页会话头')).toHaveValue('Cookie: JWT_WEB=abc123')
    expect(screen.getByLabelText('防伪令牌')).toHaveValue('connect-csrf-token: csrf-secret-value')
  })

  it('loads history stats once and navigates between stats-backed pages', async () => {
    const fetchMock = vi.fn(async (path: string) => ({
      ok: true,
      json: async () => {
        if (path === '/api/v2/history/stats' || path === '/api/v2/history/stats?window=last10') return statsPayload()
        if (path === '/api/v2/history/drilldown/900001%3A1%3A0') return drilldownPayload()
        if (path === '/api/v2/history/drilldown/900001') return roundDrilldownPayload()
        if (path === '/api/v2/sync/status') return syncStatusPayload()
        return overviewPayload()
      },
    }))
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByText('想备哪场?')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '历史' }))

    expect(await screen.findByText('成绩走势')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/history/stats?window=last10')
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/history/stats')

    await userEvent.click(screen.getByRole('button', { name: '强弱分析' }))

    expect(await screen.findByRole('heading', { name: '你最该练', level: 1 })).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: '按洞' })).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: '按杆' })).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: '问题' })).toBeInTheDocument()
    expect(screen.getByText('1D')).toBeInTheDocument()
    // missing_shots renders via issueLabel in the 问题 section and the 你最该练 fallback
    expect(screen.getAllByText('缺少击球数据').length).toBeGreaterThan(0)
    await userEvent.click(screen.getByRole('button', { name: 'Open source 900001:1:0' }))

    expect(await screen.findByRole('heading', { name: '来源详情' })).toBeInTheDocument()
    expect(screen.getByText('1D on H1')).toBeInTheDocument()
    expect(screen.getByText('geometry')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/history/drilldown/900001%3A1%3A0')
    await userEvent.click(screen.getByRole('button', { name: 'Open source 900001' }))

    expect(await screen.findByText('Black Knight B - 2026-05-18')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/history/drilldown/900001')

    await userEvent.click(screen.getByRole('button', { name: '历史' }))
    await userEvent.click(screen.getByRole('button', { name: '强弱分析' }))

    expect(await screen.findByRole('heading', { name: '问题' })).toBeInTheDocument()
    expect(fetchMock.mock.calls.filter(([path]) => path === '/api/v2/history/stats')).toHaveLength(1)
    expect(fetchMock.mock.calls.filter(([path]) => path === '/api/v2/history/stats?window=last10')).toHaveLength(1)
  })

  it('refetches trends with the newly selected window', async () => {
    const fetchMock = vi.fn(async (path: string) => ({
      ok: true,
      json: async () => {
        if (path === '/api/v2/history/stats' || String(path).startsWith('/api/v2/history/stats?')) return statsPayload()
        if (path === '/api/v2/sync/status') return syncStatusPayload()
        return overviewPayload()
      },
    }))
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByText('想备哪场?')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '历史' }))

    expect(await screen.findByText('成绩走势')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/history/stats?window=last10')
    // The boot 概览 composition already loaded the all-window stats exactly once.
    expect(fetchMock.mock.calls.filter(([path]) => path === '/api/v2/history/stats')).toHaveLength(1)

    await userEvent.click(screen.getByRole('button', { name: '近12个月' }))

    expect(await screen.findByText('成绩走势')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/history/stats?window=12m')

    await userEvent.click(screen.getByRole('button', { name: '全部' }))

    expect(await screen.findByText('成绩走势')).toBeInTheDocument()
    await waitFor(() => expect(fetchMock.mock.calls.filter(([path]) => path === '/api/v2/history/stats')).toHaveLength(2))
  })

  it('去备战 hands the clicked course globalId to the prep page', async () => {
    const fetchMock = vi.fn(async (path: string) => ({
      ok: true,
      json: async () => {
        if (path === '/api/v2/history/stats' || path === '/api/v2/history/stats?window=last10') return statsPayload()
        if (path === '/api/v2/mobile/courses/options') return mobileCourseOptionsPayload()
        if (path === '/api/v2/sync/status') return syncStatusPayload()
        if (path === '/api/v2/courses/31795/prep?include_shots=true') return coursePrepPayload()
        if (path === '/api/v2/courses/31795/prep-tips') return prepTipsPayload()
        return overviewPayload()
      },
    }))
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByText('想备哪场?')).toBeInTheDocument()
    await userEvent.click(await screen.findByRole('button', { name: '去备战 Black Knight B/C' }))

    // PrepPage header resolves the chosen globalId against course options.
    expect(await screen.findByRole('heading', { name: 'Black Knight B/C' })).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/courses/31795/prep?include_shots=true')
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/courses/31795/prep-tips')
    expect(await screen.findByText('Par 9 · 总码数 930 码')).toBeInTheDocument()
    // 你的战绩 joins stats.courses through the option's courseKey.
    expect(screen.getByText('你的战绩:打过 2 次 · 均杆 82')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '逐洞攻略' }))
    expect(screen.getByText('1 洞')).toBeInTheDocument()
    expect(screen.getByText('2 洞')).toBeInTheDocument()
  })

  it('球场 tab renders 球场表现 heading', async () => {
    const fetchMock = vi.fn(async (path: string) => ({
      ok: true,
      json: async () => {
        if (path === '/api/v2/history/stats' || path === '/api/v2/history/stats?window=last10') return statsPayload()
        if (path === '/api/v2/mobile/courses/options') return mobileCourseOptionsPayload()
        if (path === '/api/v2/sync/status') return syncStatusPayload()
        return overviewPayload()
      },
    }))
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByText('想备哪场?')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '历史' }))
    await userEvent.click(await screen.findByRole('button', { name: '球场' }))

    expect(await screen.findByRole('heading', { name: '球场表现', level: 1 })).toBeInTheDocument()
    expect(screen.getByText('Black Knight B')).toBeInTheDocument()
  })

  it('clicking 去备战 on a course row in 球场表现 navigates to the prep page', async () => {
    const fetchMock = vi.fn(async (path: string) => ({
      ok: true,
      json: async () => {
        if (path === '/api/v2/history/stats' || path === '/api/v2/history/stats?window=last10') return statsPayload()
        if (path === '/api/v2/mobile/courses/options') return mobileCourseOptionsPayload()
        if (path === '/api/v2/sync/status') return syncStatusPayload()
        if (path === '/api/v2/courses/31795/prep?include_shots=true') return coursePrepPayload()
        if (path === '/api/v2/courses/31795/prep-tips') return prepTipsPayload()
        return overviewPayload()
      },
    }))
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByText('想备哪场?')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '历史' }))
    await userEvent.click(await screen.findByRole('button', { name: '球场' }))

    // courseOptions maps black_knight → globalId 31795, so the button appears
    await userEvent.click(await screen.findByRole('button', { name: '去备战 Black Knight B' }))

    // PrepPage header resolves 31795 against courseOptions → 'Black Knight B/C'
    expect(await screen.findByRole('heading', { name: 'Black Knight B/C' })).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/courses/31795/prep?include_shots=true')
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/courses/31795/prep-tips')
  })

  it('search-selected course outside course options shows its searched name in the prep header', async () => {
    const fetchMock = vi.fn(async (path: string) => ({
      ok: true,
      json: async () => {
        if (path === '/api/v2/history/stats' || path === '/api/v2/history/stats?window=last10') return statsPayload()
        if (path === '/api/v2/mobile/courses/options') return mobileCourseOptionsPayload()
        if (path === '/api/v2/sync/status') return syncStatusPayload()
        if (path.startsWith('/api/v2/courses/search?')) {
          return {
            schema: 'ai-caddie-course-search-v1',
            query: '观澜湖',
            matches: [{ globalId: 31870, name: '观澜湖·世界杯场', holes: 18, city: '深圳', province: '广东', ratio: 0.92 }],
          }
        }
        if (path === '/api/v2/courses/31870/prep?include_shots=true') return coursePrepPayload()
        if (path === '/api/v2/courses/31870/prep-tips') return prepTipsPayload()
        return overviewPayload()
      },
    }))
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    await userEvent.type(await screen.findByLabelText('搜索球场'), '观澜湖{Enter}')
    await userEvent.click(await screen.findByRole('button', { name: /观澜湖·世界杯场/ }))

    // 31870 is NOT in course options — the header must carry the searched name.
    expect(await screen.findByRole('heading', { name: '观澜湖·世界杯场' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: '球场 31870' })).not.toBeInTheDocument()

    // 换球场 clears the remembered course (and its name) back to the entry state.
    await userEvent.click(screen.getByRole('button', { name: '换球场' }))
    expect(await screen.findByRole('heading', { name: '选择球场开始备战' })).toBeInTheDocument()
  })

  it('discards a stale trends refresh that resolves after the window changed', async () => {
    const twelveMonthStats = {
      ...statsPayload(),
      summary: { totalRounds: 9, average18: 95, bestScore: 81, shotCount: 6 },
    }
    let last10Calls = 0
    let resolveStaleRefresh!: () => void
    const staleRefresh = new Promise<{ ok: boolean; json: () => Promise<unknown> }>((resolve) => {
      resolveStaleRefresh = () => resolve({ ok: true, json: async () => statsPayload() })
    })
    const fetchMock = vi.fn((path: string, init?: RequestInit) => {
      if (path === '/api/v2/history/stats?window=last10') {
        last10Calls += 1
        // The second last10 request is the background refresh kicked off by the
        // sync run; keep it pending so it can resolve after the window changes.
        if (last10Calls > 1) return staleRefresh
        return Promise.resolve({ ok: true, json: async () => statsPayload() })
      }
      if (String(path).startsWith('/api/v2/sync/garmin?') && init?.method === 'POST') {
        return Promise.resolve({ ok: true, json: async () => syncRunPayload() })
      }
      return Promise.resolve({
        ok: true,
        json: async () => {
          if (path === '/api/v2/history/stats?window=12m') return twelveMonthStats
          if (path === '/api/v2/history/stats') return statsPayload()
          if (path === '/api/v2/readiness') return readinessPayload()
          if (path === '/api/v2/mobile/courses/options') return mobileCourseOptionsPayload()
          if (path === '/api/v2/sync/status') return syncStatusCanSyncPayload()
          return overviewPayload()
        },
      })
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByText('想备哪场?')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '历史' }))
    expect(await screen.findByText('成绩走势')).toBeInTheDocument()

    // Kick off a background trends refresh (window=last10) that stays in flight.
    await userEvent.click(screen.getByRole('button', { name: '设置' }))
    await userEvent.click(await screen.findByRole('button', { name: '立即同步' }))
    await waitFor(() =>
      expect(fetchMock.mock.calls.filter(([path]) => path === '/api/v2/history/stats?window=last10')).toHaveLength(2),
    )

    // Switch to 近12个月 while the last10 refresh is still pending.
    await userEvent.click(screen.getByRole('button', { name: '历史' }))
    await userEvent.click(screen.getByRole('button', { name: '近12个月' }))
    const averageCard = (await screen.findByText('均杆(18洞)')).closest('article') as HTMLElement
    expect(within(averageCard).getByText('95')).toBeInTheDocument()

    // The stale last10 refresh resolves late — it must not clobber the 12m view.
    await act(async () => {
      resolveStaleRefresh()
      await staleRefresh
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(screen.getByRole('button', { name: '近12个月' })).toHaveAttribute('aria-pressed', 'true')
    const averageCardAfter = screen.getByText('均杆(18洞)').closest('article') as HTMLElement
    expect(within(averageCardAfter).getByText('95')).toBeInTheDocument()
    expect(within(averageCardAfter).queryByText('82')).not.toBeInTheDocument()
  })

  it('renders loading and error states for deferred history stats', async () => {
    let statsAvailable = false
    let rejectStats: (error: Error) => void = () => {}
    const statsPromise = new Promise<never>((_, reject) => {
      rejectStats = reject
    })
    const fetchMock = vi.fn((path: string) => {
      if (path === '/api/v2/history/stats' || path === '/api/v2/history/stats?window=last10') {
        if (!statsAvailable) return statsPromise
        return Promise.resolve({ ok: true, json: async () => statsPayload() })
      }
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

    expect(await screen.findByText('想备哪场?')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '历史' }))

    expect(await screen.findByRole('heading', { name: '趋势总览加载中' })).toBeInTheDocument()

    await act(async () => {
      rejectStats(new Error('GET /api/v2/history/stats failed: 500 Internal Server Error'))
    })

    expect(await screen.findByRole('heading', { name: '趋势总览加载失败' })).toBeInTheDocument()
    expect(screen.getByText('GET /api/v2/history/stats failed: 500 Internal Server Error')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '重试' })).toBeInTheDocument()
    // The trends page keeps recovery plain — the 去设置 hint lives on the other stats pages.
    expect(screen.queryByText('如需配置访问密钥，请前往 设置 → 同步与数据健康。')).not.toBeInTheDocument()

    // 重试 refetches the windowed stats and renders the trends page.
    statsAvailable = true
    expect(fetchMock.mock.calls.filter(([path]) => path === '/api/v2/history/stats?window=last10')).toHaveLength(1)
    await userEvent.click(screen.getByRole('button', { name: '重试' }))

    expect(await screen.findByText('成绩走势')).toBeInTheDocument()
    expect(fetchMock.mock.calls.filter(([path]) => path === '/api/v2/history/stats?window=last10')).toHaveLength(2)

    await userEvent.click(screen.getByRole('button', { name: '球场' }))

    expect(await screen.findByRole('heading', { name: '历史数据加载失败' })).toBeInTheDocument()
    expect(screen.getByText('如需配置访问密钥，请前往 设置 → 同步与数据健康。')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '去设置' }))

    expect(await screen.findByRole('heading', { name: '同步与数据健康' })).toBeInTheDocument()
    expect(await screen.findByLabelText('管理令牌')).toBeInTheDocument()
  })

  it('rounds error screen offers token recovery via 去设置', async () => {
    const fetchMock = vi.fn(async (path: string) => {
      if (path === '/api/v2/history/rounds?limit=1000') return { ok: false, status: 401, statusText: 'Unauthorized' }
      if (path === '/api/v2/readiness') return { ok: false, status: 404, statusText: 'Not Found', json: async () => ({}) }
      return {
        ok: true,
        json: async () => {
          if (path === '/api/v2/history/stats' || path === '/api/v2/history/stats?window=last10') return statsPayload()
          if (path === '/api/v2/sync/status') return syncStatusPayload()
          return overviewPayload()
        },
      }
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByText('想备哪场?')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '历史' }))
    await userEvent.click(screen.getByRole('button', { name: '球局' }))

    expect(await screen.findByRole('heading', { name: '球局数据不可用' })).toBeInTheDocument()
    expect(screen.getByText('如需配置访问密钥，请前往 设置 → 同步与数据健康。')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '去设置' }))

    expect(await screen.findByRole('heading', { name: '同步与数据健康' })).toBeInTheDocument()
    expect(await screen.findByLabelText('管理令牌')).toBeInTheDocument()
  })

  it('overview failure does not block other sections', async () => {
    const fetchMock = vi.fn(async (path: string) => {
      if (path === '/api/v2/history/overview') return { ok: false, status: 401, statusText: 'Unauthorized' }
      return {
        ok: true,
        json: async () => {
          if (path === '/api/v2/history/rounds?limit=1000') return roundsPayload()
          if (path === '/api/v2/history/stats' || path === '/api/v2/history/stats?window=last10') return statsPayload()
          if (path === '/api/v2/mobile/courses/options') return mobileCourseOptionsPayload()
          if (path === '/api/v2/sync/status') return syncStatusPayload()
          return overviewPayload()
        },
      }
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByRole('heading', { name: '历史数据不可用' })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '实战' }))
    await userEvent.click(screen.getByRole('button', { name: '完整工具' }))
    expect(await screen.findByRole('heading', { name: '智能球童' })).toBeInTheDocument()
    expect(screen.queryByText('历史数据不可用')).toBeNull()

    await userEvent.click(screen.getByRole('button', { name: '概览' }))
    expect(await screen.findByRole('heading', { name: '历史数据不可用' })).toBeInTheDocument()
  })

  it('re-entering 实战 retries boot-failed overview and course options', async () => {
    let bootBroken = true
    const fetchMock = vi.fn(async (path: string) => {
      if (bootBroken && (path === '/api/v2/history/overview' || path === '/api/v2/mobile/courses/options')) {
        return { ok: false, status: 503, statusText: 'Service Unavailable' }
      }
      return {
        ok: true,
        json: async () => {
          if (path === '/api/v2/history/stats' || path === '/api/v2/history/stats?window=last10') return statsPayload()
          if (path === '/api/v2/mobile/courses/options') return mobileCourseOptionsPayload()
          if (path === '/api/v2/history/rounds/1') return roundDetailPayload('1')
          if (path === '/api/v2/sync/status') return syncStatusPayload()
          return overviewPayloadWithRoundRefs()
        },
      }
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)
    expect(await screen.findByRole('heading', { name: '历史数据不可用' })).toBeInTheDocument()

    // 实战 during the outage: the sandbox entry renders, but with no 常打球场
    // card (courseOptions failed) and no replay rows (overview failed).
    await userEvent.click(screen.getByRole('button', { name: '实战' }))
    expect(await screen.findByRole('heading', { name: '选择球场开始模拟' })).toBeInTheDocument()
    expect(screen.queryByText('Black Knight B/C')).not.toBeInTheDocument()

    // Backend recovers → tapping 实战 again retries BOTH boot failures the
    // way 概览/备战 already do (options reload + keep-ready overview refresh).
    bootBroken = false
    await userEvent.click(screen.getByRole('button', { name: '实战' }))
    expect(await screen.findByText('Black Knight B/C')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '最近回放' }))
    expect(await screen.findByRole('button', { name: '回放 Black Knight B 05-20' })).toBeInTheDocument()
  })

  it('备战 with no chosen course shows the entry finder without prep fetches', async () => {
    const fetchMock = vi.fn(async (path: string) => ({
      ok: true,
      json: async () => {
        if (path === '/api/v2/history/stats') return statsPayload()
        if (path === '/api/v2/mobile/courses/options') return mobileCourseOptionsPayload()
        if (path === '/api/v2/sync/status') return syncStatusPayload()
        return overviewPayload()
      },
    }))
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByText('想备哪场?')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '备战' }))

    expect(await screen.findByRole('heading', { name: '选择球场开始备战' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '去备战 Black Knight B/C' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '趋势总览' })).toBeNull()
    expect(fetchMock.mock.calls.some(([path]) => String(path).includes('/prep'))).toBe(false)
  })

  it('opens source detail directly from overview and rounds cards', async () => {
    const fetchMock = vi.fn(async (path: string) => ({
      ok: true,
      json: async () => {
        if (path === '/api/v2/history/rounds?limit=1000') return roundsPayload()
        if (path === '/api/v2/history/rounds/1') return roundDetailPayload('1')
        if (path === '/api/v2/reports/round/1') return roundReportPayload('1')
        if (path === '/api/v2/reports/round/1/generate') return roundReportPayload('1')
        if (path === '/api/v2/history/drilldown/1%3A1') return overviewHoleDrilldownPayload()
        if (path === '/api/v2/history/drilldown/1') return overviewRoundDrilldownPayload()
        if (path === '/api/v2/history/stats' || path === '/api/v2/history/stats?window=last10') return statsPayload()
        if (path === '/api/v2/mobile/courses/options') return mobileCourseOptionsPayload()
        if (path === '/api/v2/sync/status') return syncStatusPayload()
        return overviewPayloadWithRoundRefs()
      },
    }))
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByText('想备哪场?')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '看复盘 →' }))

    expect(await screen.findByRole('heading', { name: '球局回顾' })).toBeInTheDocument()
    expect(screen.getAllByText('Black Knight B').length).toBeGreaterThan(0)
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/history/rounds/1')
    await userEvent.click(screen.getByRole('button', { name: '载入 AI 回顾' }))

    expect(await screen.findByText('Round review from scorecard facts.')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/reports/round/1')
    await userEvent.click(screen.getByRole('button', { name: '生成 AI 回顾' }))

    expect(fetchMock).toHaveBeenCalledWith('/api/v2/reports/round/1/generate', { method: 'POST' })
    await userEvent.click(screen.getAllByRole('button', { name: 'Open source 1:1' })[0])

    expect(await screen.findByText('Black Knight B H1')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/history/drilldown/1%3A1')

    await userEvent.click(screen.getByRole('button', { name: '历史' }))
    await userEvent.click(screen.getByRole('button', { name: '球局' }))
    expect(await screen.findByRole('heading', { name: '球局', level: 1 })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '打开球局 Black Knight B, 2026-05-20T08:00:00, score 82, ref 1' }))

    expect(fetchMock.mock.calls.filter(([path]) => path === '/api/v2/history/rounds/1')).toHaveLength(2)
  })

  it('shows corrections history and adds a club correction from the response', async () => {
    const fetchMock = vi.fn(async (path: string, init?: RequestInit) => {
      if (path === '/api/v2/readiness') return { ok: false, status: 404, statusText: 'Not Found', json: async () => ({}) }
      return {
        ok: true,
        json: async () => {
          if (path === '/api/v2/annotations' && init?.method === 'POST') return createdAnnotationPayload()
          if (path === '/api/v2/annotations') return annotationsPayload()
          if (path === '/api/v2/sync/status') return syncStatusPayload()
          return overviewPayload()
        },
      }
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByText('想备哪场?')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '设置' }))
    await userEvent.click(await screen.findByRole('button', { name: '订正' }))

    expect(await screen.findByRole('heading', { name: '订正' })).toBeInTheDocument()
    const history = screen.getByLabelText('批注历史')
    expect(within(history).getByText('round-1:7:shot-3')).toBeInTheDocument()
    expect(within(history).getByText('球杆订正')).toBeInTheDocument()
    expect(within(history).getByText('7I → 8I')).toBeInTheDocument()
    expect(within(history).getByText('approach_short')).toBeInTheDocument()
    expect(screen.getByRole('option', { name: '球杆订正' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: '推杆订正' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: '问题标签' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: '备注' })).toBeInTheDocument()

    await userEvent.selectOptions(screen.getByLabelText('目标类型'), 'shot')
    await userEvent.clear(screen.getByLabelText('目标编号'))
    await userEvent.type(screen.getByLabelText('目标编号'), 'round-1:8:shot-1')
    await userEvent.selectOptions(screen.getByLabelText('订正类型'), 'club_correction')
    await userEvent.type(screen.getByLabelText('原记录球杆'), '7I')
    await userEvent.type(screen.getByLabelText('订正后球杆'), '8I')
    await userEvent.type(screen.getByLabelText('备注'), 'Trackman confirmed the club')
    await userEvent.click(screen.getByRole('button', { name: '保存批注' }))

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
    expect(screen.getAllByText('7I → 8I')).toHaveLength(2)
    expect(screen.getByText('Trackman confirmed the club')).toBeInTheDocument()
  })

  it('opens contextual corrections from source drilldown with the target prefilled', async () => {
    const fetchMock = vi.fn(async (path: string, init?: RequestInit) => ({
      ok: true,
      json: async () => {
        if (path === '/api/v2/history/rounds/1') return roundDetailPayload('1')
        if (path === '/api/v2/history/stats') return statsPayload()
        if (path === '/api/v2/mobile/courses/options') return mobileCourseOptionsPayload()
        if (path === '/api/v2/annotations') return annotationsPayload()
        if (path === '/api/v2/sync/status') return syncStatusPayload()
        if (path === '/api/v2/annotations' && init?.method === 'POST') return createdAnnotationPayload()
        return overviewPayloadWithRoundRefs()
      },
    }))
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByText('想备哪场?')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '看复盘 →' }))
    expect(await screen.findByRole('heading', { name: '球局回顾' })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Add correction for round 1' }))

    expect(await screen.findByRole('heading', { name: '订正' })).toBeInTheDocument()
    expect(screen.getByLabelText('目标类型')).toHaveValue('round')
    expect(screen.getByLabelText('目标编号')).toHaveValue('1')
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/annotations')
  })

  it('loads API-backed settings state when opening settings', async () => {
    const fetchMock = vi.fn(async (path: string) => {
      if (path === '/api/v2/readiness') return { ok: false, status: 404, statusText: 'Not Found', json: async () => ({}) }
      return {
        ok: true,
        json: async () => {
          if (path === '/api/v2/settings/product') return productSettingsPayload()
          if (path === '/api/v2/sync/status') return syncStatusPayload()
          return overviewPayload()
        },
      }
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByText('想备哪场?')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '设置' }))
    await userEvent.click(await screen.findByRole('button', { name: '后端配置' }))

    expect(await screen.findByRole('heading', { name: '后端配置' })).toBeInTheDocument()
    expect(await screen.findByText('当前:Gemini API')).toHaveClass('setting-primary')
    expect(screen.getByText('可用')).toHaveClass('setting-primary')
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/settings/product')
  })

  it('refreshes loaded history stats after creating a correction', async () => {
    const fetchMock = vi.fn(async (path: string, init?: RequestInit) => {
      if (path === '/api/v2/readiness') return { ok: false, status: 404, statusText: 'Not Found', json: async () => ({}) }
      return {
        ok: true,
        json: async () => {
          if (path === '/api/v2/history/stats' || path === '/api/v2/history/stats?window=last10') return statsPayload()
          if (path === '/api/v2/annotations' && init?.method === 'POST') return createdAnnotationPayload()
          if (path === '/api/v2/annotations') return annotationsPayload()
          if (path === '/api/v2/sync/status') return syncStatusPayload()
          return overviewPayload()
        },
      }
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByText('想备哪场?')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '历史' }))
    expect(await screen.findByText('成绩走势')).toBeInTheDocument()
    expect(fetchMock.mock.calls.filter(([path]) => path === '/api/v2/history/stats')).toHaveLength(1)

    await userEvent.click(screen.getByRole('button', { name: '设置' }))
    await userEvent.click(await screen.findByRole('button', { name: '后端配置' }))
    await userEvent.click(screen.getByRole('button', { name: '打开订正' }))
    expect(await screen.findByRole('heading', { name: '订正' })).toBeInTheDocument()

    await userEvent.selectOptions(screen.getByLabelText('目标类型'), 'shot')
    await userEvent.clear(screen.getByLabelText('目标编号'))
    await userEvent.type(screen.getByLabelText('目标编号'), 'round-1:8:shot-1')
    await userEvent.selectOptions(screen.getByLabelText('订正类型'), 'club_correction')
    await userEvent.type(screen.getByLabelText('原记录球杆'), '7I')
    await userEvent.type(screen.getByLabelText('订正后球杆'), '8I')
    await userEvent.click(screen.getByRole('button', { name: '保存批注' }))

    await waitFor(() => expect(fetchMock.mock.calls.filter(([path]) => path === '/api/v2/history/stats')).toHaveLength(2))
  })

  it('opens the reports workspace and loads a trend report', async () => {
    const fetchMock = vi.fn(async (path: string) => ({
      ok: true,
      json: async () => {
        if (path === '/api/v2/history/stats' || path === '/api/v2/history/stats?window=last10') return statsPayload()
        if (path === '/api/v2/reports') return reportIndexPayload()
        if (path === '/api/v2/reports/trend/recent_10') return trendReportPayload()
        if (path === '/api/v2/reports/course/black_knight') return courseReportPayload()
        if (path === '/api/v2/reports/hole/black_knight/7') return holeReportPayload()
        if (path === '/api/v2/reports/club/1D') return clubReportPayload()
        if (path === '/api/v2/sync/status') return syncStatusPayload()
        return overviewPayload()
      },
    }))
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByText('想备哪场?')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '历史' }))
    await userEvent.click(screen.getByRole('button', { name: '报告' }))

    expect(await screen.findByRole('heading', { name: '报告' })).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: '报告索引' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '打开已存 趋势 recent_10' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '打开已存 球场 black_knight' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Black Knight B' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Black Knight B H7' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: '1D' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '载入趋势报告' }))
    await userEvent.click(screen.getByRole('button', { name: '打开已存 趋势 recent_10' }))
    expect(await screen.findByText('Trend review from stored facts.')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '载入球场报告' }))
    expect(await screen.findByText('Course review from stored facts.')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '载入球洞报告' }))
    expect(await screen.findByText('Hole review from stored facts.')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '载入球杆报告' }))

    expect(await screen.findByText('Club review from stored facts.')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/history/stats')
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/reports')
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/reports/trend/recent_10')
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/reports/course/black_knight')
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/reports/hole/black_knight/7')
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/reports/club/1D')
  })

  it('drills from a loaded report source ref to source detail', async () => {
    const fetchMock = vi.fn(async (path: string) => ({
      ok: true,
      json: async () => {
        if (path === '/api/v2/history/stats' || path === '/api/v2/history/stats?window=last10') return statsPayload()
        if (path === '/api/v2/reports') return reportIndexPayload()
        if (path === '/api/v2/reports/trend/recent_10') return trendReportPayload()
        if (path === '/api/v2/history/drilldown/900001') return roundDrilldownPayload()
        if (path === '/api/v2/sync/status') return syncStatusPayload()
        return overviewPayload()
      },
    }))
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByText('想备哪场?')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '历史' }))
    await userEvent.click(screen.getByRole('button', { name: '报告' }))
    await userEvent.click(await screen.findByRole('button', { name: '载入趋势报告' }))
    const identity = await screen.findByLabelText('报告信息')
    await userEvent.click(within(identity).getByRole('button', { name: 'Open source 900001' }))

    expect(await screen.findByRole('heading', { name: '来源详情' })).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/history/drilldown/900001')
  })

  it('opens the sync and data quality workspace, prepares a mobile package, and applies reconciliation suggestions', async () => {
    const fetchMock = vi.fn(async (path: string, init?: RequestInit) => ({
      ok: true,
      json: async () => {
        if (path === '/api/v2/history/stats' || path === '/api/v2/history/stats?window=last10') return statsPayload()
        if (path === '/api/v2/sync/status') return syncStatusPayload()
        if (path === '/api/v2/readiness') return readinessPayload()
        if (path === '/api/v2/mobile/courses/31795/package?round_id=live-black-knight&tee_box=blue&ensure_geometry=true') return mobilePackagePayload()
        if (path === '/api/v2/mobile/rounds/900001/reconciliation') return mobileReconciliationPayload()
        if (path === '/api/v2/mobile/rounds/900001/reconciliation/apply' && init?.method === 'POST') {
          return mobileReconciliationApplyPayload()
        }
        return overviewPayload()
      },
    }))
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByText('想备哪场?')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '设置' }))

    expect(await screen.findByRole('heading', { name: '同步与数据健康' })).toBeInTheDocument()
    expect(screen.getByText('Garmin CN')).toBeInTheDocument()
    expect(screen.getAllByText('本地 Garmin 快照已就绪。').length).toBeGreaterThan(0)
    expect(screen.getByRole('heading', { name: '试运行就绪度' })).toBeInTheDocument()
    expect(screen.getByText('dataMode: fixture')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '数据健康' })).toBeInTheDocument()
    // dataQuality finding labels render through the zh dictionary, never raw
    expect(screen.getByText('击球数据')).toBeInTheDocument()
    expect(screen.queryByText('shots')).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '离线包准备' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '离线对账' })).toBeInTheDocument()

    await userEvent.type(screen.getByLabelText('管理令牌'), 'admin-secret')
    await userEvent.click(screen.getByRole('radio', { name: '球场' }))
    await userEvent.clear(screen.getByLabelText('球场全局编号'))
    await userEvent.type(screen.getByLabelText('球场全局编号'), '31795')
    await userEvent.type(screen.getByLabelText('实战球局编号'), 'live-black-knight')
    await userEvent.type(screen.getByLabelText('发球台'), 'blue')
    await userEvent.click(screen.getByRole('button', { name: '生成离线包' }))
    expect(await screen.findByText('Fixture Links')).toBeInTheDocument()
    expect(screen.getByText('12/18 洞')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '核对离线事件' }))
    expect(await screen.findByText('Local score input can correct the derived score for this hole.')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '应用所选建议' }))
    expect(await screen.findByText('已应用 1 条建议')).toBeInTheDocument()

    await waitFor(() => expect(fetchMock.mock.calls.filter(([path]) => path === '/api/v2/history/stats')).toHaveLength(2))
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/readiness')
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/mobile/courses/31795/package?round_id=live-black-knight&tee_box=blue&ensure_geometry=true', {
      headers: { 'X-AI-Caddie-Admin-Token': 'admin-secret' },
    })
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/mobile/rounds/900001/reconciliation', {
      headers: { 'X-AI-Caddie-Admin-Token': 'admin-secret' },
    })
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
          if (path === '/api/v2/history/stats' || path === '/api/v2/history/stats?window=last10') return statsPayload()
          if (path === '/api/v2/readiness') return readinessPayload()
          if (path === '/api/v2/mobile/courses/31795/package?round_id=live-black-knight&ensure_geometry=true') return mobilePackagePayload()
          return overviewPayload()
        },
      }
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByText('想备哪场?')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '设置' }))

    expect(await screen.findByRole('heading', { name: '离线包准备' })).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('管理令牌'), 'admin-secret')
    await userEvent.click(screen.getByRole('radio', { name: '球场' }))
    await userEvent.clear(screen.getByLabelText('球场全局编号'))
    await userEvent.type(screen.getByLabelText('球场全局编号'), '31795')
    await userEvent.type(screen.getByLabelText('实战球局编号'), 'live-black-knight')
    await userEvent.click(screen.getByRole('button', { name: '生成离线包' }))

    expect(await screen.findByText('Fixture Links')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/mobile/courses/31795/package?round_id=live-black-knight&ensure_geometry=true', {
      headers: { 'X-AI-Caddie-Admin-Token': 'admin-secret' },
    })
  })

  it('reloads protected mobile course options after the admin token is entered', async () => {
    const fetchMock = vi.fn(async (path: string, init?: RequestInit) => {
      if (path === '/api/v2/mobile/courses/options' && !init) {
        return { ok: false, status: 401, statusText: 'Unauthorized', json: async () => ({}) }
      }
      return {
        ok: true,
        json: async () => {
          if (path === '/api/v2/history/stats' || path === '/api/v2/history/stats?window=last10') return statsPayload()
          if (path === '/api/v2/sync/status') return syncStatusPayload()
          if (path === '/api/v2/readiness') return readinessPayload()
          if (path === '/api/v2/mobile/courses/options') return mobileCourseOptionsPayload()
          return overviewPayload()
        },
      }
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByText('想备哪场?')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '设置' }))
    await userEvent.click(screen.getByRole('radio', { name: '球场' }))

    expect(await screen.findByText('球场选项不可用:GET /api/v2/mobile/courses/options failed: 401 Unauthorized')).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('管理令牌'), 'admin-secret')

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith('/api/v2/mobile/courses/options', {
        headers: { 'X-AI-Caddie-Admin-Token': 'admin-secret' },
      }),
    )
    expect(await screen.findByLabelText('最近球场')).toBeInTheDocument()
  })

  it('refreshes loaded history stats after Garmin sync completes', async () => {
    const fetchMock = vi.fn(async (path: string, init?: RequestInit) => {
      if (path === '/api/v2/readiness') return { ok: false, status: 404, statusText: 'Not Found', json: async () => ({}) }
      return {
        ok: true,
        json: async () => {
          if (path === '/api/v2/history/stats' || path === '/api/v2/history/stats?window=last10') return statsPayload()
          if (path === '/api/v2/sync/status') return syncStatusCanSyncPayload()
          if (String(path).startsWith('/api/v2/sync/garmin?') && init?.method === 'POST') return syncRunPayload()
          return overviewPayload()
        },
      }
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByText('想备哪场?')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '历史' }))
    expect(await screen.findByText('成绩走势')).toBeInTheDocument()
    expect(fetchMock.mock.calls.filter(([path]) => path === '/api/v2/history/stats')).toHaveLength(1)

    await userEvent.click(screen.getByRole('button', { name: '设置' }))
    await userEvent.click(await screen.findByRole('button', { name: '立即同步' }))

    expect(fetchMock).toHaveBeenCalledWith('/api/v2/sync/garmin?with_shots=true&force_refresh_auth=false', { method: 'POST' })
    await waitFor(() => expect(fetchMock.mock.calls.filter(([path]) => path === '/api/v2/history/stats')).toHaveLength(2))
  })

  it('loads hole geometry evidence after selecting a hole source ref', async () => {
    const fetchMock = vi.fn(async (path: string) => ({
      ok: true,
      json: async () => {
        if (path === '/api/v2/history/stats' || path === '/api/v2/history/stats?window=last10') return statsPayload()
        if (path === '/api/v2/history/drilldown/900001%3A7') return holeDrilldownPayload()
        if (path === '/api/v2/geometry/hole/31795/7?source_ref=900001%3A7') return holeGeometryEvidencePayload()
        if (path === '/api/v2/geometry/hole/31795/7/map?provider=esri_world_imagery&source_ref=900001%3A7') return holeMapPayload()
        if (path === '/api/v2/sync/status') return syncStatusPayload()
        return overviewPayload()
      },
    }))
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByText('想备哪场?')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '历史' }))
    await userEvent.click(screen.getByRole('button', { name: '强弱分析' }))
    expect(await screen.findByRole('heading', { name: '按洞' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Open source 900001:7' }))

    expect(await screen.findByRole('heading', { name: '来源详情' })).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: '洞口几何证据' })).toBeInTheDocument()
    expect(screen.getByText('31795 H7')).toBeInTheDocument()
    expect(screen.getByText('Vector geometry overlay')).toBeInTheDocument()
    expect(screen.getByText('source Esri World Imagery / WGS84')).toBeInTheDocument()
    expect(screen.getByText('pin')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/history/drilldown/900001%3A7')
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/geometry/hole/31795/7?source_ref=900001%3A7')
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/geometry/hole/31795/7/map?provider=esri_world_imagery&source_ref=900001%3A7')
  })

  it('uses hole-level geometry target for split back-nine source refs', async () => {
    const fetchMock = vi.fn(async (path: string) => ({
      ok: true,
      json: async () => {
        if (path === '/api/v2/history/stats' || path === '/api/v2/history/stats?window=last10') {
          return {
            ...statsPayload(),
            holes: [{ courseKey: 'split_geometry', hole: 10, sampleCount: 1, averageToPar: 0, worstToPar: 0, refs: ['900001:10'] }],
          }
        }
        if (path === '/api/v2/history/drilldown/900001%3A10') return backNineHoleDrilldownPayload()
        if (path === '/api/v2/geometry/hole/222222/1?source_ref=900001%3A10') return { ...holeGeometryEvidencePayload(), globalId: 222222, localHole: 1, sourceRef: '900001:10' }
        if (path === '/api/v2/geometry/hole/222222/1/map?provider=esri_world_imagery&source_ref=900001%3A10') return { ...holeMapPayload(), globalId: 222222, localHole: 1 }
        if (path === '/api/v2/sync/status') return syncStatusPayload()
        return overviewPayload()
      },
    }))
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByText('想备哪场?')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '历史' }))
    await userEvent.click(screen.getByRole('button', { name: '强弱分析' }))
    expect(await screen.findByRole('heading', { name: '按洞' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Open source 900001:10' }))

    expect(await screen.findByText('222222 H1')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/geometry/hole/222222/1?source_ref=900001%3A10')
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/geometry/hole/222222/1/map?provider=esri_world_imagery&source_ref=900001%3A10')
  })

  it('ensures missing hole geometry and refreshes evidence', async () => {
    let ensured = false
    const fetchMock = vi.fn(async (path: string, init?: RequestInit) => ({
      ok: true,
      json: async () => {
        if (path === '/api/v2/history/stats' || path === '/api/v2/history/stats?window=last10') return statsPayload()
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

    expect(await screen.findByText('想备哪场?')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '历史' }))
    await userEvent.click(screen.getByRole('button', { name: '强弱分析' }))
    expect(await screen.findByRole('heading', { name: '按洞' })).toBeInTheDocument()
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
          if (path === '/api/v2/history/stats' || path === '/api/v2/history/stats?window=last10') return statsPayload()
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

    expect(await screen.findByText('想备哪场?')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '历史' }))
    await userEvent.click(screen.getByRole('button', { name: '强弱分析' }))
    expect(await screen.findByRole('heading', { name: '按洞' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Open source 900001:7' }))
    expect(await screen.findByText('partial coverage')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Fetch geometry for 31795 H7' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/v2/geometry/hole/31795/7/ensure', { method: 'POST' }))
    await userEvent.click(screen.getByRole('button', { name: 'Open source 900001' }))
    expect(await screen.findByText('Black Knight B - 2026-05-18')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: '洞口几何证据' })).not.toBeInTheDocument()

    await act(async () => {
      resolveEnsure()
      await ensureResponse
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(fetchMock.mock.calls.filter(([path]) => path === '/api/v2/geometry/hole/31795/7?source_ref=900001%3A7')).toHaveLength(1)
    expect(screen.queryByRole('heading', { name: '洞口几何证据' })).not.toBeInTheDocument()
  })

  it('opens the caddie workspace, attaches media context, and requests a decision', async () => {
    const fetchMock = vi.fn(async (path: string, init?: RequestInit) => ({
      ok: true,
      json: async () => {
        if (path === '/api/v2/media' && init?.method === 'POST') return createdMediaPayload()
        if (path === '/api/v2/media/target/hole/900001%3A7') return mediaListPayload()
        if (path === '/api/v2/media/media-1/analyze' && init?.method === 'POST') return visionAnalysisPayload()
        if (path === '/api/v2/media/target/hole/900001%3A7/findings') return visionFindingsPayload()
        if (String(path).startsWith('/api/v2/caddie/context')) return caddieContextPayload()
        if (path === '/api/v2/caddie/decision') return caddieDecisionPayload()
        if (path === '/api/v2/caddie/decisions/fixture-round%3A4%3Aapproach/audit/latest') return caddieAuditLatestPayload()
        if (path === '/api/v2/caddie/decisions/fixture-round%3A4%3Aapproach/audit') return caddieAuditPayload()
        if (String(path).startsWith('/api/v2/weather/snapshot')) return weatherPayload()
        if (path === '/api/v2/sync/status') return syncStatusPayload()
        return overviewPayload()
      },
    }))
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByText('想备哪场?')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '实战' }))
    // 实战 lands on the LivePage 决策沙盘 entry; the legacy dashboard sits
    // verbatim behind 完整工具.
    expect(await screen.findByRole('heading', { name: '选择球场开始模拟' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '完整工具' }))
    expect(await screen.findByRole('heading', { name: '智能球童' })).toBeInTheDocument()
    // The 备战 page (entry finder heading) must not leak into the 实战 workspace.
    expect(screen.queryByRole('heading', { name: '选择球场开始备战' })).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '加载天气' }))
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

    await userEvent.click(screen.getByRole('button', { name: '请求球童方案' }))

    expect(await screen.findByText('8I')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringMatching(
        /^\/api\/v2\/weather\/snapshot\?source=manual&persist=true&round_id=900001&hole=7&captured_at=/,
      ),
    )
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringMatching(
        /^\/api\/v2\/caddie\/context\?source_ref=900001%3A7&shot_type=approach&distance_to_pin_m=142&lie=fairway&captured_at=/,
      ),
    )
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/media/target/hole/900001%3A7')
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/media/target/hole/900001%3A7/findings')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v2/media',
      expect.objectContaining({
        method: 'POST',
        body: expect.stringContaining('"contentBase64":"bmV3LWxpZS1ieXRlcw=="'),
      }),
    )
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/caddie/decision', expect.objectContaining({ method: 'POST' }))
    expect(await screen.findByText('Latest decision audit')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/caddie/decisions/fixture-round%3A4%3Aapproach/audit/latest')
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
    expect(auditBody.actualShots).toEqual([
      {
        shotOrder: 1,
        clubName: '9I',
        meters: 137,
        end: { lie: 'fringe', feature: { surface: { kind: 'fringe' }, nearRisks: [] } },
      },
    ])
    expect(auditBody.penalty).toBe(false)
  })

  it('carries a selected history source ref into the caddie context request', async () => {
    const fetchMock = vi.fn(async (path: string) => ({
      ok: true,
      json: async () => {
        if (path === '/api/v2/history/stats' || path === '/api/v2/history/stats?window=last10') return statsPayload()
        if (path === '/api/v2/history/drilldown/900002%3A5%3A4') return selectedShotDrilldownPayload()
        if (String(path).startsWith('/api/v2/caddie/context')) return caddieContextPayload()
        if (path === '/api/v2/sync/status') return syncStatusPayload()
        return overviewPayload()
      },
    }))
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByText('想备哪场?')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '历史' }))
    await userEvent.click(screen.getByRole('button', { name: '强弱分析' }))
    expect(await screen.findByRole('heading', { name: '按杆' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Open source 900002:5:4' }))

    expect(await screen.findByText('1D on H5')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '实战' }))
    await userEvent.click(screen.getByRole('button', { name: '完整工具' }))
    expect(await screen.findByRole('heading', { name: '智能球童' })).toBeInTheDocument()
    expect(screen.getByLabelText('Source ref')).toHaveValue('900002:5:4')

    await userEvent.click(screen.getByRole('button', { name: 'Load caddie context' }))

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringMatching(
        /^\/api\/v2\/caddie\/context\?source_ref=900002%3A5%3A4&shot_type=approach&distance_to_pin_m=142&lie=fairway&captured_at=/,
      ),
    )
  })

  it('最近回放 replays a recent round and reuses the app drilldown + AI review plumbing', async () => {
    const fetchMock = vi.fn(async (path: string) => ({
      ok: true,
      json: async () => {
        if (path === '/api/v2/history/rounds/1') return roundDetailPayload('1')
        if (path === '/api/v2/reports/round/1') return roundReportPayload('1')
        if (path === '/api/v2/history/drilldown/1%3A1') return overviewHoleDrilldownPayload()
        if (path === '/api/v2/history/stats' || path === '/api/v2/history/stats?window=last10') return statsPayload()
        if (path === '/api/v2/mobile/courses/options') return mobileCourseOptionsPayload()
        if (path === '/api/v2/sync/status') return syncStatusPayload()
        return overviewPayloadWithRoundRefs()
      },
    }))
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByText('想备哪场?')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '实战' }))
    // The replay detail stays lazy until the 最近回放 tab actually opens.
    expect(fetchMock.mock.calls.some(([path]) => path === '/api/v2/history/rounds/1')).toBe(false)
    await userEvent.click(screen.getByRole('button', { name: '最近回放' }))

    expect(await screen.findByRole('heading', { name: '球局回顾' })).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/history/rounds/1')
    expect(screen.getByRole('button', { name: '回放 Black Knight B 05-20' })).toHaveAttribute('aria-current', 'true')

    // AI review buttons run through App's report plumbing, as on history pages.
    await userEvent.click(screen.getByRole('button', { name: '载入 AI 回顾' }))
    expect(await screen.findByText('Round review from scorecard facts.')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/reports/round/1')

    // Scorecard refs open the same drilldown panel as on history pages, below LivePage.
    await userEvent.click(screen.getByRole('button', { name: 'Open hole 1 detail 1:1' }))
    expect(await screen.findByText('Black Knight B H1')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/history/drilldown/1%3A1')
  })
})
