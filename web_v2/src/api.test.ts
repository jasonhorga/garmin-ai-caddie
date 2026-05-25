import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  createCaddieDecisionAudit,
  createAnnotation,
  createMedia,
  fetchCaddieDecision,
  fetchAnnotations,
  fetchAnnotationsForTarget,
  fetchHistoryOverview,
  fetchHistoryDrilldown,
  fetchHistoryRounds,
  fetchHistoryStats,
  fetchMediaForTarget,
  fetchLatestCaddieDecisionAudit,
  fetchReadiness,
  fetchWeatherSnapshot,
  fetchTrendReport,
  analyzeMedia,
  generateTrendReport,
  fetchVisionFindingsForTarget,
  fetchSyncStatus,
  runGarminSync,
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
        shotType: 'approach',
        phase: 'Approach',
        context: { distanceToPin_m: 142 },
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
})
