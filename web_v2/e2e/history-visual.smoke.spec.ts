import { readFileSync } from 'node:fs'

import { expect, test, type Page, type TestInfo } from '@playwright/test'

const overviewPayload = {
  schema: 'ai-caddie-history-overview-v2',
  metrics: {
    totalRounds: 12,
    eighteenHoleRounds: 10,
    nineHoleRounds: 2,
    courseCount: 4,
    shotCount: 612,
    average18: 82.4,
    recent10Average: 80.9,
    bestScore: 76,
  },
  recentRounds: [
    {
      id: '900001',
      date: '2026-05-20T08:00:00',
      courseName: 'Black Knight B',
      courseKey: 'black_knight',
      holesCompleted: 18,
      score: 78,
      par: 72,
      toPar: 6,
      primaryIssue: 'approach_short',
      badges: [{ label: 'shots', state: 'good', value: '100%', reason: 'all shot rows loaded' }],
      scoreStrip: [
        { hole: 1, par: 4, score: 4, toPar: 0, className: 'par' },
        { hole: 2, par: 5, score: 4, toPar: -1, className: 'birdie' },
        { hole: 3, par: 3, score: 3, toPar: 0, className: 'par' },
        { hole: 4, par: 4, score: 5, toPar: 1, className: 'bogey' },
        { hole: 5, par: 4, score: 4, toPar: 0, className: 'par' },
        { hole: 6, par: 5, score: 5, toPar: 0, className: 'par' },
        { hole: 7, par: 4, score: 6, toPar: 2, className: 'double' },
        { hole: 8, par: 3, score: 3, toPar: 0, className: 'par' },
        { hole: 9, par: 4, score: 4, toPar: 0, className: 'par' },
      ],
    },
  ],
  distribution: {
    total: 12,
    average: 82.4,
    best: 76,
    worst: 91,
    families: [
      { label: '70s', count: 3, pct: 25, className: 'birdie', roundRefs: ['900001'] },
      { label: '80s', count: 7, pct: 58.3, className: 'par', roundRefs: ['900002'] },
      { label: '90s', count: 2, pct: 16.7, className: 'bogey', roundRefs: ['900003'] },
    ],
    histogram: [
      { label: '75-79', start: 75, count: 3, roundRefs: ['900001'] },
      { label: '80-84', start: 80, count: 4, roundRefs: ['900002'] },
      { label: '85-89', start: 85, count: 3, roundRefs: ['900004'] },
      { label: '90-94', start: 90, count: 2, roundRefs: ['900003'] },
    ],
  },
  dataQuality: [
    { label: 'shots', state: 'good', value: '100%', reason: '12/12 scorecards have shot files' },
    { label: 'geometry', state: 'partial', value: '67%', reason: '8/12 rounds have hole geometry' },
  ],
  emptyState: null,
}

const roundsPayload = {
  schema: 'ai-caddie-history-rounds-v2',
  total: 2,
  groups: [
    {
      key: '2026-05',
      label: 'May 2026',
      count: 2,
      average18: 80.5,
      bestScore: 78,
      rounds: overviewPayload.recentRounds,
    },
  ],
  emptyState: null,
}

const statsPayload = {
  schema: 'ai-caddie-history-stats-v1',
  dataMode: 'fixture',
  summary: {
    totalRounds: 12,
    eighteenHoleRounds: 10,
    nineHoleRounds: 2,
    mergedRounds: 1,
    courseCount: 4,
    average18: 82.4,
    median18: 82,
    recent5Average: 79.8,
    recent10Average: 80.9,
    recent20Average: 82.4,
    bestScore: 76,
    worstScore: 91,
    shotCount: 612,
    handicapEstimate: 14.2,
    handicapTrend: -0.8,
  },
  time: {
    byYear: [{ key: '2026', roundCount: 12, average18: 82.4, bestScore: 76, roundIds: ['900001', '900002'] }],
    byQuarter: [{ key: '2026-Q2', roundCount: 8, average18: 80.9, bestScore: 76, roundIds: ['900001'] }],
    byMonth: [
      { key: '2026-05', roundCount: 2, average18: 80.5, averageDifferential: 9.1, bestScore: 78, roundIds: ['900001', '900002'] },
      { key: '2026-04', roundCount: 3, average18: 82.0, averageDifferential: 10.4, bestScore: 79, roundIds: ['900004'] },
      { key: '2026-03', roundCount: 2, average18: 84.5, averageDifferential: 12.0, bestScore: 81, roundIds: ['900005'] },
    ],
    byDay: [
      { key: '2026-05-20', roundCount: 1, average18: 78, bestScore: 78, roundIds: ['900001'] },
      { key: '2026-05-03', roundCount: 1, average18: 83, bestScore: 83, roundIds: ['900002'] },
      { key: '2026-04-16', roundCount: 1, average18: 79, bestScore: 79, roundIds: ['900004'] },
    ],
    playFrequency: { totalMonths: 4, roundsPerMonth: 3.2, mostActiveMonth: { key: '2026-05', roundCount: 4 } },
    improvement: {
      direction: 'improving',
      baselineAverage18: 85.2,
      recentAverage18: 80.9,
      deltaAverage18: -4.3,
      strokesPerRoundTrend: -0.7,
      confidence: 'medium',
      windowSize: 5,
      baselineRoundRefs: ['900007', '900008'],
      recentRoundRefs: ['900001', '900002'],
    },
  },
  trend: {
    points: [
      { date: '2026-03-14', score: 85, toPar: 13, roundId: '900005' },
      { date: '2026-04-16', score: 79, toPar: 7, roundId: '900004' },
      { date: '2026-05-20', score: 78, toPar: 6, roundId: '900001' },
    ],
  },
  scoring: {
    scoreBands: [
      { label: '70s', count: 3, roundIds: ['900001', '900004'] },
      { label: '80s', count: 7, roundIds: ['900002', '900005'] },
    ],
    outcomes: { eagleOrBetter: 1, birdie: 14, par: 94, bogey: 76, doubleOrWorse: 31 },
    outcomeDistribution: [
      { key: 'eagleOrBetter', label: 'Eagle+', count: 1, pct: 0.5 },
      { key: 'birdie', label: 'Birdie', count: 14, pct: 6.5 },
      { key: 'par', label: 'Par', count: 94, pct: 43.5 },
      { key: 'bogey', label: 'Bogey', count: 76, pct: 35.2 },
      { key: 'double', label: 'Double', count: 22, pct: 10.2 },
      { key: 'triple', label: 'Triple', count: 6, pct: 2.8 },
      { key: 'quadPlus', label: '+4 or worse', count: 3, pct: 1.4 },
    ],
    byPar: [
      { par: 3, holeCount: 40, averageToPar: 0.3, parOrBetter: 29, parOrBetterPct: 72.5 },
      { par: 4, holeCount: 120, averageToPar: 0.7, parOrBetter: 61, parOrBetterPct: 50.8 },
      { par: 5, holeCount: 56, averageToPar: 0.4, parOrBetter: 35, parOrBetterPct: 62.5 },
    ],
    phaseStats: [
      { phase: 'Tee', fairwaysRecorded: 100, fairwaysHit: 57, fairwayMissLeft: 26, fairwayMissRight: 17 },
      { phase: 'Approach', girRecorded: 216, gir: 91, missedGir: 125, girPct: 42.1 },
      { phase: 'Putting', totalPutts: 397, holesWithPutts: 216, averagePutts: 1.84, threePutts: 5 },
    ],
    teeDirection: { hitPct: 57, leftPct: 26, rightPct: 12, otherPct: 5, recorded: 60, dominantMiss: 'left' },
    approachMiss: { girPct: 42, shortPct: 30, longPct: 12, leftPct: 10, rightPct: 24, recorded: 60, dominantMiss: 'short' },
    putting: { totalPutts: 397, averagePuttsPerRound: 33.1, averagePutts: 1.84, threePutts: 5, roundsWithPutts: 12 },
  },
  courseDistribution: [
    {
      courseKey: 'black_knight',
      courseName: 'Black Knight B',
      roundCount: 5,
      pct: 41.7,
      location: { latitude: 22.281, longitude: 114.164 },
      roundRefs: ['900001', '900002'],
    },
  ],
  records: {
    best18: { score: 76, courseName: 'Black Knight B', roundRefs: ['900001'] },
    worst18: { score: 91, courseName: 'Fixture Links', roundRefs: ['900003'] },
    bestNine: { score: 38, courseName: 'Black Knight B', roundRefs: ['900004'] },
    mostPlayedCourse: { courseName: 'Black Knight B', roundCount: 5, roundRefs: ['900001', '900002'] },
    longestShots: [{ club: '1D', distance: 270, shotRefs: ['900001:1:0'] }],
    bestHoleOutcomes: [{ hole: 2, toPar: -1, holeRefs: ['900001:2'] }],
  },
  courses: [
    {
      courseKey: 'black_knight',
      courseName: 'Black Knight B',
      roundCount: 5,
      average18: 80.5,
      bestScore: 76,
      worstScore: 86,
      recentRoundId: '900001',
      nineBreakdown: [
        { label: 'B/C', roundCount: 3, average: 80.3, bestScore: 76, recentRoundId: '900001' },
        { label: 'A/B', roundCount: 2, average: 83.5, bestScore: 81, recentRoundId: '900004' },
      ],
      rounds: [
        { roundId: '900001', date: '2026-05-20', score: 78, holesCompleted: 18, toPar: 6, nine: 'B/C' },
        { roundId: '900002', date: '2026-05-03', score: 83, holesCompleted: 18, toPar: 11, nine: 'B/C' },
      ],
      geometryCoverage: 'partial',
      roundRefs: ['900001', '900002'],
      recentForm: { direction: 'improving', recentAverage18: 79, deltaAverage18: -2.4 },
    },
  ],
  holes: [
    {
      courseKey: 'black_knight',
      hole: 7,
      sampleCount: 5,
      averageToPar: 1.1,
      worstToPar: 3,
      geometryCoverage: 'ready',
      holeRefs: ['900001:7'],
      scoreDistribution: [{ label: 'Bogey', className: 'bogey', count: 2, pct: 40, holeRefs: ['900001:7'] }],
      repeatedIssues: [{ issue: 'approach_short', phase: 'Approach', count: 3, refs: ['900001:7'] }],
    },
  ],
  // Measured per-club stats (metres). Codes map onto the effective-bag tokens
  // (1D→driver / 3W→wood3 / 5I→iron5 / 7I→iron7 / 9I→iron9 / PW→pw) so the 球包
  // gapping ladder shows real P10–P90 dispersion bands; the bag's sw/putter carry
  // no measured samples and render 数据不足.
  clubs: [
    { club: '1D', sampleCount: 41, median: 208, p10: 196, p90: 220, max: 232, confidence: 'high', shotRefs: ['900001:1:0', '900002:4:0'] },
    { club: '3W', sampleCount: 22, median: 186, p10: 176, p90: 196, max: 205, confidence: 'medium', shotRefs: ['900002:3:0'] },
    { club: '5I', sampleCount: 34, median: 158, p10: 150, p90: 167, max: 173, confidence: 'high', shotRefs: ['900001:5:1'] },
    { club: '7I', sampleCount: 64, median: 130, p10: 122, p90: 139, max: 146, confidence: 'high', shotRefs: ['900001:7:1'] },
    { club: '9I', sampleCount: 41, median: 112, p10: 105, p90: 120, max: 126, confidence: 'medium', shotRefs: ['900001:9:1'] },
    { club: 'PW', sampleCount: 58, median: 100, p10: 93, p90: 108, max: 114, confidence: 'high', shotRefs: ['900001:12:1'] },
  ],
  diagnosis: {
    topIssue: { issue: 'approach_short', phase: 'Approach' },
    issueTrends: [
      { issue: 'approach_short', phase: 'Approach', estimatedStrokesLost: 2.1, estimatedStrokesImpact: 2.1 },
      { issue: 'three_putt', phase: 'Putting', estimatedStrokesLost: 0.7, estimatedStrokesImpact: 0.7 },
      { issue: 'tee_left', phase: 'Tee', estimatedStrokesLost: 0.4, estimatedStrokesImpact: 0.4 },
    ],
  },
  issues: [
    {
      issue: 'approach_short',
      phase: 'Approach',
      source: 'deterministic',
      confidence: 'medium',
      count: 6,
      refs: ['900001:7', '900002:11'],
    },
  ],
  dataQuality: [
    { label: 'shots', state: 'good', ready: 12, total: 12, refs: ['900001'] },
    { label: 'geometry', state: 'partial', ready: 8, total: 12, refs: ['900003'] },
    { label: 'reports', state: 'partial', ready: 4, total: 12, refs: ['900001'] },
  ],
  drillDown: { roundIds: ['900001', '900002'], roundRefs: ['900001', '900002'] },
}

