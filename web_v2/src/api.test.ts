import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  createCaddieDecisionAudit,
  confirmVisionFinding,
  createAnnotation,
  createMedia,
  fetchCaddieContext,
  fetchCaddieDecision,
  fetchAnnotations,
  fetchAnnotationsForTarget,
  fetchCourseGeometryCoverage,
  fetchCoursePrep,
  fetchCourseReport,
  fetchCourseSearch,
  ensureHoleGeometry,
  fetchHistoryOverview,
  fetchHistoryDrilldown,
  fetchHistoryRounds,
  fetchHistoryRoundDetail,
  fetchHistoryStats,
  fetchHoleGeometryEvidence,
  fetchHoleMap,
  fetchMediaForTarget,
  fetchLatestCaddieDecisionAudit,
  fetchPrepTips,
  fetchReadiness,
  fetchWeatherSnapshot,
  fetchReportIndex,
  fetchRoundReport,
  fetchHoleReport,
  fetchClubReport,
  fetchTrendReport,
  analyzeMedia,
  generateCourseReport,
  generateRoundReport,
  generateHoleReport,
  generateClubReport,
  generateTrendReport,
  fetchVisionFindingsForTarget,
  fetchSyncStatus,
  fetchMobileCourseOptions,
  fetchMobileReconciliation,
  fetchMobileCoursePackage,
  fetchMobileRoundPackage,
  fetchProductSettings,
  applyMobileReconciliationSuggestions,
  redactMedia,
  runGarminSync,
  saveGarminSession,
} from './api'
import { readPlayerToken } from './playerContext'

vi.mock('./playerContext', () => ({
  readPlayerToken: vi.fn(() => null),
}))

const HISTORY_OVERVIEW_PAYLOAD = {
  schema: 'ai-caddie-history-overview-v2',
  metrics: {
    totalRounds: 0,
    eighteenHoleRounds: 0,
    nineHoleRounds: 0,
    courseCount: 0,
    shotCount: 0,
    average18: null,
    recent10Average: null,
    bestScore: null,
  },
  recentRounds: [],
  distribution: { total: 0, average: null, best: null, worst: null, families: [], histogram: [] },
  dataQuality: [],
  emptyState: null,
}

describe('player bearer token injection', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    vi.mocked(readPlayerToken).mockReturnValue(null)
  })

  it('attaches Authorization: Bearer from the player token on GET reads', async () => {
    vi.mocked(readPlayerToken).mockReturnValue('player-tok-123')
    const fetchMock = vi.fn(async () => ({ ok: true, json: async () => HISTORY_OVERVIEW_PAYLOAD }))
    vi.stubGlobal('fetch', fetchMock)

    await fetchHistoryOverview()

    expect(fetchMock).toHaveBeenCalledWith('/api/v2/history/overview', {
      headers: { Authorization: 'Bearer player-tok-123' },
    })
  })

  it('coexists with the admin token header when both are present', async () => {
    vi.mocked(readPlayerToken).mockReturnValue('player-tok-123')
    const fetchMock = vi.fn(async () => ({ ok: true, json: async () => HISTORY_OVERVIEW_PAYLOAD }))
    vi.stubGlobal('fetch', fetchMock)

    await fetchHistoryOverview('admin-secret')

    expect(fetchMock).toHaveBeenCalledWith('/api/v2/history/overview', {
      headers: { 'X-AI-Caddie-Admin-Token': 'admin-secret', Authorization: 'Bearer player-tok-123' },
    })
  })

  it('attaches Authorization: Bearer on POST writes', async () => {
    vi.mocked(readPlayerToken).mockReturnValue('player-tok-123')
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-decision-v2',
        decisionId: 'd',
        sourceRef: 's',
        evidenceRefs: [],
        shotType: 'approach',
        phase: 'Approach',
        context: {},
        options: [],
        selected: null,
        selectedOptionId: null,
        selectedOption: null,
        avoidZones: [],
        forbiddenZones: [],
        acceptableMiss: {},
        evidence: [],
        confidence: {},
        missingData: [],
        auditCriteria: [],
      }),
    }))
    vi.stubGlobal('fetch', fetchMock)

    const request = { shotType: 'approach' as const, context: { distanceToPin_m: 142 } }
    await fetchCaddieDecision(request)

    expect(fetchMock).toHaveBeenCalledWith('/api/v2/caddie/decision', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer player-tok-123' },
      body: JSON.stringify(request),
    })
  })

  it('attaches Authorization: Bearer on empty POST writes', async () => {
    vi.mocked(readPlayerToken).mockReturnValue('player-tok-123')
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-review-report-v1',
        kind: 'round',
        provider: 'StaticProvider',
        model: 'static',
        factsUsed: [],
        missingData: [],
        narrative: 'round review',
        confidence: 'medium',
      }),
    }))
    vi.stubGlobal('fetch', fetchMock)

    await generateRoundReport('900001')

    expect(fetchMock).toHaveBeenCalledWith('/api/v2/reports/round/900001/generate', {
      method: 'POST',
      headers: { Authorization: 'Bearer player-tok-123' },
    })
  })

  it('attaches Authorization: Bearer on the Garmin sync POST', async () => {
    vi.mocked(readPlayerToken).mockReturnValue('player-tok-123')
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({ schema: 'ai-caddie-sync-run-v2' }),
    }))
    vi.stubGlobal('fetch', fetchMock)

    await runGarminSync({ withShots: false, forceRefreshAuth: false })

    expect(fetchMock).toHaveBeenCalledWith('/api/v2/sync/garmin?with_shots=false&force_refresh_auth=false', {
      method: 'POST',
      headers: { Authorization: 'Bearer player-tok-123' },
    })
  })

  it('sends no Authorization header when there is no player token', async () => {
    const fetchMock = vi.fn(async () => ({ ok: true, json: async () => HISTORY_OVERVIEW_PAYLOAD }))
    vi.stubGlobal('fetch', fetchMock)

    await fetchHistoryOverview()

    expect(fetchMock).toHaveBeenCalledWith('/api/v2/history/overview')
  })
})

describe('fetchHistoryOverview', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
    vi.restoreAllMocks()
  })

  it('loads the v2 history overview payload', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-history-overview-v2',
        metrics: {
          totalRounds: 0,
          eighteenHoleRounds: 0,
          nineHoleRounds: 0,
          courseCount: 0,
          shotCount: 0,
          average18: null,
          recent10Average: null,
          bestScore: null,
        },
        recentRounds: [],
        distribution: {
          total: 0,
          average: null,
          best: null,
          worst: null,
          families: [],
          histogram: [],
        },
        dataQuality: [],
        emptyState: {
          kind: 'no_rounds',
          title: 'No Garmin rounds loaded',
          detail: 'Fetch Garmin scorecards locally, then refresh this view.',
        },
      }),
    })))

    const payload = await fetchHistoryOverview()

    expect(payload.schema).toBe('ai-caddie-history-overview-v2')
    expect(payload.metrics.totalRounds).toBe(0)
    expect(fetch).toHaveBeenCalledWith('/api/v2/history/overview')
  })

  it('uses the configured staging API base URL when Vercel hosts the web app separately', async () => {
    vi.stubEnv('VITE_AI_CADDIE_API_BASE_URL', 'https://ai-caddie-api.onrender.com/')
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-history-overview-v2',
        metrics: {
          totalRounds: 0,
          eighteenHoleRounds: 0,
          nineHoleRounds: 0,
          courseCount: 0,
          shotCount: 0,
          average18: null,
          recent10Average: null,
          bestScore: null,
        },
        recentRounds: [],
        distribution: { total: 0, average: null, best: null, worst: null, families: [], histogram: [] },
        dataQuality: [],
        emptyState: null,
      }),
    })))

    await fetchHistoryOverview()

    expect(fetch).toHaveBeenCalledWith('https://ai-caddie-api.onrender.com/api/v2/history/overview')
  })

  it('loads product settings from the settings endpoint', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-product-settings-v1',
        dataSources: [],
        aiProviders: { activeProvider: 'static', factBindingRequired: true, providers: [] },
        liveApps: {},
        privacy: {},
        endpoints: {},
      }),
    })))

    const settings = await fetchProductSettings()

    expect(fetch).toHaveBeenCalledWith('/api/v2/settings/product')
    expect(settings.schema).toBe('ai-caddie-product-settings-v1')
  })

  it('throws a useful error when the API request fails', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
    })))

    await expect(fetchHistoryOverview()).rejects.toThrow('GET /api/v2/history/overview failed: 500 Internal Server Error')
  })

  it('can attach admin tokens to protected history reads', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-history-overview-v2',
        metrics: {
          totalRounds: 0,
          eighteenHoleRounds: 0,
          nineHoleRounds: 0,
          courseCount: 0,
          shotCount: 0,
          average18: null,
          recent10Average: null,
          bestScore: null,
        },
        recentRounds: [],
        distribution: { total: 0, average: null, best: null, worst: null, families: [], histogram: [] },
        dataQuality: [],
        emptyState: null,
      }),
    }))
    vi.stubGlobal('fetch', fetchMock)

    await fetchHistoryOverview('admin-secret')

    expect(fetchMock).toHaveBeenCalledWith('/api/v2/history/overview', {
      headers: { 'X-AI-Caddie-Admin-Token': 'admin-secret' },
    })
  })
})

