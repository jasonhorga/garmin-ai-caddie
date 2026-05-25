import { afterEach, describe, expect, it, vi } from 'vitest'
import { fetchHistoryOverview, fetchSyncStatus } from './api'

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
      }),
    }))

    const data = await fetchSyncStatus()

    expect(fetch).toHaveBeenCalledWith('/api/v2/sync/status')
    expect(data.schema).toBe('ai-caddie-sync-status-v2')
    expect(data.connector.state).toBe('no_data')
  })
})