const syncStatusPayload = {
  schema: 'ai-caddie-sync-status-v2',
  connector: {
    name: 'garmin_cn_web_session',
    state: 'ready',
    detail: 'Local Garmin snapshots are available.',
    canSync: true,
    reauthRequired: false,
    nextAction: 'review_history',
  },
  connectors: [
    {
      name: 'garmin_cn_web_session',
      state: 'ready',
      detail: 'CN session connector is ready.',
      canSync: true,
      reauthRequired: false,
      nextAction: 'review_history',
    },
    {
      name: 'garmin_oauth_feasibility',
      state: 'not_available',
      detail: 'Official OAuth is tracked as feasibility only.',
      canSync: false,
      reauthRequired: false,
      feasibilityQuestions: ['Can official OAuth access golf scorecards?'],
    },
  ],
  snapshot: {
    dataMode: 'fixture',
    scorecardCount: 12,
    shotFileCount: 12,
    summaryPresent: true,
    lastSuccessfulSyncAt: '2026-05-25T10:00:00Z',
  },
  lastRun: { state: 'ready', snapshotId: 'snap-20260525' },
}

const mobileCourseOptionsPayload = {
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
      geometryCoverage: 'partial',
      sourceRefs: ['900001', '900002'],
    },
  ],
  emptyState: null,
  generatedAt: '2026-05-25T08:00:00Z',
}

const courseSearchPayload = {
  schema: 'ai-caddie-course-search-v1',
  query: '观澜湖',
  matches: [{ globalId: 31870, name: '观澜湖·奥拉沙宝场', holes: 18, city: '深圳', province: '广东', ratio: 0.92 }],
}

const readinessPayload = {
  schema: 'ai-caddie-readiness-v1',
  status: 'degraded',
  checks: [
    { label: 'service', state: 'ready', detail: 'API process is responding.', evidence: {} },
    { label: 'history', state: 'ready', detail: 'Fixture rounds loaded.', evidence: { totalRounds: 12 } },
    { label: 'geometry', state: 'degraded', detail: 'Some holes lack geometry.', evidence: { coverage: '67%' } },
  ],
}

const productSettingsPayload = {
  schema: 'ai-caddie-product-settings-v1',
  dataSources: [
    {
      id: 'garmin_cn_web_session',
      label: 'Garmin CN Web Session',
      track: 'primary',
      state: 'available',
      credentialPolicy: 'session_material_only',
      capabilities: ['scorecards', 'shot_rows'],
    },
    {
      id: 'garmin_oauth',
      label: 'Official Garmin OAuth',
      track: 'feasibility',
      state: 'not_syncable',
      credentialPolicy: 'pkce_only_if_golf_data_is_proven',
      capabilities: ['identity_feasibility'],
      capabilityMatrix: [
        {
          key: 'scorecards',
          label: 'Golf scorecards',
          state: 'unproven',
          evidence: 'Official OAuth golf scorecard access is not proven.',
          nextStep: 'Verify whether Garmin OAuth can read golf scorecards or FIT golf activity data.',
          canReplaceCnConnector: false,
          migrationValue: true,
        },
        {
          key: 'identity',
          label: 'Identity',
          state: 'possible',
          evidence: 'OAuth can still support identity and migration if golf data is unavailable.',
          nextStep: 'Keep the connector interface replaceable.',
          canReplaceCnConnector: false,
          migrationValue: true,
        },
      ],
      probe: {
        schema: 'ai-caddie-garmin-oauth-probe-v1',
        state: 'not_configured',
        liveProbeAllowed: false,
        configured: {
          clientId: false,
          clientCredential: false,
          redirectUri: false,
          consentEndpoint: false,
          exchangeEndpoint: false,
          scopes: false,
        },
        missing: ['client_id', 'redirect_uri', 'consent_endpoint', 'exchange_endpoint', 'scopes'],
        consentRequest: {
          method: 'GET',
          endpointConfigured: false,
          parameterKeys: ['response_type', 'client_id', 'redirect_uri', 'scope', 'state'],
          redactedPreview: null,
        },
        manualSteps: ['Register a Garmin OAuth client and redirect URI through the official developer path.'],
      },
    },
  ],
  aiProviders: {
    activeProvider: 'gemini_api_key',
    factBindingRequired: true,
    providers: [
      { id: 'static', label: 'Static', state: 'ready' },
      { id: 'gemini_api_key', label: 'Gemini API', state: 'configured' },
    ],
  },
  liveApps: {
    ios: { state: 'contract_ready', offlineFirst: true },
    watch: { state: 'contract_ready', requiresIphoneBridge: true },
    vision: { state: 'bounded_context', confirmationRequired: true },
  },
  privacy: {
    noGarminPasswordStorage: true,
    adminProtectedWrites: true,
    mediaRedaction: true,
    localSnapshotsSurviveReauth: true,
    secretFreeStatusResponses: true,
  },
  endpoints: {
    syncStatus: '/api/v2/sync/status',
    caddieDecision: '/api/v2/caddie/decision',
    reports: '/api/v2/reports',
  },
}