describe('fetchHistoryRounds', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('loads the v2 history rounds payload', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-history-rounds-v2',
        total: 0,
        groups: [],
        emptyState: {
          kind: 'no_rounds',
          title: 'No local Garmin rounds loaded',
          detail: 'The History timeline is ready, but this remote workspace has 0 rounds.',
        },
      }),
    })))

    const payload = await fetchHistoryRounds()

    expect(payload.schema).toBe('ai-caddie-history-rounds-v2')
    expect(payload.total).toBe(0)
    // backend defaults to limit=120 which truncates the real archive (435
    // rounds) — every fetch must ask for the full archive explicitly
    expect(fetch).toHaveBeenCalledWith('/api/v2/history/rounds?limit=1000')
  })

  it('keeps limit=1000 on filtered archive reads', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({ schema: 'ai-caddie-history-rounds-v2', total: 0, groups: [], emptyState: null }),
    }))
    vi.stubGlobal('fetch', fetchMock)

    await fetchHistoryRounds(undefined, { year: '2026', hasShots: true })

    expect(fetchMock).toHaveBeenCalledWith('/api/v2/history/rounds?year=2026&hasShots=true&limit=1000')
  })

  it('can attach admin tokens to protected history round reads', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({ schema: 'ai-caddie-history-rounds-v2', total: 0, groups: [], emptyState: null }),
    }))
    vi.stubGlobal('fetch', fetchMock)

    await fetchHistoryRounds('admin-secret')

    expect(fetchMock).toHaveBeenCalledWith('/api/v2/history/rounds?limit=1000', {
      headers: { 'X-AI-Caddie-Admin-Token': 'admin-secret' },
    })
  })
})

describe('fetchHistoryRoundDetail', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('loads a scorecard-first round detail payload with encoded refs', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-history-round-detail-v1',
        roundRef: 'round:900001',
        requestedRef: 'round:900001',
        found: true,
        title: 'Black Knight - 2026-05-20',
        round: { id: 'round:900001', score: 82 },
        scorecard: [{ hole: 1, par: 4, score: 4, toPar: 0, className: 'par', putts: 2, gir: true, fairway: 'hit', holeRef: 'round:900001:1', shotRefs: [], sourceRefs: [], status: 'complete' }],
        phaseSummary: [],
        holeDetails: [],
        relatedRefs: { roundRefs: ['round:900001'], holeRefs: ['round:900001:1'], shotRefs: [], sourceRefs: [] },
        sourceFields: { strokes: 82 },
        missingData: [],
      }),
    })))

    const payload = await fetchHistoryRoundDetail('round:900001')

    expect(payload.schema).toBe('ai-caddie-history-round-detail-v1')
    expect(payload.scorecard[0].holeRef).toBe('round:900001:1')
    expect(fetch).toHaveBeenCalledWith('/api/v2/history/rounds/round%3A900001')
  })

  it('can attach admin tokens to protected round detail reads', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-history-round-detail-v1',
        roundRef: '900001',
        requestedRef: '900001',
        found: true,
        title: 'Round',
        round: {},
        scorecard: [],
        phaseSummary: [],
        holeDetails: [],
        relatedRefs: { roundRefs: [], holeRefs: [], shotRefs: [], sourceRefs: [] },
        sourceFields: {},
        missingData: [],
      }),
    }))
    vi.stubGlobal('fetch', fetchMock)

    await fetchHistoryRoundDetail('900001', 'admin-secret')

    expect(fetchMock).toHaveBeenCalledWith('/api/v2/history/rounds/900001', {
      headers: { 'X-AI-Caddie-Admin-Token': 'admin-secret' },
    })
  })
})

describe('fetchHistoryStats', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('loads the v1 history stats payload', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-history-stats-v1',
        dataMode: 'fixture',
        summary: { totalRounds: 3, average18: 82 },
        time: { byMonth: [] },
        scoring: { scoreBands: [] },
        courseDistribution: [],
        records: {},
        courses: [],
        holes: [],
        clubs: [],
        issues: [],
        dataQuality: [],
        drillDown: { roundIds: [] },
      }),
    })))

    const payload = await fetchHistoryStats()

    expect(payload.schema).toBe('ai-caddie-history-stats-v1')
    expect(payload.summary.totalRounds).toBe(3)
    expect(fetch).toHaveBeenCalledWith('/api/v2/history/stats')
  })

  it('can attach admin tokens to protected history stats reads', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-history-stats-v1',
        dataMode: 'fixture',
        summary: { totalRounds: 0 },
        time: {},
        scoring: {},
        courseDistribution: [],
        records: {},
        courses: [],
        holes: [],
        clubs: [],
        issues: [],
        dataQuality: [],
        drillDown: {},
      }),
    }))
    vi.stubGlobal('fetch', fetchMock)

    await fetchHistoryStats('admin-secret')

    expect(fetchMock).toHaveBeenCalledWith('/api/v2/history/stats', {
      headers: { 'X-AI-Caddie-Admin-Token': 'admin-secret' },
    })
  })

  it('omits window query param when window is all (default)', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-history-stats-v1',
        dataMode: 'fixture',
        summary: { totalRounds: 3, average18: 82 },
        time: { byMonth: [] },
        scoring: { scoreBands: [] },
        courseDistribution: [],
        records: {},
        courses: [],
        holes: [],
        clubs: [],
        issues: [],
        dataQuality: [],
        drillDown: { roundIds: [] },
      }),
    })))

    await fetchHistoryStats(undefined, 'all')

    expect(fetch).toHaveBeenCalledWith('/api/v2/history/stats')
  })

  it('appends ?window=last10 when window is last10', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-history-stats-v1',
        dataMode: 'fixture',
        summary: { totalRounds: 3, average18: 82 },
        time: { byMonth: [] },
        scoring: { scoreBands: [] },
        courseDistribution: [],
        records: {},
        courses: [],
        holes: [],
        clubs: [],
        issues: [],
        dataQuality: [],
        drillDown: { roundIds: [] },
      }),
    })))

    await fetchHistoryStats(undefined, 'last10')

    expect(fetch).toHaveBeenCalledWith('/api/v2/history/stats?window=last10')
  })

  it('appends ?window=12m when window is 12m', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-history-stats-v1',
        dataMode: 'fixture',
        summary: { totalRounds: 3, average18: 82 },
        time: { byMonth: [] },
        scoring: { scoreBands: [] },
        courseDistribution: [],
        records: {},
        courses: [],
        holes: [],
        clubs: [],
        issues: [],
        dataQuality: [],
        drillDown: { roundIds: [] },
      }),
    })))

    await fetchHistoryStats(undefined, '12m')

    expect(fetch).toHaveBeenCalledWith('/api/v2/history/stats?window=12m')
  })
})

describe('fetchHistoryDrilldown', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('loads a source ref drill-down payload with encoded refs', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-history-drilldown-v1',
        ref: '900001:1:1',
        refType: 'shot',
        found: true,
        title: '8I on H1',
        round: { id: '900001', score: 77 },
        hole: { number: 1, par: 4, strokes: 4, toPar: 0 },
        shot: { club: '8I', distance: 142, surface: 'green' },
        relatedRefs: { roundRefs: ['900001'], holeRefs: ['900001:1'], shotRefs: ['900001:1:1'] },
        sourceFields: { globalShotIndex: 1 },
        missingData: [],
      }),
    })))

    const payload = await fetchHistoryDrilldown('900001:1:1')

    expect(payload.schema).toBe('ai-caddie-history-drilldown-v1')
    expect(payload.refType).toBe('shot')
    expect(payload.shot?.club).toBe('8I')
    expect(fetch).toHaveBeenCalledWith('/api/v2/history/drilldown/900001%3A1%3A1')
  })

  it('can attach admin tokens to protected history drilldown reads', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-history-drilldown-v1',
        ref: '900001',
        refType: 'round',
        found: true,
        title: 'Round',
        round: {},
        hole: null,
        shot: null,
        relatedRefs: {},
        sourceFields: {},
        missingData: [],
      }),
    }))
    vi.stubGlobal('fetch', fetchMock)

    await fetchHistoryDrilldown('900001', 'admin-secret')

    expect(fetchMock).toHaveBeenCalledWith('/api/v2/history/drilldown/900001', {
      headers: { 'X-AI-Caddie-Admin-Token': 'admin-secret' },
    })
  })
})

