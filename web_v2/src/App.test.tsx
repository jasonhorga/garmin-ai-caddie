import { render, screen, waitFor } from '@testing-library/react'
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
    clubs: [{ club: '1D', sampleCount: 2, median: 240, p10: 225, p90: 255, max: 270, confidence: 'medium' }],
    issues: [{ issue: 'missing_shots', count: 1, refs: ['900003'] }],
    dataQuality: [{ label: 'shots', state: 'partial', ready: 2, total: 3, refs: ['900003'] }],
    drillDown: { roundIds: ['900001', '900002', '900003'] },
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

describe('App navigation', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('navigates from overview to the history timeline', async () => {
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
    expect(screen.getByText('ready')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'History' }))

    expect(await screen.findByText('History Timeline')).toBeInTheDocument()
    expect(screen.getByText('May 2026')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/history/rounds')
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/sync/status')
    await waitFor(() => expect(screen.queryByText('History API unavailable')).not.toBeInTheDocument())
  })

  it('loads history stats once and navigates between stats-backed pages', async () => {
    const fetchMock = vi.fn(async (path: string) => ({
      ok: true,
      json: async () => {
        if (path === '/api/v2/history/stats') return statsPayload()
        if (path === '/api/v2/sync/status') return syncStatusPayload()
        return overviewPayload()
      },
    }))
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByText('History Overview')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Clubs' }))

    expect(await screen.findByRole('heading', { name: 'Club Stats' })).toBeInTheDocument()
    expect(screen.getByText('1D')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/history/stats')

    await userEvent.click(screen.getByRole('button', { name: 'Issues' }))

    expect(await screen.findByRole('heading', { name: 'Issue Stats' })).toBeInTheDocument()
    expect(screen.getByText('missing_shots')).toBeInTheDocument()
    expect(fetchMock.mock.calls.filter(([path]) => path === '/api/v2/history/stats')).toHaveLength(1)
  })
})