const reportIndexPayload = {
  schema: 'ai-caddie-review-report-index-v1',
  total: 2,
  reports: [
    {
      id: 'trend-recent-10',
      storedAt: '2026-05-25T10:30:00Z',
      kind: 'trend',
      subjectId: 'recent_10',
      confidence: 'medium',
      provider: 'StaticProvider',
      model: 'static',
      sourceRefs: ['900001', '900002'],
    },
    {
      id: 'round-900001',
      storedAt: '2026-05-25T09:30:00Z',
      kind: 'round',
      subjectId: '900001',
      confidence: 'high',
      provider: 'StaticProvider',
      model: 'static',
      sourceRefs: ['900001'],
    },
  ],
}

const annotationsPayload = {
  schema: 'ai-caddie-annotations-v1',
  total: 2,
  target: null,
  annotations: [
    {
      id: 'annotation-1',
      createdAt: '2026-05-25T09:00:00Z',
      targetType: 'hole',
      targetId: '900001:7',
      kind: 'issue_tag',
      payload: { tag: 'approach_short', note: 'missed short twice from 140m' },
      source: 'manual',
    },
    {
      id: 'annotation-2',
      createdAt: '2026-05-25T09:10:00Z',
      targetType: 'shot',
      targetId: '900001:7:2',
      kind: 'club_correction',
      payload: { from: '8I', to: '7I', note: 'Garmin club selection was wrong' },
      source: 'manual',
    },
  ],
}

// 备战 walk fixtures for globalId 31795 ('Black Knight B/C' in the mobile
// course options above). The package is installed (all requested holes carry
// geometryCoverage=ready), so it can enter the full workbench gate. Hole 1
// deliberately carries a 1x1 legacy fallback under the realistic Topo response
// plus a two-dot shot scatter. Holes 2/7 carry authoritative route/par facts but
// omit a rendered raster/projection, keeping the explicit no-map fallback covered
// without pretending their geometry is missing. Hole 7 matches the
// stats.holes black_knight row so 关键洞 and the 逐洞速览 chip pick up 平均+1.1.
const tinyHoleJpeg =
  'data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAMCAgICAgMCAgIDAwMDBAYEBAQEBAgGBgUGCQgKCgkICQkKDA8MCgsOCwkJDRENDg8QEBEQCgwSExIQEw8QEBD/yQALCAABAAEBAREA/8wABgAQEAX/2gAIAQEAAD8A0s8g/9k='

const prepHoleOneOverlay = {
  w: 360,
  h: 563,
  ppm: 0.85,
  ln: 393,
  route: [
    [180, 528, 0],
    [176, 260, 212],
    [184, 68, 393],
  ],
}

const coursePrepPayload = {
  schema: 'ai-caddie-course-prep-v1',
  globalId: 31795,
  holeCount: 3,
  clubs: [
    { name: '1D', m: 220, yd: 241 },
    { name: '8I', m: 131, yd: 143 },
  ],
  holes: [
    {
      hole: 1,
      par: 4,
      par_source: 'courseview',
      blue_yards: 430,
      route_len_m: 393,
      route: prepHoleOneOverlay.route,
      geometryCoverage: 'ready',
      sourceRefs: [],
      missingData: [],
      candidateRoutes: [],
      carryTargets: [],
      steps: [
        { club: '1D', note: '开球瞄球道左侧,避开右侧沙坑' },
        { club: '8I', note: '第二杆攻果岭中部' },
      ],
      cautions: ['右侧长草密集,宁左勿右'],
      landing_m: 215,
      tee_club: '1D',
      hazards: { water_carry: [[120, 180]], bunkers: [[260, 8]] },
      map: { image: tinyHoleJpeg, overlay: prepHoleOneOverlay },
      yourShots: [
        { x: 168, y: 260, club: '1D', shotType: 'TEE', roundId: '900001' },
        { x: 188, y: 96, club: '8I', shotType: 'APPROACH', roundId: '900002' },
      ],
    },
    {
      hole: 2,
      par: 3,
      par_source: 'courseview',
      blue_yards: 180,
      route_len_m: 165,
      route: [
        [0, 0, 0],
        [0, 140, 165],
      ],
      geometryCoverage: 'ready',
      sourceRefs: ['course:31795', 'geometry:31795:2'],
      missingData: [],
      candidateRoutes: [],
      carryTargets: [],
      steps: [{ club: null, note: '一杆上果岭,宁长勿短' }],
      cautions: [],
      landing_m: null,
      tee_club: null,
      hazards: { water_carry: [], bunkers: [] },
    },
    {
      hole: 7,
      par: 4,
      par_source: 'played',
      blue_yards: 410,
      route_len_m: 375,
      route: [
        [0, 0, 0],
        [0, 300, 375],
      ],
      geometryCoverage: 'ready',
      sourceRefs: ['course:31795', 'geometry:31795:7'],
      missingData: [],
      candidateRoutes: [],
      carryTargets: [],
      steps: [{ club: '1D', note: '历史失分洞,稳住开球' }],
      cautions: ['连续两轮 +2,别贪长'],
      landing_m: null,
      tee_club: '1D',
      hazards: { water_carry: [], bunkers: [] },
    },
  ],
}

// Prep now opens every selected course through the same mobile package used by
// iOS/Watch before reading the web prep view. Keep the E2E package honest enough
// to supply the provider's real local-hole identities; the prep payload below
// remains the rendered map authority exercised by this visual walk.
const mobileCoursePackagePayload = {
  schema: 'ai-caddie-live-round-package-v1',
  roundId: 'web-prep-31795',
  dataMode: 'fixture',
  holes: coursePrepPayload.holes.map((hole) => ({
    number: hole.hole,
    sourceGlobalId: 31795,
    sourceLocalHole: hole.hole,
    par: hole.par,
    yards: hole.blue_yards,
    geometryCoverage: hole.geometryCoverage,
  })),
}

// basis carries the REAL backend machine keys (ai_caddie/prep_tips.py); the
// page maps them to zh 依据 lines and must never render them raw.
const prepTipsPayload = {
  schema: 'ai-caddie-prep-tips-v1',
  courseKey: 'black_knight',
  tips: [
    {
      priority: 1,
      severity: 'high',
      text: '开球偏右(58%),第1洞、第7洞尤其要瞄球道左侧',
      basis: 'course.teeDirection',
      sourceRefs: ['stats:black_knight:teeDirection'],
    },
    {
      priority: 2,
      severity: 'info',
      text: '三杆洞稳(平均+0.2),按部就班拿帕',
      basis: 'course.parScoring.par3',
      sourceRefs: ['stats:black_knight:parScoring:par3'],
    },
  ],
}