describe('report API helpers', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('loads and generates trend reports with encoded period ids', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-review-report-v1',
        kind: 'trend',
        provider: 'StaticProvider',
        model: 'static',
        factsUsed: [],
        missingData: [],
        narrative: 'trend review',
        confidence: 'medium',
      }),
    })))

    const loaded = await fetchTrendReport('quarter:2026-Q2')
    const generated = await generateTrendReport('quarter:2026-Q2')

    expect(loaded.kind).toBe('trend')
    expect(generated.narrative).toBe('trend review')
    expect(fetch).toHaveBeenNthCalledWith(1, '/api/v2/reports/trend/quarter%3A2026-Q2')
    expect(fetch).toHaveBeenNthCalledWith(2, '/api/v2/reports/trend/quarter%3A2026-Q2/generate', { method: 'POST' })
  })

  it('loads and generates course, hole, and club reports with encoded subjects', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-review-report-v1',
        kind: 'course',
        subjectId: 'black knight/c',
        provider: 'StaticProvider',
        model: 'static',
        factsUsed: [],
        missingData: [],
        inferencesMade: [],
        narrative: 'course review',
        confidence: 'medium',
      }),
    })))

    await fetchCourseReport('black knight/c')
    await generateCourseReport('black knight/c')
    await fetchHoleReport('black knight/c', 7)
    await generateHoleReport('black knight/c', 7)
    await fetchClubReport('58 wedge')
    await generateClubReport('58 wedge')

    expect(fetch).toHaveBeenNthCalledWith(1, '/api/v2/reports/course/black%20knight%2Fc')
    expect(fetch).toHaveBeenNthCalledWith(2, '/api/v2/reports/course/black%20knight%2Fc/generate', { method: 'POST' })
    expect(fetch).toHaveBeenNthCalledWith(3, '/api/v2/reports/hole/black%20knight%2Fc/7')
    expect(fetch).toHaveBeenNthCalledWith(4, '/api/v2/reports/hole/black%20knight%2Fc/7/generate', { method: 'POST' })
    expect(fetch).toHaveBeenNthCalledWith(5, '/api/v2/reports/club/58%20wedge')
    expect(fetch).toHaveBeenNthCalledWith(6, '/api/v2/reports/club/58%20wedge/generate', { method: 'POST' })
  })

  it('loads the report inventory index', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-review-report-index-v1',
        total: 1,
        reports: [
          {
            id: 'report-1',
            storedAt: '2026-05-26T00:00:00Z',
            kind: 'trend',
            subjectId: 'recent_10',
            confidence: 'medium',
            provider: 'StaticProvider',
            model: 'static',
            sourceRefs: ['900001'],
          },
        ],
      }),
    })))

    const payload = await fetchReportIndex()

    expect(payload.schema).toBe('ai-caddie-review-report-index-v1')
    expect(payload.reports[0].subjectId).toBe('recent_10')
    expect(fetch).toHaveBeenCalledWith('/api/v2/reports')
  })

  it('sends admin token headers for protected report generation', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-review-report-v1',
        kind: 'round',
        provider: 'StaticProvider',
        model: 'static',
        factsUsed: [],
        missingData: [],
        narrative: 'round review',
        confidence: 'medium',
      }),
    })))

    await generateRoundReport('900001', 'admin-secret')
    await generateTrendReport('quarter:2026-Q2', 'admin-secret')
    await generateCourseReport('black_knight', 'admin-secret')
    await generateHoleReport('black_knight', 7, 'admin-secret')
    await generateClubReport('1D', 'admin-secret')

    expect(fetch).toHaveBeenNthCalledWith(1, '/api/v2/reports/round/900001/generate', {
      method: 'POST',
      headers: { 'X-AI-Caddie-Admin-Token': 'admin-secret' },
    })
    expect(fetch).toHaveBeenNthCalledWith(2, '/api/v2/reports/trend/quarter%3A2026-Q2/generate', {
      method: 'POST',
      headers: { 'X-AI-Caddie-Admin-Token': 'admin-secret' },
    })
    expect(fetch).toHaveBeenNthCalledWith(3, '/api/v2/reports/course/black_knight/generate', {
      method: 'POST',
      headers: { 'X-AI-Caddie-Admin-Token': 'admin-secret' },
    })
    expect(fetch).toHaveBeenNthCalledWith(4, '/api/v2/reports/hole/black_knight/7/generate', {
      method: 'POST',
      headers: { 'X-AI-Caddie-Admin-Token': 'admin-secret' },
    })
    expect(fetch).toHaveBeenNthCalledWith(5, '/api/v2/reports/club/1D/generate', {
      method: 'POST',
      headers: { 'X-AI-Caddie-Admin-Token': 'admin-secret' },
    })
  })

  it('sends admin token headers for protected report reads', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-review-report-v1',
        kind: 'round',
        provider: 'StaticProvider',
        model: 'static',
        factsUsed: [],
        missingData: [],
        narrative: 'round review',
        confidence: 'medium',
      }),
    })))

    await fetchReportIndex('admin-secret')
    await fetchRoundReport('900001', 'admin-secret')
    await fetchTrendReport('quarter:2026-Q2', 'admin-secret')
    await fetchCourseReport('black_knight', 'admin-secret')
    await fetchHoleReport('black_knight', 7, 'admin-secret')
    await fetchClubReport('1D', 'admin-secret')

    expect(fetch).toHaveBeenNthCalledWith(1, '/api/v2/reports', {
      headers: { 'X-AI-Caddie-Admin-Token': 'admin-secret' },
    })
    expect(fetch).toHaveBeenNthCalledWith(2, '/api/v2/reports/round/900001', {
      headers: { 'X-AI-Caddie-Admin-Token': 'admin-secret' },
    })
    expect(fetch).toHaveBeenNthCalledWith(3, '/api/v2/reports/trend/quarter%3A2026-Q2', {
      headers: { 'X-AI-Caddie-Admin-Token': 'admin-secret' },
    })
    expect(fetch).toHaveBeenNthCalledWith(4, '/api/v2/reports/course/black_knight', {
      headers: { 'X-AI-Caddie-Admin-Token': 'admin-secret' },
    })
    expect(fetch).toHaveBeenNthCalledWith(5, '/api/v2/reports/hole/black_knight/7', {
      headers: { 'X-AI-Caddie-Admin-Token': 'admin-secret' },
    })
    expect(fetch).toHaveBeenNthCalledWith(6, '/api/v2/reports/club/1D', {
      headers: { 'X-AI-Caddie-Admin-Token': 'admin-secret' },
    })
  })
})

describe('fetchCaddieDecision', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('posts a caddie decision request', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-decision-v2',
        decisionId: 'fixture-round:4:approach',
        sourceRef: 'fixture-round:4',
        evidenceRefs: ['fixture-round:4'],
        shotType: 'approach',
        phase: 'Approach',
        context: { sourceRef: 'fixture-round:4', distanceToPin_m: 142 },
        options: [{ id: 'stock', label: 'Stock', recommendedClub: '8I' }],
        selected: { id: 'stock' },
        selectedOptionId: 'stock',
        selectedOption: { id: 'stock' },
        avoidZones: [],
        forbiddenZones: [],
        acceptableMiss: { side: 'long' },
        evidence: [{ label: 'distance', value: 142 }],
        confidence: { level: 'medium' },
        missingData: [],
        auditCriteria: [],
      }),
    })))

    const request = { shotType: 'approach' as const, context: { distanceToPin_m: 142 } }
    const payload = await fetchCaddieDecision(request)

    expect(payload.schema).toBe('ai-caddie-decision-v2')
    expect(payload.selectedOptionId).toBe('stock')
    expect(fetch).toHaveBeenCalledWith('/api/v2/caddie/decision', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    })
  })

  it('sends the admin token header for protected caddie decision requests', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-decision-v2',
        decisionId: 'fixture-round:4:approach',
        sourceRef: 'fixture-round:4',
        evidenceRefs: ['fixture-round:4'],
        shotType: 'approach',
        phase: 'Approach',
        context: {},
        options: [],
        selected: null,
        selectedOptionId: null,
        selectedOption: null,
        avoidZones: [],
        forbiddenZones: [],
        acceptableMiss: {},
        evidence: [],
        confidence: {},
        missingData: [],
        auditCriteria: [],
      }),
    })))

    const request = { shotType: 'approach' as const, context: { distanceToPin_m: 142 } }
    await fetchCaddieDecision(request, 'admin-secret')

    expect(fetch).toHaveBeenCalledWith('/api/v2/caddie/decision', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-AI-Caddie-Admin-Token': 'admin-secret' },
      body: JSON.stringify(request),
    })
  })
})

