import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  createAnnotation,
  fetchAnnotations,
  fetchAnnotationsForTarget,
  fetchHistoryOverview,
  fetchHistoryDrilldown,
  fetchHistoryRounds,
  fetchHistoryStats,
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