// 实战 walk fixtures: the 决策沙盘 advice pair. Shapes mirror App.test.tsx
// caddieContextPayload/caddieDecisionPayload. The context mock echoes the
// request's source_ref/shot_type/lie/distance/strategy_mode back into the
// context the way the real builder does (ai_caddie/caddie_context.py binds
// strategyMode into the context only when requested), so the decision POST
// body carries exactly what the wire carried.
function caddieContextPayload(query: URLSearchParams) {
  const sourceRef = query.get('source_ref')
  const shotType = query.get('shot_type')
  const distance = query.get('distance_to_pin_m')
  const lie = query.get('lie')
  const strategyMode = query.get('strategy_mode')
  return {
    schema: 'ai-caddie-context-v1',
    sourceRef,
    shotType,
    context: {
      source: 'history_drilldown',
      sourceRef,
      roundId: '900001',
      courseName: 'Black Knight B',
      hole: 1,
      globalId: 31795,
      localHole: 1,
      shotType,
      ...(distance === null ? {} : { distanceToPin_m: Number(distance) }),
      ...(lie === null ? {} : { lie }),
      ...(strategyMode === null ? {} : { strategyMode }),
      geometry: { coverage: 'partial', hasHazards: true, hasMeshes: false, hazardCount: 1 },
      hazards: [{ kind: 'water', id: 'water-left' }],
      clubProfiles: { '8I': { clubName: '8I', sampleSize: 4, median: 144, p10: 132, p90: 153 } },
    },
    evidence: [{ label: 'history_ref', value: sourceRef }],
    missingData: [],
  }
}

// The decision mock keys its selected option off the POSTed
// context.strategyMode (default → stock 8I, attack → 7I), so the 博 recompute
// in the walk only renders a new club if the toggle truly flowed through the
// context fetch into the decision request.
function caddieDecisionPayload(strategyMode: string | undefined) {
  const attack = strategyMode === 'attack'
  const selectedId = attack ? 'attack' : 'stock'
  return {
    schema: 'ai-caddie-decision-v2',
    decisionId: `900001:1:approach:${selectedId}`,
    sourceRef: '900001:1',
    evidenceRefs: ['900001:1'],
    shotType: 'approach',
    phase: 'Approach',
    context: { courseName: 'Black Knight B', hole: 1, sourceRef: '900001:1' },
    options: [
      { id: 'safe', label: 'Safe', recommendedClub: '9I', carry_m: 118, riskScore: 1, confidence: 'high' },
      { id: 'stock', label: 'Stock', recommendedClub: '8I', carry_m: 131, riskScore: 2, confidence: 'medium' },
      { id: 'attack', label: 'Attack', recommendedClub: '7I', carry_m: 144, riskScore: 4, confidence: 'medium' },
    ],
    selectedOptionId: selectedId,
    selectedOption: { id: selectedId },
    selected: { id: selectedId },
    avoidZones: [{ kind: 'water', id: 'water_front' }],
    forbiddenZones: [],
    acceptableMiss: attack
      ? { direction: 'short', rationale: '果岭后沙坑深,宁短勿长' }
      : { direction: 'long', rationale: '前水后草,宁长勿短' },
    evidence: [{ label: 'water_front', value: 'carry 126m' }],
    confidence: { level: 'medium' },
    explanation: {
      narrative: attack ? '强攻角度更激进,7号铁直攻旗杆。' : '顺风顺路,8号铁打中线最稳。',
      factBinding: [{ claim: 'club', refs: ['900001:1:1'] }],
    },
    missingData: [],
    auditCriteria: [],
  }
}

// 最近回放 detail for the one overview recent round (900001); shape mirrors
// LivePage.test.tsx roundDetailFixture with the overview row's score/toPar.
const replayRoundDetailPayload = {
  schema: 'ai-caddie-history-round-detail-v1',
  roundRef: '900001',
  requestedRef: '900001',
  found: true,
  title: 'Black Knight B · 2026-05-20',
  round: {
    id: '900001',
    score: 78,
    toPar: 6,
    holesScored: 18,
    shotCount: 64,
    confidence: 'high',
    coverage: { scorecard: 'full', shots: 'full', putts: 'full' },
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
      holeRef: '900001:1',
      shotRefs: ['900001:1:0'],
      sourceRefs: ['900001:1'],
      status: 'complete',
    },
    {
      hole: 2,
      par: 5,
      score: 4,
      toPar: -1,
      className: 'birdie',
      putts: 1,
      gir: true,
      fairway: 'hit',
      holeRef: '900001:2',
      shotRefs: ['900001:2:0'],
      sourceRefs: ['900001:2'],
      status: 'complete',
    },
  ],
  phaseSummary: [],
  holeDetails: [],
  relatedRefs: { roundRefs: ['900001'], holeRefs: ['900001:1', '900001:2'], shotRefs: [], sourceRefs: [] },
  sourceFields: { id: '900001' },
  missingData: [],
}

// 复盘逐洞落点图 for the auto-selected overview round/hole: a tiny hole render + the
// round's actual shots (tee → landing → green) so the 落点图 + 杆序 timeline render.
const TRANSPARENT_PNG =
  'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='
const roundShotMapPayload = {
  schema: 'ai-caddie-round-hole-shotmap-v1',
  found: true,
  roundRef: '900001',
  hole: 1,
  par: 4,
  globalId: 31795,
  localHole: 1,
  geometryRevision: 'visual-fixture',
  mapKind: 'prodgeometry',
  map: {
    image: TRANSPARENT_PNG,
    overlay: { w: 300, h: 470, ppm: 1, ln: 400, route: [[150, 455, 0], [150, 72, 400]] },
  },
  shots: [
    { start: [150, 455], end: [128, 270], club: '一号木', lie: 'TeeBox', endLie: 'Fairway', shotType: 'TEE', order: 1, synthetic: false },
    { start: [128, 270], end: [182, 120], club: '五号木', lie: 'Fairway', endLie: 'Bunker', shotType: 'APPROACH', order: 2, synthetic: false },
    { start: [182, 120], end: [150, 72], club: '推杆', lie: 'Green', endLie: 'Green', shotType: 'PUTT', order: 3, synthetic: false },
  ],
  missingData: [],
}