describe('fetchCaddieContext', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('loads a caddie context from a history source ref and current lie inputs', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-context-v1',
        sourceRef: '900001:7',
        shotType: 'approach',
        context: {
          source: 'history_drilldown',
          sourceRef: '900001:7',
          roundId: '900001',
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
      }),
    })))

    const payload = await fetchCaddieContext({
      sourceRef: '900001:7',
      shotType: 'approach',
      distanceToPinM: 142,
      lie: 'fairway',
      currentLatitude: 22.279,
      currentLongitude: 114.162,
      targetLatitude: 22.2799,
      targetLongitude: 114.162,
      strategyMode: 'protect_score',
      capturedAt: '2026-05-25T09:15:00Z',
    })

    expect(fetch).toHaveBeenCalledWith(
      '/api/v2/caddie/context?source_ref=900001%3A7&shot_type=approach&distance_to_pin_m=142&lie=fairway&current_latitude=22.279&current_longitude=114.162&target_latitude=22.2799&target_longitude=114.162&strategy_mode=protect_score&captured_at=2026-05-25T09%3A15%3A00Z',
    )
    expect(payload.schema).toBe('ai-caddie-context-v1')
    expect(payload.context.source).toBe('history_drilldown')
    expect(payload.context.geometry).toEqual(expect.objectContaining({ coverage: 'partial' }))
  })

  it('passes route local coordinates for geometry-bound tee context', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-context-v1',
        sourceRef: '900001:7',
        shotType: 'tee',
        context: {
          source: 'history_drilldown',
          sourceRef: '900001:7',
          routeEvidence: { routeLength_m: 182 },
        },
        evidence: [{ label: 'route_geometry', value: 'route length 182m' }],
        missingData: [],
      }),
    })))

    await fetchCaddieContext({
      sourceRef: '900001:7',
      shotType: 'tee',
      startX: 0,
      startY: 0,
      targetX: 0,
      targetY: 182,
      landingRadiusM: 18,
    })

    expect(fetch).toHaveBeenCalledWith(
      '/api/v2/caddie/context?source_ref=900001%3A7&shot_type=tee&start_x=0&start_y=0&target_x=0&target_y=182&landing_radius_m=18',
    )
  })

  it('sends the admin token header for protected context reads', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-context-v1',
        sourceRef: '900001:7',
        shotType: 'approach',
        context: { sourceRef: '900001:7' },
        evidence: [],
        missingData: [],
      }),
    })))

    await fetchCaddieContext({ sourceRef: '900001:7', shotType: 'approach' }, 'admin-secret')

    expect(fetch).toHaveBeenCalledWith(
      '/api/v2/caddie/context?source_ref=900001%3A7&shot_type=approach',
      { headers: { 'X-AI-Caddie-Admin-Token': 'admin-secret' } },
    )
  })
})

describe('caddie audit API helpers', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('creates and loads decision audits with encoded decision ids', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-decision-audit-store-v1',
        record: {
          id: 'audit-1',
          storedAt: '2026-05-25T00:00:00Z',
          decisionId: 'round-1:4:2',
          audit: {
            schema: 'ai-caddie-decision-audit-v1',
            classification: 'execution',
            plannedOptionId: 'stock',
            actualOptionId: 'stock',
          },
        },
      }),
    }))

    const request = {
      decision: { selectedOptionId: 'stock' },
      actualShot: { clubName: '8I', meters: 143 },
    }
    const created = await createCaddieDecisionAudit('round-1:4:2', request)
    await fetchLatestCaddieDecisionAudit('round-1:4:2')

    expect(fetch).toHaveBeenNthCalledWith(1, '/api/v2/caddie/decisions/round-1%3A4%3A2/audit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    })
    expect(fetch).toHaveBeenNthCalledWith(2, '/api/v2/caddie/decisions/round-1%3A4%3A2/audit/latest')
    expect(created.record.audit.classification).toBe('execution')
  })

  it('sends the admin token header for protected decision audits', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-decision-audit-store-v1',
        record: {
          id: 'audit-1',
          storedAt: '2026-05-25T00:00:00Z',
          decisionId: 'round-1:4:2',
          audit: { classification: 'execution' },
        },
      }),
    }))

    const request = {
      decision: { selectedOptionId: 'stock' },
      actualShot: { clubName: '8I', meters: 143 },
    }
    await createCaddieDecisionAudit('round-1:4:2', request, 'admin-secret')

    expect(fetch).toHaveBeenCalledWith('/api/v2/caddie/decisions/round-1%3A4%3A2/audit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-AI-Caddie-Admin-Token': 'admin-secret' },
      body: JSON.stringify(request),
    })
  })

  it('sends the admin token header for protected latest decision audit reads', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-decision-audit-latest-v1',
        record: null,
      }),
    }))

    await fetchLatestCaddieDecisionAudit('round-1:4:2', 'admin-secret')

    expect(fetch).toHaveBeenCalledWith(
      '/api/v2/caddie/decisions/round-1%3A4%3A2/audit/latest',
      { headers: { 'X-AI-Caddie-Admin-Token': 'admin-secret' } },
    )
  })
})

describe('fetchWeatherSnapshot', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('loads manual weather snapshots with caddie context params', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
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
      }),
    }))

    const data = await fetchWeatherSnapshot({
      source: 'manual',
      roundId: 'fixture-round',
      hole: 4,
      capturedAt: '2026-05-25T08:00:00Z',
      latitude: 22.279,
      longitude: 114.162,
      windSpeedMps: 5.4,
      windDirectionDeg: 110,
      temperatureC: 28.5,
      precipitationMm: 0,
    })

    expect(fetch).toHaveBeenCalledWith(
      '/api/v2/weather/snapshot?source=manual&round_id=fixture-round&hole=4&captured_at=2026-05-25T08%3A00%3A00Z&latitude=22.279&longitude=114.162&wind_speed_mps=5.4&wind_direction_deg=110&temperature_c=28.5&precipitation_mm=0',
    )
    expect(data.windSpeedMps).toBe(5.4)
  })

  it('sends the admin token header when persisting weather snapshots', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
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
      }),
    }))

    await fetchWeatherSnapshot({ source: 'manual', persist: true, roundId: 'fixture-round' }, 'admin-secret')

    expect(fetch).toHaveBeenCalledWith(
      '/api/v2/weather/snapshot?source=manual&persist=true&round_id=fixture-round',
      { headers: { 'X-AI-Caddie-Admin-Token': 'admin-secret' } },
    )
  })
})

