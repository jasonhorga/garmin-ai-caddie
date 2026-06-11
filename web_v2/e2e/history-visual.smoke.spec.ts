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
  },
  time: {
    byYear: [{ key: '2026', roundCount: 12, average18: 82.4, bestScore: 76, roundRefs: ['900001', '900002'] }],
    byQuarter: [{ key: '2026-Q2', roundCount: 8, average18: 80.9, bestScore: 76, roundRefs: ['900001'] }],
    byMonth: [{ key: '2026-05', roundCount: 2, average18: 80.5, bestScore: 78, roundRefs: ['900001', '900002'] }],
    playFrequency: { roundsPerMonth: 3.2, activeMonths: 4 },
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
  scoring: {
    scoreBands: [
      { label: '70s', count: 3, roundRefs: ['900001'] },
      { label: '80s', count: 7, roundRefs: ['900002'] },
    ],
    outcomes: { eagleOrBetter: 1, birdie: 14, par: 94, bogey: 76, doubleOrWorse: 31 },
    phaseStats: [
      { phase: 'Tee', fairwaysHit: 6, sampleCount: 10, sourceRefs: ['900001:1'] },
      { phase: 'Approach', girPct: 44, sampleCount: 18, sourceRefs: ['900001:7'] },
      { phase: 'Putting', averagePutts: 1.9, sampleCount: 18, sourceRefs: ['900001:8'] },
    ],
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
  clubs: [
    {
      club: '1D',
      sampleCount: 16,
      median: 241,
      p10: 218,
      p90: 263,
      max: 270,
      confidence: 'medium',
      shotRefs: ['900001:1:0', '900002:4:0'],
    },
    {
      club: '8I',
      sampleCount: 21,
      median: 143,
      p10: 132,
      p90: 154,
      max: 161,
      confidence: 'high',
      shotRefs: ['900001:7:1'],
    },
  ],
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
// course options above). Hole 1 carries a rendered map (real, valid 1x1 JPEG so
// the browser raises no decode errors) plus a two-dot shot scatter; holes 2/7
// degrade without geometry. Hole 7 matches the stats.holes black_knight row so
// 关键洞 and the 逐洞速览 chip pick up 平均+1.1.
const tinyHoleJpeg =
  'data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAMCAgICAgMCAgIDAwMDBAYEBAQEBAgGBgUGCQgKCgkICQkKDA8MCgsOCwkJDRENDg8QEBEQCgwSExIQEw8QEBD/yQALCAABAAEBAREA/8wABgAQEAX/2gAIAQEAAD8A0s8g/9k='

const prepHoleOneOverlay = {
  w: 360,
  h: 360,
  ppm: 0.85,
  ln: 393,
  route: [
    [180, 330, 0],
    [176, 150, 212],
    [184, 40, 393],
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
        { x: 168, y: 150, club: '1D', shotType: 'TEE', roundId: '900001' },
        { x: 188, y: 60, club: '8I', shotType: 'APPROACH', roundId: '900002' },
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
      geometryCoverage: 'missing',
      sourceRefs: [],
      missingData: [{ label: 'geometry', reason: 'prodgeometry geometry is missing for this hole' }],
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
      geometryCoverage: 'missing',
      sourceRefs: [],
      missingData: [{ label: 'geometry', reason: 'prodgeometry geometry is missing for this hole' }],
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

const prepTipsPayload = {
  schema: 'ai-caddie-prep-tips-v1',
  courseKey: 'black_knight',
  tips: [
    {
      priority: 1,
      severity: 'high',
      text: '开球偏右(58%),第1洞、第7洞尤其要瞄球道左侧',
      basis: '开球方向:右 58% · 近20轮',
      sourceRefs: ['stats:black_knight:teeDirection'],
    },
    {
      priority: 2,
      severity: 'info',
      text: '三杆洞稳(平均+0.2),按部就班拿帕',
      basis: 'Par3 平均 +0.2 · 近20轮',
      sourceRefs: ['stats:black_knight:parScoring:par3'],
    },
  ],
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
  const { prepIncludeShots } = await mockApi(page)

  await page.goto('/')
  await expect(page.getByText('想备哪场?')).toBeVisible()
  await expect(page.getByText('Black Knight B', { exact: true })).toBeVisible()
  await assertNoViewportOverflow(page)
  await expect(page.getByText('History API unavailable')).toHaveCount(0)
  await captureSmokeScreenshot(page, testInfo, 'overview')

  // exact: home 近期状态 has a 看历史 → button whose name would substring-match 历史.
  await page.getByRole('button', { name: '历史', exact: true }).click()
  for (const [tab, heading] of [
    ['趋势总览', '成绩走势'],
    ['球局', 'Rounds'],
    ['强弱分析', 'Hole Stats'],
    ['球场', 'Course Stats'],
    ['报告', 'Reports'],
  ] as const) {
    await page.getByRole('button', { name: tab }).click()
    await expect(page.getByRole('heading', { name: heading, exact: true })).toBeVisible()
    await assertNoViewportOverflow(page)
    await expect(page.locator('text=/unavailable|failed/i')).toHaveCount(0)
  }

  await page.getByRole('button', { name: '强弱分析' }).click()
  await expect(page.getByRole('heading', { name: 'Hole Stats', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Club Stats', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Issue Stats', exact: true })).toBeVisible()
  await assertNoViewportOverflow(page)

  // prepGlobalId is null on a fresh visit, so 备战 lands on the PrepPage entry
  // state (course finder); the full prep walk runs at the end of this test.
  await page.getByRole('button', { name: '备战' }).click()
  await expect(page.getByRole('heading', { name: '选择球场开始备战' })).toBeVisible()
  await assertNoViewportOverflow(page)

  await page.getByRole('button', { name: '实战' }).click()
  await expect(page.getByRole('heading', { name: 'Caddie', exact: true })).toBeVisible()
  await assertNoViewportOverflow(page)

  await page.getByRole('button', { name: '设置' }).click()
  await expect(page.getByRole('heading', { name: 'Sync & Data Quality', exact: true })).toBeVisible()
  await expect(page.getByText('Review history')).toBeVisible()
  await assertNoViewportOverflow(page)
  await page.getByRole('button', { name: '订正' }).click()
  await expect(page.getByRole('heading', { name: 'Corrections', exact: true })).toBeVisible()
  await assertNoViewportOverflow(page)
  await page.getByRole('button', { name: '后端配置' }).click()
  await expect(page.getByRole('heading', { name: 'Settings', exact: true })).toBeVisible()
  await assertNoViewportOverflow(page)
  await captureSmokeScreenshot(page, testInfo, 'settings')

  // 备战 full walk: 概览 finder → course header → 三页签 → scatter legend.
  await page.getByRole('button', { name: '概览', exact: true }).click()
  await expect(page.getByText('想备哪场?')).toBeVisible()
  await page.getByRole('button', { name: '去备战 Black Knight B/C' }).click()

  // Course header joins courseOptions (name) + prep totals + stats record.
  await expect(page.getByRole('heading', { name: 'Black Knight B/C' })).toBeVisible()
  await expect(page.getByText('Par 11 · 总码数 1020 码')).toBeVisible()
  await expect(page.getByText('你的战绩:打过 5 次 · 均杆 80.5')).toBeVisible()

  // 概览 tab is active by default: 关键洞 (stats-backed hole 7) + 逐洞速览 chips.
  const prepTabs = page.getByRole('navigation', { name: '备战页签' })
  await expect(prepTabs.getByRole('button', { name: '概览' })).toHaveAttribute('aria-current', 'page')
  await expect(page.getByRole('heading', { name: '关键洞' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '第7洞 · Par4' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '逐洞速览' })).toBeVisible()
  await expect(page.getByRole('button', { name: '第7洞 Par4 平均+1.1' })).toBeVisible()
  await assertNoViewportOverflow(page)
  await captureSmokeScreenshot(page, testInfo, 'prep-overview')

  // 速览 chip jumps into 逐洞攻略; hole 1 card carries the mocked shot scatter.
  await page.getByRole('button', { name: '第1洞 Par4 未打过' }).click()
  await expect(prepTabs.getByRole('button', { name: '逐洞攻略' })).toHaveAttribute('aria-current', 'page')
  await expect(page.getByText('1 洞', { exact: true })).toBeVisible()
  await expect(page.getByText('你的落点:')).toBeVisible()
  await assertNoViewportOverflow(page)
  await captureSmokeScreenshot(page, testInfo, 'prep-holes')

  // 针对你 renders both mocked tips verbatim.
  await prepTabs.getByRole('button', { name: '针对你' }).click()
  await expect(page.getByText('开球偏右(58%),第1洞、第7洞尤其要瞄球道左侧')).toBeVisible()
  await expect(page.getByText('三杆洞稳(平均+0.2),按部就班拿帕')).toBeVisible()
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

  await expect(failedResponses).toEqual([])
  await expect(browserErrors).toEqual([])
})

async function mockApi(page: Page): Promise<{ prepIncludeShots: Array<string | null> }> {
  // Recorded ?include_shots values of every /prep request: the scatter walk is
  // only honest if the page actually asked the server for yourShots.
  const prepIncludeShots: Array<string | null> = []
  await page.route('**/api/v2/**', async (route) => {
    const requestUrl = new URL(route.request().url())
    const path = requestUrl.pathname
    if (path === '/api/v2/history/overview') return route.fulfill({ json: overviewPayload })
    if (path === '/api/v2/history/rounds') return route.fulfill({ json: roundsPayload })
    if (path === '/api/v2/history/stats') return route.fulfill({ json: statsPayload })
    if (path === '/api/v2/sync/status') return route.fulfill({ json: syncStatusPayload })
    if (path === '/api/v2/mobile/courses/options') return route.fulfill({ json: mobileCourseOptionsPayload })
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
    return route.fulfill({ status: 404, json: { detail: `Unhandled test route: ${path}` } })
  })
  return { prepIncludeShots }
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
  await page.screenshot({
    path: testInfo.outputPath(`${name}.png`),
    fullPage: true,
    animations: 'disabled',
  })
}