test('major product screens render with stable Garmin Pro layout', async ({ page }, testInfo) => {
  const browserErrors: string[] = []
  const failedResponses: string[] = []
  page.on('pageerror', (error) => browserErrors.push(error.message))
  page.on('console', (message) => {
    if (message.type() === 'error') browserErrors.push(message.text())
  })
  page.on('response', (response) => {
    if (response.status() >= 400) {
      failedResponses.push(`${response.status()} ${new URL(response.url()).pathname}`)
    }
  })
  const { prepIncludeShots, caddieContextQueries, caddieDecisionBodies } = await mockApi(page)

  await page.goto('/')
  // 成绩 is the one answer-first destination for career, trends, analysis and archive.
  await expect(page.locator('section[aria-label="成绩主页"]')).toBeVisible()
  await expect(page.locator('section[aria-label="生涯概览"]')).toContainText('82.4')
  await expect(page.locator('section[aria-label="最近球局"]')).toContainText('Black Knight B')
  await assertNoViewportOverflow(page)
  await expect(page.getByText('历史数据不可用')).toHaveCount(0)
  await captureSmokeScreenshot(page, testInfo, 'overview')

  // All archive, trend and analysis pages now live under the one 成绩 destination.
  // Scope clicks to its subnav so same-named page links cannot satisfy the journey.
  const subnav = page.getByRole('navigation', { name: '辅助导航' })

  await subnav.getByRole('button', { name: '时间趋势' }).click()
  await expect(page.getByRole('heading', { name: '时间趋势', exact: true })).toBeVisible()
  await expect(page.getByRole('img', { name: '成绩时间趋势图' })).toBeVisible()
  await expect(page.locator('section[aria-label="历年表现"]')).toContainText('2026 年')
  await expect(page.locator('section[aria-label="打球频率"]')).toContainText('3 场')
  await page.getByRole('group', { name: '统计范围' }).getByRole('button', { name: '近 12 月' }).click()
  await expect(page.getByRole('group', { name: '汇总粒度' }).getByRole('button', { name: '月' })).toHaveAttribute('aria-pressed', 'true')
  await assertNoViewportOverflow(page)
  await captureSmokeScreenshot(page, testInfo, 'trends')

  await subnav.getByRole('button', { name: '表现分析' }).click()
  await expect(page.getByRole('heading', { name: '表现分析', exact: true })).toBeVisible()
  const phases = page.locator('section[aria-label="四个环节"]')
  await expect(phases).toContainText('开球')
  await expect(phases).toContainText('57%')
  await expect(phases).toContainText('攻果岭')
  await expect(phases).toContainText('42%')
  await expect(phases).toContainText('33.1')
  await expect(phases).toContainText('当前历史统计未提供可靠分母')
  await expect(page.locator('section[aria-label="成绩构成"]')).toContainText('双柏忌+')
  await expect(page.locator('section[aria-label="按标准杆类型"]')).toContainText('Par 3')
  await assertNoViewportOverflow(page)
  await expect(page.locator('text=/unavailable|failed/i')).toHaveCount(0)

  await subnav.getByRole('button', { name: '球场' }).click()
  await expect(page.getByRole('heading', { name: '球场表现', exact: true, level: 1 })).toBeVisible()
  await page.getByText('Black Knight B', { exact: true }).click()
  await expect(page.getByRole('heading', { name: '九洞组合' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '球局证据' })).toBeVisible()
  await assertNoViewportOverflow(page)
  await expect(page.locator('text=/unavailable|failed/i')).toHaveCount(0)

  await subnav.getByRole('button', { name: '表现分析' }).click()
  await page.getByRole('button', { name: /球杆表现/ }).click()
  await expect(page.getByRole('heading', { name: '球杆表现', exact: true })).toBeVisible()
  await expect(page.getByText('227 码')).toBeVisible()
  await assertNoViewportOverflow(page)
  await captureSmokeScreenshot(page, testInfo, 'strengths')

  await subnav.getByRole('button', { name: '全部球局' }).click()
  await expect(page.getByRole('heading', { name: '球局', exact: true, level: 1 })).toBeVisible()
  await expect(page.getByRole('button', { name: /打开球局 Black Knight B/ })).toBeVisible()
  await assertNoViewportOverflow(page)
  await page.getByRole('button', { name: /打开球局 Black Knight B/ }).click()
  await expect(page.locator('[aria-label="第1洞落点图"]')).toBeVisible()
  await expect(page.getByRole('heading', { name: '球局回顾', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: '记分卡', exact: true })).toBeVisible()

  // 球包 (bag rail) = the P5 club-distance gapping workbench: a shared-axis ladder
  // (carry marker + measured P10–P90 band) + a selected-club detail + the editable
  // club table, all wired to the effective bag + measured per-club stats.
  await page.getByRole('button', { name: '球包', exact: true }).click()
  await expect(page.getByRole('heading', { name: '球包', exact: true, level: 1 })).toBeVisible()
  const ladder = page.locator('section[aria-label="距离阶梯"]')
  await expect(ladder).toBeVisible()
  // The ladder is real: the driver bar comes from the effective bag (一号木, 205m → 224 码).
  await expect(ladder.getByRole('button', { name: '一号木 距离条' })).toBeVisible()
  await expect(page.locator('section[aria-label="球杆详情"]')).toBeVisible()
  const bagTable = page.locator('section[aria-label="全部球杆"]')
  await expect(bagTable).toContainText('五号铁')
  await expect(bagTable).toContainText('224') // driver carry P50, yards
  // sw/putter carry no measured samples → honest 数据不足 (no fabricated dispersion).
  await expect(bagTable).toContainText('数据不足')
  await assertNoViewportOverflow(page)
  await expect(page.locator('text=/unavailable|failed/i')).toHaveCount(0)
  await captureSmokeScreenshot(page, testInfo, 'bag')

  // prepGlobalId is null on a fresh visit, so 备战 lands on the PrepPage entry
  // state (course finder); the full prep walk runs at the end of this test.
  await page.getByRole('button', { name: '备战' }).click()
  await expect(page.getByRole('heading', { name: '选择球场开始备战' })).toBeVisible()
  await assertNoViewportOverflow(page)

  // 球童沙盘 is the off-rail caddie sandbox (Web has no live-play rail section); it
  // lands on the LivePage 决策沙盘 entry. (The legacy 完整工具 caddie dashboard is now
  // diagnostics-gated and no longer in the consumer live tabs.)
  await page.getByRole('button', { name: '球童沙盘' }).click()
  const liveTabs = page.getByRole('navigation', { name: '实战页签' })
  await expect(liveTabs.getByRole('button', { name: '决策沙盘' })).toHaveAttribute('aria-current', 'page')
  await expect(page.getByRole('heading', { name: '选择球场开始模拟' })).toBeVisible()
  await assertNoViewportOverflow(page)

  await page.getByRole('button', { name: '设置' }).click()
  await expect(page.getByRole('heading', { name: '同步与数据健康', exact: true })).toBeVisible()
  await expect(page.getByText('查看历史')).toBeVisible()
  await assertNoViewportOverflow(page)
  await page.getByRole('button', { name: '订正' }).click()
  await expect(page.getByRole('heading', { name: '订正', exact: true })).toBeVisible()
  await assertNoViewportOverflow(page)
  await page.getByRole('button', { name: '后端配置' }).click()
  await expect(page.getByRole('heading', { name: '后端配置', exact: true })).toBeVisible()
  await assertNoViewportOverflow(page)
  await captureSmokeScreenshot(page, testInfo, 'settings')

  // 备战 full walk: the course finder lives on the 备战 entry now (the 复盘 landing is
  // the round-review workbench) → course header → 三页签.
  await page.getByRole('button', { name: '备战', exact: true }).click()
  await expect(page.getByRole('heading', { name: '选择球场开始备战' })).toBeVisible()
  await page.getByRole('button', { name: '去备战 Black Knight B/C' }).click()

  // Workbench: crumb (course name) + hole-list totals + stats record.
  await expect(page.getByRole('heading', { name: 'Black Knight B/C' })).toBeVisible()
  await expect(page.getByText('PAR 11 · 1020 码')).toBeVisible()
  await expect(page.getByText('你的战绩:打过 5 次 · 均杆 80.5')).toBeVisible()

  // The compact picker replaces the old 18-row rail. Exercise a real hole switch so the option's
  // yardage/history labels and the selected-hole summary are both covered without restoring a list.
  const holePicker = page.getByRole('combobox', { name: '选择球洞' })
  await expect(holePicker.locator('option[value="7"]')).toHaveText(/第 7 洞 · Par 4 · 410码 · 平均\+1\.1 · 关键/)
  await holePicker.selectOption('7')
  await expect(page.locator('.prep-active-hole-summary')).toContainText('平均+1.1')
  await expect(page.locator('.prep-active-hole-summary')).toContainText('关键')
  await holePicker.selectOption('1')

  // Hole 1 is selected by default. Its real geometry, shot scatter and nearest-club recommendation
  // now live on the map; the dock keeps only progressive strategy/personal detail.
  const prepInspector = page.getByRole('complementary', { name: '球童试算' })
  await expect(holePicker).toHaveValue('1')
  const prepCanvas = page.getByLabel('第1洞球道图')
  await expect(prepCanvas).toBeVisible()
  await expect(prepCanvas.getByLabel('地图推荐球杆')).toContainText('1D · 235码落点')
  await expect(prepCanvas.locator('title').filter({ hasText: '1D · 900001' })).toHaveCount(1)
  await expect(prepInspector.getByLabel('展开完整打法')).toBeVisible()
  const prepFrameBox = await prepCanvas.locator('.prep-canvas-frame').boundingBox()
  const prepBaseBox = await prepCanvas.locator('.prep-canvas-img').boundingBox()
  expect(prepFrameBox).not.toBeNull()
  expect(prepBaseBox).not.toBeNull()
  expect(prepBaseBox?.width).toBeCloseTo(prepFrameBox?.width ?? 0, 0)
  expect(prepBaseBox?.height).toBeCloseTo(prepFrameBox?.height ?? 0, 0)
  await assertNoViewportOverflow(page)
  await captureSmokeScreenshot(page, testInfo, 'prep-overview')

  // Selecting hole 7 re-drives the same map surface. This fixture has no rendered
  // raster/projection for that hole, so the explicit placeholder remains visible
  // and no recommendation point is fabricated.
  await holePicker.selectOption('7')
  await expect(holePicker).toHaveValue('7')
  const holeSevenCanvas = page.getByLabel('第7洞球道图')
  await expect(holeSevenCanvas).toBeVisible()
  await expect(holeSevenCanvas.getByLabel('地图推荐球杆')).toHaveCount(0)
  await expect(holeSevenCanvas.getByText('此洞暂无实景航图(示意图)', { exact: true })).toBeVisible()
  await assertNoViewportOverflow(page)
  await captureSmokeScreenshot(page, testInfo, 'prep-holes')

  // 针对你 tips render in the inspector (no tab), machine basis keys mapped to zh 依据
  // lines (raw keys must never surface).
  await prepInspector.getByText(/^\u9488对你 ·/).click()
  await expect(page.getByText('开球偏右(58%),第1洞、第7洞尤其要瞄球道左侧')).toBeVisible()
  await expect(page.getByText('三杆洞稳(平均+0.2),按部就班拿帕')).toBeVisible()
  await expect(page.getByText('依据:你在本场的开球倾向')).toBeVisible()
  await expect(page.getByText('course.parScoring.par3')).toHaveCount(0)
  await assertNoViewportOverflow(page)

  // 换球场 returns to the entry finder.
  await page.getByRole('button', { name: '换球场' }).click()
  await expect(page.getByRole('heading', { name: '选择球场开始备战' })).toBeVisible()
  await assertNoViewportOverflow(page)

  // The scatter we walked through was REQUESTED, not fixture luck: every prep
  // fetch of this walk carried include_shots=true on the wire. (StrictMode dev
  // double-fires the effect, so assert values, not a count of one.)
  expect(prepIncludeShots.length).toBeGreaterThanOrEqual(1)
  expect(prepIncludeShots).toEqual(prepIncludeShots.map(() => 'true'))

  // 实战 full walk: 决策沙盘 (course pick → hole sim → advice → 博 recompute)
  // → 最近回放 → 完整工具. Runs after the 备战 include_shots assertions above
  // because the sandbox's prep fetches carry NO include_shots (asserted at the
  // end of this walk).
  const sandboxPrepStart = prepIncludeShots.length
  await page.getByRole('button', { name: '球童沙盘' }).click()
  await expect(page.getByRole('heading', { name: '选择球场开始模拟' })).toBeVisible()
  await page.getByRole('button', { name: '开始模拟 Black Knight B/C' }).click()
  await expect(page.getByRole('heading', { name: 'Black Knight B/C' })).toBeVisible()

  // Hole chips come from the prep payload (1/2/7); hole 1 is active by default
  // and carries the rendered map. Hole 7 has no rendered overlay in this fixture,
  // so switching there degrades to the manual 到果岭 input; back on hole 1 the
  // map overlay shows the full tee-to-green distance for the blue player marker.
  await expect(page.getByRole('button', { name: '第1洞' })).toHaveAttribute('aria-current', 'true')
  await page.getByRole('button', { name: '第7洞' }).click()
  await expect(page.getByLabel('到果岭(码)')).toBeVisible()
  await page.getByRole('button', { name: '第1洞' }).click()
  // 393m * 1.09361 = 430.09 → 430码. The old text strip is deliberately gone;
  // distance is now one Garmin-style map overlay.
  await expect(page.locator('.live-sandbox-map-distance')).toContainText('430码')
  await assertNoViewportOverflow(page)

  // Tee shots take no lie; switching 击球类型 to 攻果岭 (ball still on the
  // tee, 393m out) unlocks 球位状态 → 长草.
  await expect(page.getByLabel('球位状态')).toBeDisabled()
  await page.getByLabel('击球类型').selectOption({ label: '攻果岭' })
  await expect(page.getByLabel('球位状态')).toBeEnabled()
  await page.getByLabel('球位状态').selectOption({ label: '长草' })

  // 要建议 runs the context+decision pair; the card shows the selected option
  // (stock 8I) with the 为什么 narrative and the acceptable-miss line. No
  // weather request belongs in this flow: manual wind is constructed
  // client-side, and an unexpected /weather/snapshot fetch would 404 into
  // failedResponses below.
  await page.getByRole('button', { name: '要建议' }).click()
  const adviceCard = page.getByRole('region', { name: '沙盘建议' })
  await expect(adviceCard.getByText('8I', { exact: true })).toBeVisible()
  // 风险 is visible text on the 主建议 (stock riskScore 2), not a dot-only glyph.
  await expect(adviceCard.getByText('风险 2', { exact: true })).toBeVisible()
  await expect(adviceCard.getByText('为什么')).toBeVisible()
  await expect(adviceCard.getByText('顺风顺路,8号铁打中线最稳。')).toBeVisible()
  await expect(adviceCard.getByText('可接受偏向:偏长 — 前水后草,宁长勿短')).toBeVisible()
  await assertNoViewportOverflow(page)
  await captureSmokeScreenshot(page, testInfo, 'live-advice')

  // 博 re-requests the pair with strategyMode=attack; the decision mock keys
  // its selected option off the POSTed context.strategyMode, so the 7I card
  // only renders if the toggle truly flowed through the wire.
  await page.getByRole('group', { name: '策略' }).getByRole('button', { name: '博' }).click()
  await expect(adviceCard.getByText('7I', { exact: true })).toBeVisible()
  await expect(adviceCard.getByText('强攻角度更激进,7号铁直攻旗杆。')).toBeVisible()

  // Wire-level proof: exactly one context+decision pair per request (event
  // driven — StrictMode does not double-fire clicks), first pair carrying the
  // simulated situation, second pair carrying the attack strategy.
  expect(caddieContextQueries.length).toBe(2)
  expect(caddieContextQueries[0]?.get('source_ref')).toBe('900001:1')
  expect(caddieContextQueries[0]?.get('shot_type')).toBe('approach')
  expect(caddieContextQueries[0]?.get('lie')).toBe('rough')
  expect(caddieContextQueries[0]?.get('distance_to_pin_m')).toBe('393')
  expect(caddieContextQueries[0]?.get('strategy_mode')).toBeNull()
  expect(caddieContextQueries[1]?.get('strategy_mode')).toBe('attack')
  expect(caddieDecisionBodies.length).toBe(2)
  expect(caddieDecisionBodies[0]?.shotType).toBe('approach')
  expect(caddieDecisionBodies[0]?.includeExplanation).toBe(true)
  expect(caddieDecisionBodies[0]?.context?.strategyMode).toBeUndefined()
  expect(caddieDecisionBodies[1]?.context?.strategyMode).toBe('attack')

  // 最近回放: the newest overview round auto-selects and its detail loads
  // through GET /api/v2/history/rounds/900001.
  await liveTabs.getByRole('button', { name: '最近回放' }).click()
  await expect(page.getByRole('button', { name: '回放 Black Knight B 05-20' })).toHaveAttribute('aria-current', 'true')
  await expect(page.getByRole('heading', { name: '球局回顾', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: '记分卡', exact: true })).toBeVisible()
  await assertNoViewportOverflow(page)
  await captureSmokeScreenshot(page, testInfo, 'live-replay')

  // The sandbox never asks for the prep shot scatter: its prep fetches carry
  // no include_shots at all (recorded as null), unlike the 备战 walk's.
  const sandboxPrepFetches = prepIncludeShots.slice(sandboxPrepStart)
  expect(sandboxPrepFetches.length).toBeGreaterThanOrEqual(1)
  expect(sandboxPrepFetches).toEqual(sandboxPrepFetches.map(() => null))

  await expect(failedResponses).toEqual([])
  await expect(browserErrors).toEqual([])
})