describe('media API helpers', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('creates, lists, analyzes, and reloads vision findings for target media', async () => {
    vi.stubGlobal('fetch', vi.fn(async (path: string, init?: RequestInit) => ({
      ok: true,
      json: async () => {
        if (path === '/api/v2/media' && init?.method === 'POST') {
          return {
            schema: 'ai-caddie-media-create-v1',
            media: {
              id: 'media-1',
              createdAt: '2026-05-25T00:00:00Z',
              targetType: 'shot',
              targetId: 'round-1:4:2',
              mediaKind: 'photo',
              localPath: 'data/media/uploads/lie.jpg',
              capturedAt: '2026-05-25T08:00:00Z',
              privacyState: 'private_local',
              source: 'manual',
            },
          }
        }
        if (path === '/api/v2/media/target/shot/round-1%3A4%3A2') {
          return {
            schema: 'ai-caddie-media-list-v1',
            total: 1,
            target: { targetType: 'shot', targetId: 'round-1:4:2' },
            media: [
              {
                id: 'media-1',
                createdAt: '2026-05-25T00:00:00Z',
                targetType: 'shot',
                targetId: 'round-1:4:2',
                mediaKind: 'photo',
                localPath: 'data/media/uploads/lie.jpg',
                capturedAt: '2026-05-25T08:00:00Z',
                privacyState: 'private_local',
                source: 'manual',
              },
            ],
          }
        }
        if (path === '/api/v2/media/media-1/analyze' && init?.method === 'POST') {
          return {
            schema: 'ai-caddie-vision-context-v1',
            mediaId: 'media-1',
            targetType: 'shot',
            targetId: 'round-1:4:2',
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
        if (path === '/api/v2/media/target/shot/round-1%3A4%3A2/findings') {
          return {
            schema: 'ai-caddie-vision-findings-list-v1',
            total: 1,
            target: { targetType: 'shot', targetId: 'round-1:4:2' },
            findings: [
              {
                id: 'finding-1',
                createdAt: '2026-05-25T00:01:00Z',
                targetType: 'shot',
                targetId: 'round-1:4:2',
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
        throw new Error(`Unexpected request ${path}`)
      },
    })))

    const created = await createMedia({
      targetType: 'shot',
      targetId: 'round-1:4:2',
      mediaKind: 'photo',
      fileName: 'lie.jpg',
      contentBase64: 'ZmFrZQ==',
      capturedAt: '2026-05-25T08:00:00Z',
      privacyState: 'private_local',
    })
    const listed = await fetchMediaForTarget('shot', 'round-1:4:2')
    const analyzed = await analyzeMedia('media-1')
    const findings = await fetchVisionFindingsForTarget('shot', 'round-1:4:2')

    expect(fetch).toHaveBeenNthCalledWith(1, '/api/v2/media', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        targetType: 'shot',
        targetId: 'round-1:4:2',
        mediaKind: 'photo',
        fileName: 'lie.jpg',
        contentBase64: 'ZmFrZQ==',
        capturedAt: '2026-05-25T08:00:00Z',
        privacyState: 'private_local',
      }),
    })
    expect(fetch).toHaveBeenNthCalledWith(2, '/api/v2/media/target/shot/round-1%3A4%3A2')
    expect(fetch).toHaveBeenNthCalledWith(3, '/api/v2/media/media-1/analyze', { method: 'POST' })
    expect(fetch).toHaveBeenNthCalledWith(4, '/api/v2/media/target/shot/round-1%3A4%3A2/findings')
    expect(created.media.localPath).toBe('data/media/uploads/lie.jpg')
    expect(listed.media).toHaveLength(1)
    expect(analyzed.findings[0].findingType).toBe('visible_bunker')
    expect(findings.findings[0].evidenceText).toBe('front bunker visible')
  })

  it('sends admin token headers for protected media create and analysis', async () => {
    vi.stubGlobal('fetch', vi.fn(async (path: string) => ({
      ok: true,
      json: async () => {
        if (path === '/api/v2/media') {
          return {
            schema: 'ai-caddie-media-create-v1',
            media: {
              id: 'media-1',
              createdAt: '2026-05-25T00:00:00Z',
              targetType: 'shot',
              targetId: 'round-1:4:2',
              mediaKind: 'photo',
              localPath: 'data/media/uploads/lie.jpg',
              capturedAt: '2026-05-25T08:00:00Z',
              privacyState: 'private_local',
              source: 'manual',
            },
          }
        }
        return {
          schema: 'ai-caddie-vision-context-v1',
          mediaId: 'media-1',
          targetType: 'shot',
          targetId: 'round-1:4:2',
          mediaKind: 'photo',
          provider: 'static',
          model: 'static',
          findings: [],
        }
      },
    })))

    const request = {
      targetType: 'shot' as const,
      targetId: 'round-1:4:2',
      mediaKind: 'photo' as const,
      fileName: 'lie.jpg',
      contentBase64: 'ZmFrZQ==',
      capturedAt: '2026-05-25T08:00:00Z',
      privacyState: 'private_local' as const,
    }
    await createMedia(request, 'admin-secret')
    await analyzeMedia('media-1', 'admin-secret')

    expect(fetch).toHaveBeenNthCalledWith(1, '/api/v2/media', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-AI-Caddie-Admin-Token': 'admin-secret' },
      body: JSON.stringify(request),
    })
    expect(fetch).toHaveBeenNthCalledWith(2, '/api/v2/media/media-1/analyze', {
      method: 'POST',
      headers: { 'X-AI-Caddie-Admin-Token': 'admin-secret' },
    })
  })

  it('redacts media with an admin token header', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-media-redact-v1',
        media: {
          id: 'media-1',
          createdAt: '2026-05-25T00:00:00Z',
          targetType: 'shot',
          targetId: 'round-1:4:2',
          mediaKind: 'photo',
          localPath: '[redacted]',
          capturedAt: '2026-05-25T08:00:00Z',
          privacyState: 'redacted',
          source: 'manual',
        },
        deletedContent: true,
      }),
    }))

    const response = await redactMedia('media-1', 'admin-secret')

    expect(fetch).toHaveBeenCalledWith('/api/v2/media/media-1/redact', {
      method: 'POST',
      headers: { 'X-AI-Caddie-Admin-Token': 'admin-secret' },
    })
    expect(response.media.privacyState).toBe('redacted')
    expect(response.deletedContent).toBe(true)
  })

  it('sends admin token headers for protected media context reads', async () => {
    vi.stubGlobal('fetch', vi.fn(async (path: string) => ({
      ok: true,
      json: async () => {
        if (path === '/api/v2/media/target/shot/round-1%3A4%3A2') {
          return { schema: 'ai-caddie-media-list-v1', total: 0, target: { targetType: 'shot', targetId: 'round-1:4:2' }, media: [] }
        }
        return {
          schema: 'ai-caddie-vision-findings-list-v1',
          total: 0,
          target: { targetType: 'shot', targetId: 'round-1:4:2' },
          findings: [],
        }
      },
    })))

    await fetchMediaForTarget('shot', 'round-1:4:2', 'admin-secret')
    await fetchVisionFindingsForTarget('shot', 'round-1:4:2', 'admin-secret')

    expect(fetch).toHaveBeenNthCalledWith(1, '/api/v2/media/target/shot/round-1%3A4%3A2', {
      headers: { 'X-AI-Caddie-Admin-Token': 'admin-secret' },
    })
    expect(fetch).toHaveBeenNthCalledWith(2, '/api/v2/media/target/shot/round-1%3A4%3A2/findings', {
      headers: { 'X-AI-Caddie-Admin-Token': 'admin-secret' },
    })
  })

  it('confirms vision findings with an admin token header', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-vision-finding-confirmation-v1',
        finding: {
          id: 'finding-1',
          createdAt: '2026-05-25T00:01:00Z',
          confirmedAt: '2026-05-25T00:02:00Z',
          confirmedBy: 'tester',
          targetType: 'shot',
          targetId: 'round-1:4:2',
          mediaId: 'media-1',
          mediaKind: 'photo',
          findingType: 'visible_bunker',
          evidenceText: 'front bunker visible',
          confidence: 'medium',
          confirmationState: 'manual_confirmed',
          missingInfo: [],
          provider: 'static',
          model: 'static',
          source: 'vision_model',
        },
      }),
    }))

    const response = await confirmVisionFinding(
      'finding-1',
      { confirmationState: 'manual_confirmed', confirmedBy: 'tester' },
      'admin-secret',
    )

    expect(fetch).toHaveBeenCalledWith('/api/v2/media/findings/finding-1/confirmation', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-AI-Caddie-Admin-Token': 'admin-secret' },
      body: JSON.stringify({ confirmationState: 'manual_confirmed', confirmedBy: 'tester' }),
    })
    expect(response.schema).toBe('ai-caddie-vision-finding-confirmation-v1')
    expect(response.finding.confirmationState).toBe('manual_confirmed')
    expect(response.finding.confirmedBy).toBe('tester')
  })
})

describe('geometry API helpers', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('loads course coverage, hole evidence, and hole map DTOs', async () => {
    vi.stubGlobal('fetch', vi.fn(async (path: string) => ({
      ok: true,
      json: async () => {
        if (path === '/api/v2/geometry/course/31795/coverage?holes=1&holes=7') {
          return {
            schema: 'ai-caddie-course-geometry-coverage-v1',
            globalId: 31795,
            coverage: 'partial',
            readyHoles: 1,
            partialHoles: 0,
            totalHoles: 2,
            holes: [],
          }
        }
        if (path === '/api/v2/geometry/hole/31795/7') {
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
        if (path === '/api/v2/geometry/hole/31795/7/map?provider=esri_world_imagery') {
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
                { type: 'Feature', geometry: { type: 'Point', coordinates: [114.162, 22.279] }, properties: { layer: 'target', id: 'pin' } },
              ],
            },
            missingData: [],
          }
        }
        throw new Error(`Unexpected request ${path}`)
      },
    })))

    const coverage = await fetchCourseGeometryCoverage(31795, [1, 7])
    const evidence = await fetchHoleGeometryEvidence(31795, 7)
    const map = await fetchHoleMap(31795, 7, 'esri_world_imagery')

    expect(fetch).toHaveBeenNthCalledWith(1, '/api/v2/geometry/course/31795/coverage?holes=1&holes=7')
    expect(fetch).toHaveBeenNthCalledWith(2, '/api/v2/geometry/hole/31795/7')
    expect(fetch).toHaveBeenNthCalledWith(3, '/api/v2/geometry/hole/31795/7/map?provider=esri_world_imagery')
    expect(coverage.coverage).toBe('partial')
    expect(evidence.evidence[0].label).toBe('hazards')
    expect(map.provider.coordinateSystem).toBe('WGS84')
    expect(map.layers).toContain('target')
  })

  it('requests geometry ensure with admin token and force/profile query params', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-geometry-ensure-v1',
        status: 'downloaded',
        ok: true,
        globalId: 31795,
        localHole: 7,
        releaseSource: 'prodgeometry',
        steps: {},
      }),
    })))

    const response = await ensureHoleGeometry(31795, 7, { force: true, profileId: 'player-1' }, 'admin-secret')

    expect(fetch).toHaveBeenCalledWith('/api/v2/geometry/hole/31795/7/ensure?profile_id=player-1&force=true', {
      method: 'POST',
      headers: { 'X-AI-Caddie-Admin-Token': 'admin-secret' },
    })
    expect(response.schema).toBe('ai-caddie-geometry-ensure-v1')
    expect(response.ok).toBe(true)
  })

  it('loads source-bound hole evidence and map routes with encoded source refs', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-geometry-evidence-v1',
        globalId: 31795,
        localHole: 7,
        coverage: 'ready',
        hasHazards: true,
        hasMeshes: true,
        sourceRef: '900001:7',
        shotRoutes: [{ shotRef: '900001:7:0', club: '7I' }],
        surfaceClassifications: [{ shotRef: '900001:7:0', surface: { kind: 'green' } }],
        evidence: [],
        missingData: [],
      }),
    })))

    await fetchHoleGeometryEvidence(31795, 7, '900001:7')
    await fetchHoleMap(31795, 7, 'esri_world_imagery', '900001:7')

    expect(fetch).toHaveBeenNthCalledWith(1, '/api/v2/geometry/hole/31795/7?source_ref=900001%3A7')
    expect(fetch).toHaveBeenNthCalledWith(
      2,
      '/api/v2/geometry/hole/31795/7/map?provider=esri_world_imagery&source_ref=900001%3A7',
    )
  })

  it('loads hole evidence with route geometry query parameters', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-geometry-evidence-v1',
        globalId: 31795,
        localHole: 7,
        coverage: 'ready',
        hasHazards: true,
        hasMeshes: true,
        routeEvidence: { routeLength_m: 200 },
        evidence: [],
        missingData: [],
      }),
    })))

    await fetchHoleGeometryEvidence(31795, 7, '900001:7', {
      startX: 0,
      startY: 0,
      targetX: 200,
      targetY: 0,
      landingRadiusM: 18,
    })

    expect(fetch).toHaveBeenCalledWith(
      '/api/v2/geometry/hole/31795/7?source_ref=900001%3A7&start_x=0&start_y=0&target_x=200&target_y=0&landing_radius_m=18',
    )
  })
})

