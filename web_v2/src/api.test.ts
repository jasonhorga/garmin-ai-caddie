import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  createCaddieDecisionAudit,
  createAnnotation,
  createMedia,
  fetchCaddieContext,
  fetchCaddieDecision,
  fetchAnnotations,
  fetchAnnotationsForTarget,
  fetchCourseGeometryCoverage,
  fetchHistoryOverview,
  fetchHistoryDrilldown,
  fetchHistoryRounds,
  fetchHistoryStats,
  fetchHoleGeometryEvidence,
  fetchHoleMap,
  fetchMediaForTarget,
  fetchLatestCaddieDecisionAudit,
  fetchReadiness,
  fetchWeatherSnapshot,
  fetchReportIndex,
  fetchRoundReport,
  fetchTrendReport,
  analyzeMedia,
  generateRoundReport,
  generateTrendReport,
  fetchVisionFindingsForTarget,
  fetchSyncStatus,
  fetchMobileReconciliation,
  applyMobileReconciliationSuggestions,
  runGarminSync,
  saveGarminSession,
} from './api'

describe('fetchHistoryOverview', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
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

  it('throws a useful error when the API request fails', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
    })))

    await expect(fetchHistoryOverview()).rejects.toThrow('GET /api/v2/history/overview failed: 500 Internal Server Error')
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
    expect(fetch).toHaveBeenCalledWith('/api/v2/history/rounds')
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

    expect(fetch).toHaveBeenNthCalledWith(1, '/api/v2/reports/round/900001/generate', {
      method: 'POST',
      headers: { 'X-AI-Caddie-Admin-Token': 'admin-secret' },
    })
    expect(fetch).toHaveBeenNthCalledWith(2, '/api/v2/reports/trend/quarter%3A2026-Q2/generate', {
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

    expect(fetch).toHaveBeenNthCalledWith(1, '/api/v2/reports', {
      headers: { 'X-AI-Caddie-Admin-Token': 'admin-secret' },
    })
    expect(fetch).toHaveBeenNthCalledWith(2, '/api/v2/reports/round/900001', {
      headers: { 'X-AI-Caddie-Admin-Token': 'admin-secret' },
    })
    expect(fetch).toHaveBeenNthCalledWith(3, '/api/v2/reports/trend/quarter%3A2026-Q2', {
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
    })

    expect(fetch).toHaveBeenCalledWith(
      '/api/v2/caddie/context?source_ref=900001%3A7&shot_type=approach&distance_to_pin_m=142&lie=fairway&current_latitude=22.279&current_longitude=114.162&target_latitude=22.2799&target_longitude=114.162&strategy_mode=protect_score',
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