// Recorded shape of every POST /api/v2/caddie/decision body the sandbox sent.
interface RecordedDecisionRequest {
  shotType?: string
  includeExplanation?: boolean
  context?: { strategyMode?: string }
}

// Effective club bag for the 球包 page: canonical tokens + carry distances (metres).
// Tokens line up with the measured statsPayload.clubs codes so the gapping ladder
// enriches each bar with its measured P10–P90 band; sw/putter have no measured samples.
const effectiveClubBagPayload = {
  schema: 'ai-caddie-effective-club-bag-v1',
  source: 'garmin',
  found: true,
  clubs: [
    { token: 'driver', zhName: '一号木', customName: null, clubTypeId: 1, distanceM: 205, distanceSource: null },
    { token: 'wood3', zhName: '三号木', customName: null, clubTypeId: 2, distanceM: 185, distanceSource: null },
    { token: 'iron5', zhName: '五号铁', customName: null, clubTypeId: 14, distanceM: 160, distanceSource: null },
    { token: 'iron7', zhName: '七号铁', customName: null, clubTypeId: 16, distanceM: 128, distanceSource: null },
    { token: 'iron9', zhName: '九号铁', customName: null, clubTypeId: 18, distanceM: 114, distanceSource: null },
    { token: 'pw', zhName: 'P杆', customName: null, clubTypeId: 19, distanceM: 102, distanceSource: null },
    { token: 'sw', zhName: 'S杆', customName: null, clubTypeId: 21, distanceM: null, distanceSource: null },
    { token: 'putter', zhName: '推杆', customName: null, clubTypeId: 23, distanceM: null, distanceSource: null },
  ],
}