describe('fetchSyncStatus', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('fetches sync status', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-sync-status-v2',
        connector: {
          name: 'garmin_cn_web_session',
          state: 'no_data',
          detail: 'No local Garmin snapshots are loaded.',
          canSync: false,
          reauthRequired: false,
        },
        snapshot: {
          dataMode: 'fixture',
          scorecardCount: 0,
          shotFileCount: 0,
          summaryPresent: false,
          lastSuccessfulSyncAt: null,
        },
        lastRun: null,
      }),
    }))

    const data = await fetchSyncStatus()

    expect(fetch).toHaveBeenCalledWith('/api/v2/sync/status')
    expect(data.schema).toBe('ai-caddie-sync-status-v2')
    expect(data.connector.state).toBe('no_data')
  })
})

describe('fetchReadiness', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('loads private trial readiness checks', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-readiness-v1',
        status: 'degraded',
        checks: [
          {
            label: 'history',
            state: 'degraded',
            detail: 'No rounds are loaded for history review.',
            evidence: { dataMode: 'fixture', totalRounds: 0 },
          },
        ],
      }),
    }))

    const data = await fetchReadiness()

    expect(fetch).toHaveBeenCalledWith('/api/v2/readiness')
    expect(data.schema).toBe('ai-caddie-readiness-v1')
    expect(data.checks[0].label).toBe('history')
  })
})

describe('mobile reconciliation API helpers', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('loads a protected mobile round package with captured time and admin token', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-live-round-package-v1',
        roundId: 'round:1',
        dataMode: 'fixture',
        sourceCoverage: {
          state: 'ready',
          dataMode: 'fixture',
          requestedRoundId: 'round:1',
          selectedRoundId: 'round:1',
          roundFound: true,
          availableRoundCount: 3,
          holeCount: 18,
          clubProfileCount: 12,
          preparationMode: 'round',
          requestedCourseGlobalId: null,
          courseFound: true,
        },
        missingData: [],
        playerProfile: { playerId: 'player-1', displayName: 'Test Player', handedness: 'right' },
        course: { globalId: 31795, name: 'Fixture Links', teeBox: 'blue' },
        holes: [],
        geometryCoverage: { state: 'ready', readyHoles: 18, totalHoles: 18 },
        caddieContextSeeds: [],
        weatherSnapshot: { schema: 'ai-caddie-weather-snapshot-v1', state: 'ready', source: 'open_meteo', confidence: 'medium', missingData: [] },
        clubProfiles: [],
        caddieDecisionEndpoint: '/api/v2/caddie/decision',
        offlinePackageStatus: {
          state: 'ready',
          preparedAt: '2026-05-25T08:00:00Z',
          expiresAt: '2026-05-26T08:00:00Z',
          cachePolicy: { staleAfterHours: 6, expiresAfterHours: 24 },
        },
        eventCursor: { serverSequence: 0, pendingEventCount: 0 },
        recentHistory: { course: {}, rounds: [], holes: [] },
        cachedCaddieRules: { decisionContract: 'ai-caddie-decision-v2', offlineCapable: true, requiredInputs: [], degradeWhenMissing: [] },
        generatedAt: '2026-05-25T08:00:00Z',
      }),
    }))

    const data = await fetchMobileRoundPackage('round:1', { capturedAt: '2026-05-25T08:00:00Z', ensureGeometry: true }, 'admin-secret')

    expect(fetch).toHaveBeenCalledWith('/api/v2/mobile/rounds/round%3A1/package?captured_at=2026-05-25T08%3A00%3A00Z&ensure_geometry=true', {
      headers: { 'X-AI-Caddie-Admin-Token': 'admin-secret' },
    })
    expect(data.schema).toBe('ai-caddie-live-round-package-v1')
    expect(data.sourceCoverage.preparationMode).toBe('round')
  })

  it('loads a course package with optional round, tee, captured time, and admin token', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
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
        missingData: [{ label: 'weather', reason: 'weather snapshot is missing for the prepared round time' }],
        playerProfile: { playerId: 'player-1', displayName: 'Test Player', handedness: 'right' },
        course: { globalId: 31795, name: 'Fixture Links', teeBox: 'blue' },
        holes: [],
        geometryCoverage: { state: 'partial', readyHoles: 12, totalHoles: 18 },
        caddieContextSeeds: [],
        weatherSnapshot: { schema: 'ai-caddie-weather-snapshot-v1', state: 'missing', source: 'missing', confidence: 'low', missingData: [] },
        clubProfiles: [],
        caddieDecisionEndpoint: '/api/v2/caddie/decision',
        offlinePackageStatus: {
          state: 'degraded',
          preparedAt: '2026-05-25T08:00:00Z',
          expiresAt: '2026-05-26T08:00:00Z',
          cachePolicy: { staleAfterHours: 6, expiresAfterHours: 24 },
        },
        eventCursor: { serverSequence: 0, pendingEventCount: 0 },
        recentHistory: { course: {}, rounds: [], holes: [] },
        cachedCaddieRules: { decisionContract: 'ai-caddie-decision-v2', offlineCapable: true, requiredInputs: [], degradeWhenMissing: [] },
        generatedAt: '2026-05-25T08:00:00Z',
      }),
    }))

    const data = await fetchMobileCoursePackage(
      31795,
      { roundId: 'live-black-knight', teeBox: 'blue', capturedAt: '2026-05-25T08:00:00Z', ensureGeometry: true },
      'admin-secret',
    )

    expect(fetch).toHaveBeenCalledWith(
      '/api/v2/mobile/courses/31795/package?round_id=live-black-knight&tee_box=blue&captured_at=2026-05-25T08%3A00%3A00Z&ensure_geometry=true',
      { headers: { 'X-AI-Caddie-Admin-Token': 'admin-secret' } },
    )
    expect(data.roundId).toBe('live-black-knight')
    expect(data.sourceCoverage.requestedCourseGlobalId).toBe(31795)
  })

  it('loads mobile course options for start-round selection', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
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
            teeBox: 'unknown',
            geometryCoverage: 'missing',
            sourceRefs: ['900001', '900002'],
          },
        ],
        emptyState: null,
        generatedAt: '2026-05-25T08:00:00Z',
      }),
    }))

    const data = await fetchMobileCourseOptions('admin-secret')

    expect(fetch).toHaveBeenCalledWith('/api/v2/mobile/courses/options', {
      headers: { 'X-AI-Caddie-Admin-Token': 'admin-secret' },
    })
    expect(data.schema).toBe('ai-caddie-mobile-course-options-v1')
    expect(data.courses[0].suggestedLiveRoundId).toBe('live-31795')
  })

  it('loads mobile reconciliation for a round with encoded ids', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-mobile-reconciliation-v1',
        roundId: 'round:1',
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
        conflicts: [{ eventId: 'score-conflict', kind: 'score', hole: 1, localValue: 5, garminValue: 4, ref: 'round:1:1' }],
        candidateDecisionAudits: [],
        annotationSuggestions: [
          {
            id: 'score-conflict:score-correction',
            targetType: 'hole',
            targetId: 'round:1:1',
            kind: 'score_correction',
            payload: { from: 4, to: 5, sourceEventId: 'score-conflict' },
            reason: 'Local score input can correct the derived score for this hole.',
            confidence: 'medium',
          },
        ],
      }),
    }))

    const data = await fetchMobileReconciliation('round:1')

    expect(fetch).toHaveBeenCalledWith('/api/v2/mobile/rounds/round%3A1/reconciliation')
    expect(data.schema).toBe('ai-caddie-mobile-reconciliation-v1')
    expect(data.annotationSuggestions[0].kind).toBe('score_correction')
  })

  it('sends the admin token header for protected mobile reconciliation reads', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-mobile-reconciliation-v1',
        roundId: '900001',
        summary: {
          eventCount: 0,
          matchedCount: 0,
          localOnlyCount: 0,
          garminOnlyCount: 0,
          conflictCount: 0,
          candidateDecisionAuditCount: 0,
          annotationSuggestionCount: 0,
        },
        matched: [],
        localOnly: [],
        garminOnly: [],
        conflicts: [],
        candidateDecisionAudits: [],
        annotationSuggestions: [],
      }),
    }))

    await fetchMobileReconciliation('900001', 'admin-secret')

    expect(fetch).toHaveBeenCalledWith('/api/v2/mobile/rounds/900001/reconciliation', {
      headers: { 'X-AI-Caddie-Admin-Token': 'admin-secret' },
    })
  })

  it('applies selected mobile reconciliation suggestions', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-mobile-reconciliation-apply-v1',
        roundId: '900001',
        appliedCount: 1,
        skippedCount: 0,
        missingSuggestionIds: [],
        skippedSuggestionIds: [],
        annotations: [
          {
            id: 'ann-1',
            createdAt: '2026-05-25T11:00:00Z',
            targetType: 'hole',
            targetId: '900001:1',
            kind: 'putt_correction',
            payload: { from: 2, to: 3, sourceSuggestionId: 'putt-conflict:putt-correction' },
            source: 'manual',
          },
        ],
      }),
    }))

    const data = await applyMobileReconciliationSuggestions('900001', ['putt-conflict:putt-correction'])

    expect(fetch).toHaveBeenCalledWith('/api/v2/mobile/rounds/900001/reconciliation/apply', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ suggestionIds: ['putt-conflict:putt-correction'] }),
    })
    expect(data.appliedCount).toBe(1)
    expect(data.annotations[0].kind).toBe('putt_correction')
  })

  it('sends the admin token header for protected mobile reconciliation apply', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-mobile-reconciliation-apply-v1',
        roundId: '900001',
        appliedCount: 0,
        skippedCount: 0,
        missingSuggestionIds: [],
        skippedSuggestionIds: [],
        annotations: [],
      }),
    }))

    await applyMobileReconciliationSuggestions('900001', ['score-conflict:score-correction'], 'admin-secret')

    expect(fetch).toHaveBeenCalledWith('/api/v2/mobile/rounds/900001/reconciliation/apply', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-AI-Caddie-Admin-Token': 'admin-secret' },
      body: JSON.stringify({ suggestionIds: ['score-conflict:score-correction'] }),
    })
  })
})

