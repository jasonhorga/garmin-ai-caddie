import { render, screen } from '@testing-library/react'
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
  }
}

describe('App sync status', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('renders overview with Garmin sync state', async () => {
    const fetchMock = vi.fn(async (path: string) => ({
      ok: true,
      json: async () => {
        if (path === '/api/v2/sync/status') return syncStatusPayload()
        return overviewPayload()
      },
    }))
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByText('History Overview')).toBeInTheDocument()
    expect(await screen.findByText('Garmin CN')).toBeInTheDocument()
    expect(screen.getByText('ready')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/history/overview')
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/sync/status')
  })
})