interface MockApiRecords {
  prepIncludeShots: Array<string | null>
  caddieContextQueries: URLSearchParams[]
  caddieDecisionBodies: RecordedDecisionRequest[]
  correctionBodies: Array<Record<string, unknown>>
  shotMapResponses: Array<Record<string, unknown>>
}

// Keep this duplicate smoke walk visually honest as well: a transparent response only proves that
// an <img> loaded, not that the map can actually be reviewed.
const TOPO_PNG_STUB = readFileSync(new URL('../public/hole-sample.png', import.meta.url))

async function mockApi(page: Page): Promise<MockApiRecords> {
  // Recorded ?include_shots values of every /prep request: the scatter walk is
  // only honest if the page actually asked the server for yourShots.
  const prepIncludeShots: Array<string | null> = []
  // Recorded 要建议 wire traffic: context GET queries + decision POST bodies,
  // so the 实战 walk can assert exactly what the sandbox requested.
  const caddieContextQueries: URLSearchParams[] = []
  const caddieDecisionBodies: RecordedDecisionRequest[] = []
  const correctionBodies: Array<Record<string, unknown>> = []
  const shotMapResponses: Array<Record<string, unknown>> = []
  let persistedShotMap: Record<string, unknown> = roundShotMapPayload
  await page.route('**/api/v2/**', async (route) => {
    const requestUrl = new URL(route.request().url())
    const path = requestUrl.pathname
    if (path === '/api/v2/history/overview') return route.fulfill({ json: overviewPayload })
    if (path === '/api/v2/history/rounds') return route.fulfill({ json: roundsPayload })
    if (/\/holes\/\d+\/shotmap$/.test(path) && route.request().method() === 'GET') {
      shotMapResponses.push(persistedShotMap)
      return route.fulfill({ json: persistedShotMap })
    }
    if (path === '/api/v2/history/rounds/900001/corrections' && route.request().method() === 'POST') {
      const body = route.request().postDataJSON() as Record<string, unknown>
      correctionBodies.push(body)
      // The refresh GET is a mocked server read of the accepted whole-hole snapshot.
      persistedShotMap = { ...roundShotMapPayload, shots: body.shots }
      return route.fulfill({ status: 201, json: { schema: 'ai-caddie-round-correction-v1', stored: body } })
    }
    // Realistic-topo base bitmap: on the real homeserver a course WITH CourseView geometry (e.g.
    // gid31795) returns a PNG here; serve a stub so the hole canvas' base <img> loads (no 404) and
    // the topo path is exercised. A geometry-less course would 404 → the canvas falls back.
    if (/\/holes\/\d+\/topo\.png$/.test(path)) return route.fulfill({ contentType: 'image/png', body: TOPO_PNG_STUB })
    // Fire-and-forget topo prewarm the web kicks on course select — return the queued-hole ack so the
    // POST never 404s into failedResponses (the real endpoint renders the course's holes in background).
    if (/\/topo\/prewarm$/.test(path)) return route.fulfill({ json: { schema: 'ai-caddie-topo-prewarm-v1', globalId: 31795, holes: [1, 2, 7], queued: 3 } })
    if (path === '/api/v2/history/rounds/900001') return route.fulfill({ json: replayRoundDetailPayload })
    if (path === '/api/v2/history/stats') return route.fulfill({ json: statsPayload })
    // 趋势 landing fetches the compact window-aware mobile stats; serve the same fixture
    // (it carries the subset the trends view reads, incl. scoring.outcomeDistribution).
    if (path === '/api/v2/history/stats/mobile') return route.fulfill({ json: statsPayload })
    if (path === '/api/v2/history/summary')
      return route.fulfill({
        json: { schema: 'ai-caddie-history-summary-v1', summary: statsPayload.summary, topIssue: statsPayload.issues?.[0]?.issue ?? null },
      })
    if (path === '/api/v2/caddie/context') {
      caddieContextQueries.push(requestUrl.searchParams)
      return route.fulfill({ json: caddieContextPayload(requestUrl.searchParams) })
    }
    if (path === '/api/v2/caddie/decision') {
      const body = route.request().postDataJSON() as RecordedDecisionRequest
      caddieDecisionBodies.push(body)
      return route.fulfill({ json: caddieDecisionPayload(body.context?.strategyMode) })
    }
    if (path === '/api/v2/sync/status') return route.fulfill({ json: syncStatusPayload })
    if (path === '/api/v2/mobile/courses/options') return route.fulfill({ json: mobileCourseOptionsPayload })
    if (path === '/api/v2/mobile/courses/31795/package') return route.fulfill({ json: mobileCoursePackagePayload })
    if (path === '/api/v2/courses/31795/install/status') {
      return route.fulfill({
        json: {
          schema: 'ai-caddie-course-install-v1',
          jobId: 'visual-fixture-31795',
          globalId: 31795,
          teeBox: 'blue',
          nine: 'all',
          phase: 'ready',
          stage: 'complete',
          totalHoles: 3,
          geometryReady: 3,
          topoReady: 3,
          holes: [1, 2, 7].map((hole) => ({
            globalId: 31795,
            localHole: hole,
            displayHole: hole,
            geometry: 'ready',
            topo: 'ready',
          })),
        },
      })
    }
    if (path === '/api/v2/courses/search') return route.fulfill({ json: courseSearchPayload })
    // PrepPage course fetches carry the globalId in the path (and the prep
    // request a ?include_shots=true query), so match by prefix + suffix.
    if (path.startsWith('/api/v2/courses/') && path.endsWith('/prep')) {
      const includeShots = requestUrl.searchParams.get('include_shots')
      prepIncludeShots.push(includeShots)
      // Honest contract: yourShots ship ONLY when requested, like the real API —
      // the visible scatter in the walk then proves the wire parameter.
      const payload =
        includeShots === 'true'
          ? coursePrepPayload
          : {
              ...coursePrepPayload,
              holes: coursePrepPayload.holes.map((hole) => {
                const { yourShots: _omitted, ...rest } = hole as { yourShots?: unknown }
                void _omitted
                return rest
              }),
            }
      return route.fulfill({ json: payload })
    }
    if (path.startsWith('/api/v2/courses/') && path.endsWith('/prep-tips')) return route.fulfill({ json: prepTipsPayload })
    if (path === '/api/v2/readiness') return route.fulfill({ json: readinessPayload })
    if (path === '/api/v2/reports') return route.fulfill({ json: reportIndexPayload })
    if (path === '/api/v2/settings/product') return route.fulfill({ json: productSettingsPayload })
    if (path === '/api/v2/annotations') return route.fulfill({ json: annotationsPayload })
    if (/^\/api\/v2\/players\/[^/]+\/clubs\/bag$/.test(path)) return route.fulfill({ json: effectiveClubBagPayload })
    return route.fulfill({ status: 404, json: { detail: `Unhandled test route: ${path}` } })
  })
  return { prepIncludeShots, caddieContextQueries, caddieDecisionBodies, correctionBodies, shotMapResponses }
}

async function assertNoViewportOverflow(page: Page) {
  const overflow = await page.evaluate(() => {
    const root = document.documentElement
    const body = document.body
    return Math.max(root.scrollWidth, body.scrollWidth) - root.clientWidth
  })
  expect(overflow).toBeLessThanOrEqual(2)
}