describe('runGarminSync', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
    vi.restoreAllMocks()
  })

  it('posts the Garmin sync run request', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-sync-run-v2',
        connector: 'garmin_cn_web_session',
        state: 'ready',
        detail: 'Garmin CN sync completed.',
        reauthRequired: false,
        errorCode: null,
        snapshot: {
          snapshotId: 'snap_1',
          scorecardCount: 2,
          shotFileCount: 1,
          summaryPresent: true,
          files: ['data/summary.json'],
        },
      }),
    }))

    const data = await runGarminSync({ withShots: true, forceRefreshAuth: false })

    expect(fetch).toHaveBeenCalledWith('/api/v2/sync/garmin?with_shots=true&force_refresh_auth=false', {
      method: 'POST',
    })
    expect(data.schema).toBe('ai-caddie-sync-run-v2')
    expect(data.snapshot?.snapshotId).toBe('snap_1')
  })

  it('sends the admin token header for protected Garmin sync runs', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-sync-run-v2',
        connector: 'garmin_cn_web_session',
        state: 'ready',
        detail: 'Garmin CN sync completed.',
        reauthRequired: false,
        errorCode: null,
        snapshot: null,
      }),
    }))

    await runGarminSync({ withShots: true, forceRefreshAuth: false, adminToken: 'admin-secret' })

    expect(fetch).toHaveBeenCalledWith('/api/v2/sync/garmin?with_shots=true&force_refresh_auth=false', {
      method: 'POST',
      headers: { 'X-AI-Caddie-Admin-Token': 'admin-secret' },
    })
  })

  it('uses the configured staging API base URL for Garmin sync runs', async () => {
    vi.stubEnv('VITE_AI_CADDIE_API_BASE_URL', 'https://ai-caddie-api.onrender.com/')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-sync-run-v2',
        connector: 'garmin_cn_web_session',
        state: 'ready',
        detail: 'Garmin CN sync completed.',
        reauthRequired: false,
        errorCode: null,
        snapshot: null,
      }),
    }))

    await runGarminSync({ withShots: true, forceRefreshAuth: true, adminToken: 'admin-secret' })

    expect(fetch).toHaveBeenCalledWith('https://ai-caddie-api.onrender.com/api/v2/sync/garmin?with_shots=true&force_refresh_auth=true', {
      method: 'POST',
      headers: { 'X-AI-Caddie-Admin-Token': 'admin-secret' },
    })
  })
})

describe('saveGarminSession', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('posts manual Garmin session material without expecting echoed values', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-garmin-session-import-v1',
        connector: 'garmin_cn_web_session',
        state: 'stored',
        detail: 'Garmin CN web session saved for local sync.',
        sessionFieldCount: 2,
        antiForgeryPresent: true,
        source: 'manual_paste',
      }),
    }))

    const data = await saveGarminSession({
      webSessionHeader: 'Cookie: JWT_WEB=abc123',
      antiForgeryValue: 'connect-csrf-token: csrf-secret-value',
    })

    expect(fetch).toHaveBeenCalledWith('/api/v2/sync/garmin/session', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        webSessionHeader: 'Cookie: JWT_WEB=abc123',
        antiForgeryValue: 'connect-csrf-token: csrf-secret-value',
      }),
    })
    expect(data.schema).toBe('ai-caddie-garmin-session-import-v1')
    expect(JSON.stringify(data)).not.toContain('abc123')
    expect(JSON.stringify(data)).not.toContain('csrf-secret-value')
  })

  it('sends the admin token header for protected Garmin session imports', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-garmin-session-import-v1',
        connector: 'garmin_cn_web_session',
        state: 'stored',
        detail: 'Garmin CN web session saved for local sync.',
        sessionFieldCount: 1,
        antiForgeryPresent: true,
        source: 'manual_paste',
      }),
    }))

    const request = {
      webSessionHeader: 'Cookie: JWT_WEB=abc123',
      antiForgeryValue: 'connect-csrf-token: csrf-secret-value',
    }
    await saveGarminSession(request, 'admin-secret')

    expect(fetch).toHaveBeenCalledWith('/api/v2/sync/garmin/session', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-AI-Caddie-Admin-Token': 'admin-secret' },
      body: JSON.stringify(request),
    })
  })
})

describe('annotation API helpers', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('loads annotation history', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-annotations-v1',
        total: 1,
        target: null,
        annotations: [
          {
            id: 'ann-1',
            createdAt: '2026-05-25T10:30:00Z',
            targetType: 'shot',
            targetId: 'round-1:7:shot-3',
            kind: 'club_correction',
            payload: { from: '7I', to: '8I' },
            source: 'manual',
          },
        ],
      }),
    }))

    const data = await fetchAnnotations()

    expect(fetch).toHaveBeenCalledWith('/api/v2/annotations')
    expect(data.schema).toBe('ai-caddie-annotations-v1')
    expect(data.annotations[0].kind).toBe('club_correction')
  })

  it('creates annotations with the backend POST contract', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-annotation-create-v1',
        annotation: {
          id: 'ann-2',
          createdAt: '2026-05-25T10:35:00Z',
          targetType: 'hole',
          targetId: 'round-1:7',
          kind: 'issue_tag',
          payload: { tag: 'approach_short' },
          source: 'manual',
        },
      }),
    }))

    const request = {
      targetType: 'hole' as const,
      targetId: 'round-1:7',
      kind: 'issue_tag' as const,
      payload: { tag: 'approach_short' },
    }
    const data = await createAnnotation(request)

    expect(fetch).toHaveBeenCalledWith('/api/v2/annotations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    })
    expect(data.schema).toBe('ai-caddie-annotation-create-v1')
    expect(data.annotation.id).toBe('ann-2')
  })

  it('sends the admin token header for protected annotation creation', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-annotation-create-v1',
        annotation: {
          id: 'ann-2',
          createdAt: '2026-05-25T10:35:00Z',
          targetType: 'hole',
          targetId: 'round-1:7',
          kind: 'issue_tag',
          payload: { tag: 'approach_short' },
          source: 'manual',
        },
      }),
    }))

    const request = {
      targetType: 'hole' as const,
      targetId: 'round-1:7',
      kind: 'issue_tag' as const,
      payload: { tag: 'approach_short' },
    }
    await createAnnotation(request, 'admin-secret')

    expect(fetch).toHaveBeenCalledWith('/api/v2/annotations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-AI-Caddie-Admin-Token': 'admin-secret' },
      body: JSON.stringify(request),
    })
  })

  it('loads annotation history for a target', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-annotations-v1',
        total: 0,
        target: { targetType: 'hole', targetId: 'round-1:7' },
        annotations: [],
      }),
    }))

    const data = await fetchAnnotationsForTarget('hole', 'round-1:7')

    expect(fetch).toHaveBeenCalledWith('/api/v2/annotations/target/hole/round-1%3A7')
    expect(data.target).toEqual({ targetType: 'hole', targetId: 'round-1:7' })
  })

  it('sends the admin token header for protected annotation reads', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-annotations-v1',
        total: 0,
        target: null,
        annotations: [],
      }),
    }))

    await fetchAnnotations('admin-secret')
    await fetchAnnotationsForTarget('hole', 'round-1:7', 'admin-secret')

    expect(fetch).toHaveBeenNthCalledWith(1, '/api/v2/annotations', {
      headers: { 'X-AI-Caddie-Admin-Token': 'admin-secret' },
    })
    expect(fetch).toHaveBeenNthCalledWith(2, '/api/v2/annotations/target/hole/round-1%3A7', {
      headers: { 'X-AI-Caddie-Admin-Token': 'admin-secret' },
    })
  })
})