async function captureSmokeScreenshot(page: Page, testInfo: TestInfo, name: string) {
  await page.evaluate(() => {
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur()
    document.documentElement.style.scrollBehavior = 'auto'
    document.body.style.scrollBehavior = 'auto'
    if (document.scrollingElement) document.scrollingElement.scrollTop = 0
    window.scrollTo(0, 0)
  })
  await page.waitForFunction(
    () => Math.abs(document.scrollingElement?.scrollTop ?? window.scrollY) <= 1,
    undefined,
    { timeout: 5_000 },
  )
  await page.screenshot({
    path: testInfo.outputPath(`${name}.png`),
    fullPage: true,
    animations: 'disabled',
  })
}

test('review editor saves one map-first draft after browser interactions', async ({ page }, testInfo) => {
  const { correctionBodies, shotMapResponses } = await mockApi(page)
  await page.goto('/')
  await page.getByRole('button', { name: '全部球局', exact: true }).click()
  await expect(page.getByRole('heading', { name: '球局', exact: true, level: 1 })).toBeVisible()
  await page.getByRole('button', { name: /打开球局 Black Knight B/ }).click()
  await expect(page.getByLabel('第1洞落点图')).toBeVisible()

  await page.getByRole('button', { name: '编辑落点' }).click()
  const editor = page.locator('[aria-label="复盘编辑"]')
  await expect(editor).toBeVisible()
  const canvas = page.getByLabel('第1洞落点图')
  const svg = canvas.locator('svg.review-canvas-svg')
  const originalShotIds = await canvas.locator('circle[data-shot-id]').evaluateAll((markers) => markers.map((marker) => marker.getAttribute('data-shot-id')))
  expect(originalShotIds).toHaveLength(3)
  const svgBox = await svg.boundingBox()
  expect(svgBox).not.toBeNull()
  if (!svgBox) throw new Error('review canvas SVG has no box')
  await page.mouse.click(svgBox.x + svgBox.width * 0.82, svgBox.y + svgBox.height * 0.82)
  await expect(editor.getByRole('button', { name: '删除第4杆' })).toBeVisible()
  const addedShotId = await canvas.locator('circle[data-shot-id]').nth(3).getAttribute('data-shot-id')
  expect(addedShotId).toMatch(/^web-draft-/)

  // Drag the second existing shot so it remains in the saved snapshot after deleting shot 1.
  const marker = canvas.locator('circle[data-shot-id]').nth(1)
  const draggedShotId = await marker.getAttribute('data-shot-id')
  expect(draggedShotId).toBeTruthy()
  const initialX = Number(await marker.getAttribute('cx'))
  const initialY = Number(await marker.getAttribute('cy'))
  const box = await marker.boundingBox()
  expect(box).not.toBeNull()
  if (!box) throw new Error('editable landing marker has no box')
  const startX = box.x + box.width / 2
  const startY = box.y + box.height / 2
  const endX = startX + 24
  const endY = startY + 16
  const dragDiagnosticStart = await page.evaluate(({ startX, startY }) => {
    const svg = document.querySelector('svg.review-canvas-svg')
    const target = document.elementFromPoint(startX, startY)
    const describe = (element: Element | null) =>
      element
        ? { tag: element.tagName, shotId: element.getAttribute('data-shot-id'), hitId: element.getAttribute('data-shot-hit-id') }
        : null
    const logs: Array<Record<string, unknown>> = []
    const handlers = ['pointerdown', 'pointermove', 'pointerup', 'touchstart', 'touchmove', 'touchend'].map((type) => {
      const handler = (event: Event) => {
        const point = 'touches' in event && event.touches.length > 0 ? event.touches[0] : event
        logs.push({
          type,
          pointerId: 'pointerId' in event ? event.pointerId : null,
          clientX: 'clientX' in point ? point.clientX : null,
          clientY: 'clientY' in point ? point.clientY : null,
          target: describe(event.target instanceof Element ? event.target : null),
        })
      }
      svg?.addEventListener(type, handler, true)
      return { type, handler }
    })
    if (svg) (svg as SVGSVGElement & { __dragDiagnostic?: unknown }).__dragDiagnostic = { logs, handlers }
    return {
      hit: describe(target),
      markerBox: (svg?.querySelector('circle[data-shot-id]') as SVGCircleElement | null)?.getBoundingClientRect().toJSON() ?? null,
      editableBox: (svg?.querySelector('circle[data-shot-id="web-source-2"]') as SVGCircleElement | null)?.getBoundingClientRect().toJSON() ?? null,
      hitBox: (svg?.querySelector('circle[data-shot-hit-id="web-source-2"]') as SVGCircleElement | null)?.getBoundingClientRect().toJSON() ?? null,
    }
  }, { startX, startY })
  console.log(`[review-drag-diagnostic-start] ${JSON.stringify(dragDiagnosticStart)}`)
  if (testInfo.project.name === 'mobile-chromium') {
    const cdp = await page.context().newCDPSession(page)
    await cdp.send('Input.dispatchTouchEvent', {
      type: 'touchStart',
      touchPoints: [{ id: 1, x: startX, y: startY, radiusX: 8, radiusY: 8, force: 1 }],
    })
    await cdp.send('Input.dispatchTouchEvent', {
      type: 'touchMove',
      touchPoints: [{ id: 1, x: endX, y: endY, radiusX: 8, radiusY: 8, force: 1 }],
    })
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] })
    await cdp.detach()
  } else {
    await page.mouse.move(startX, startY)
    await page.mouse.down()
    await page.mouse.move(endX, endY)
    await page.mouse.up()
  }
  const dragDiagnosticEvents = await page.evaluate(() => {
    const svg = document.querySelector('svg.review-canvas-svg') as (SVGSVGElement & { __dragDiagnostic?: { logs: Array<Record<string, unknown>>; handlers: Array<{ type: string; handler: EventListener }> } }) | null
    const diagnostic = svg?.__dragDiagnostic
    if (!svg || !diagnostic) return []
    for (const { type, handler } of diagnostic.handlers) svg.removeEventListener(type, handler, true)
    delete svg.__dragDiagnostic
    return diagnostic.logs
  })
  console.log(`[review-drag-diagnostic-events] ${JSON.stringify(dragDiagnosticEvents)}`)
  await expect.poll(async () => Number(await marker.getAttribute('cx'))).not.toBe(initialX)
  await expect.poll(async () => Number(await marker.getAttribute('cy'))).not.toBe(initialY)
  const draggedX = Number(await marker.getAttribute('cx'))
  const draggedY = Number(await marker.getAttribute('cy'))

  await editor.getByRole('button', { name: '第2杆下移' }).click()
  await editor.getByRole('button', { name: '删除第1杆' }).click()
  await editor.getByRole('button', { name: '保存全部修改' }).click()
  await expect(editor.getByRole('button', { name: '编辑落点' })).toBeVisible()
  await expect.poll(() => correctionBodies.length).toBe(1)
  expect(correctionBodies[0]).toMatchObject({ op: 'replaceHoleShots', hole: 1 })
  const postedShots = correctionBodies[0]?.shots as Array<{ id?: string; end?: [number, number] }> | undefined
  expect(postedShots).toHaveLength(3)
  expect(postedShots?.map((shot) => shot.id)).toEqual([originalShotIds[2], draggedShotId, addedShotId])
  const postedDraggedShot = postedShots?.find((shot) => shot.id === draggedShotId)
  expect(postedDraggedShot).toBeDefined()
  expect(postedDraggedShot?.end?.[0]).toBeCloseTo(draggedX, 3)
  expect(postedDraggedShot?.end?.[1]).toBeCloseTo(draggedY, 3)

  // POST success triggers one canonical shotmap GET whose mocked response carries the saved coords.
  await expect.poll(() => shotMapResponses.length).toBeGreaterThan(1)
  const refreshedShots = shotMapResponses.at(-1)?.shots as Array<{ id?: string; end?: [number, number] }> | undefined
  expect(shotMapResponses.at(-1)).toMatchObject({ mapKind: 'prodgeometry', geometryRevision: 'visual-fixture' })
  const refreshedDraggedShot = refreshedShots?.find((shot) => shot.id === draggedShotId)
  expect(refreshedDraggedShot).toBeDefined()
  expect(refreshedDraggedShot?.end?.[0]).toBeCloseTo(draggedX, 3)
  expect(refreshedDraggedShot?.end?.[1]).toBeCloseTo(draggedY, 3)
  await expect(canvas).toContainText('第 1 洞')
  expect(correctionBodies).toHaveLength(1)
})