describe('fetchCourseSearch', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('URL-encodes CJK course name and passes response through', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-course-search-v1',
        query: '观澜湖',
        matches: [
          {
            globalId: 12345,
            name: '观澜湖高尔夫球会',
            holes: 18,
            city: '深圳',
            province: '广东',
            ratio: 0.92,
          },
        ],
      }),
    })))

    const result = await fetchCourseSearch('观澜湖')

    expect(fetch).toHaveBeenCalledWith(`/api/v2/courses/search?name=${encodeURIComponent('观澜湖')}`)
    expect(result.schema).toBe('ai-caddie-course-search-v1')
    expect(result.query).toBe('观澜湖')
    expect(result.matches[0].globalId).toBe(12345)
    expect(result.matches[0].ratio).toBe(0.92)
    expect(result.matches[0].city).toBe('深圳')
  })

  it('sends admin token for protected course search reads', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-course-search-v1',
        query: 'black knight',
        matches: [],
      }),
    })))

    await fetchCourseSearch('black knight', 'admin-secret')

    expect(fetch).toHaveBeenCalledWith(`/api/v2/courses/search?name=${encodeURIComponent('black knight')}`, {
      headers: { 'X-AI-Caddie-Admin-Token': 'admin-secret' },
    })
  })
})

describe('fetchPrepTips', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('loads prep tips for a course globalId from the correct endpoint', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-prep-tips-v1',
        courseKey: 'black_knight',
        tips: [
          {
            priority: 1,
            severity: 'high',
            text: '开球偏左(62%),瞄球道右侧留余量;第3洞有水/沙,尤其当心',
            basis: 'course.teeDirection',
            sourceRefs: ['course:31795'],
          },
          {
            priority: 2,
            severity: 'medium',
            text: '攻果岭常偏短(41%),本场多带半杆',
            basis: 'course.approachMiss',
            sourceRefs: [],
          },
        ],
      }),
    })))

    const result = await fetchPrepTips(31795)

    expect(fetch).toHaveBeenCalledWith('/api/v2/courses/31795/prep-tips')
    expect(result.schema).toBe('ai-caddie-prep-tips-v1')
    expect(result.courseKey).toBe('black_knight')
    expect(result.tips).toHaveLength(2)
    expect(result.tips[0].severity).toBe('high')
    expect(result.tips[0].priority).toBe(1)
    expect(result.tips[1].basis).toBe('course.approachMiss')
  })

  it('returns null courseKey for a course that has never been played', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-prep-tips-v1',
        courseKey: null,
        tips: [
          {
            priority: 1,
            severity: 'info',
            text: '新球场:按 HCP 与长度提示,关注最长的第4洞、第7洞、第2洞',
            basis: 'course.prepHoles',
            sourceRefs: [],
          },
        ],
      }),
    })))

    const result = await fetchPrepTips(99999)

    expect(fetch).toHaveBeenCalledWith('/api/v2/courses/99999/prep-tips')
    expect(result.courseKey).toBeNull()
    expect(result.tips[0].severity).toBe('info')
  })

  it('sends admin token header for protected prep-tips reads', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-prep-tips-v1',
        courseKey: null,
        tips: [],
      }),
    }))
    vi.stubGlobal('fetch', fetchMock)

    await fetchPrepTips(31795, 'admin-secret')

    expect(fetchMock).toHaveBeenCalledWith('/api/v2/courses/31795/prep-tips', {
      headers: { 'X-AI-Caddie-Admin-Token': 'admin-secret' },
    })
  })

  it('throws a useful error when the prep-tips request fails', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: false,
      status: 403,
      statusText: 'Forbidden',
    })))

    await expect(fetchPrepTips(31795)).rejects.toThrow(
      'GET /api/v2/courses/31795/prep-tips failed: 403 Forbidden',
    )
  })
})

describe('fetchCoursePrep', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('calls the prep endpoint with no query string by default', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-course-prep-v1',
        globalId: 31795,
        holeCount: 9,
        clubs: [],
        holes: [],
      }),
    })))

    const result = await fetchCoursePrep(31795)

    expect(fetch).toHaveBeenCalledWith('/api/v2/courses/31795/prep')
    expect(result.schema).toBe('ai-caddie-course-prep-v1')
    expect(result.globalId).toBe(31795)
  })

  it('appends include_shots=true when includeShots option is true', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-course-prep-v1',
        globalId: 31870,
        holeCount: 9,
        clubs: [],
        holes: [
          {
            hole: 3,
            par: 4,
            par_source: 'courseview',
            blue_yards: 380,
            route_len_m: 347,
            route: [],
            geometryCoverage: 'ready',
            sourceRefs: ['course:31870'],
            missingData: [],
            candidateRoutes: [],
            carryTargets: [],
            steps: [],
            cautions: [],
            landing_m: null,
            tee_club: '1D',
            hazards: { water_carry: [], bunkers: [] },
            map: { image: 'base64img', overlay: { w: 200, h: 400, ppm: 2.5, ln: 347, route: [] } },
            yourShots: [
              { x: 45, y: 120, club: '1D', shotType: 'TEE', roundId: 'round-900001' },
              { x: 100, y: 280, club: '7I', shotType: 'APPROACH', roundId: 'round-900001' },
            ],
          },
        ],
      }),
    })))

    const result = await fetchCoursePrep(31870, { includeShots: true })

    expect(fetch).toHaveBeenCalledWith('/api/v2/courses/31870/prep?include_shots=true')
    expect(result.holes[0].yourShots).toHaveLength(2)
    expect(result.holes[0].yourShots![0].shotType).toBe('TEE')
    expect(result.holes[0].yourShots![1].club).toBe('7I')
    expect(result.holes[0].yourShots![1].roundId).toBe('round-900001')
  })

  it('omits include_shots when includeShots is false or undefined', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-course-prep-v1',
        globalId: 31795,
        holeCount: 9,
        clubs: [],
        holes: [],
      }),
    })))

    await fetchCoursePrep(31795, { includeShots: false })
    await fetchCoursePrep(31795, {})

    expect(fetch).toHaveBeenNthCalledWith(1, '/api/v2/courses/31795/prep')
    expect(fetch).toHaveBeenNthCalledWith(2, '/api/v2/courses/31795/prep')
  })

  it('combines render=false with include_shots=true in the query string', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-course-prep-v1',
        globalId: 31795,
        holeCount: 9,
        clubs: [],
        holes: [],
      }),
    })))

    await fetchCoursePrep(31795, { render: false, includeShots: true })

    expect(fetch).toHaveBeenCalledWith('/api/v2/courses/31795/prep?render=false&include_shots=true')
  })

  it('combines specific holes with include_shots in the query string', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-course-prep-v1',
        globalId: 31795,
        holeCount: 9,
        clubs: [],
        holes: [],
      }),
    })))

    await fetchCoursePrep(31795, { holes: [1, 3], includeShots: true })

    expect(fetch).toHaveBeenCalledWith('/api/v2/courses/31795/prep?holes=1&holes=3&include_shots=true')
  })

  it('sends admin token header for protected prep reads', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        schema: 'ai-caddie-course-prep-v1',
        globalId: 31795,
        holeCount: 9,
        clubs: [],
        holes: [],
      }),
    }))
    vi.stubGlobal('fetch', fetchMock)

    await fetchCoursePrep(31795, { includeShots: true }, 'admin-secret')

    expect(fetchMock).toHaveBeenCalledWith('/api/v2/courses/31795/prep?include_shots=true', {
      headers: { 'X-AI-Caddie-Admin-Token': 'admin-secret' },
    })
  })
})
