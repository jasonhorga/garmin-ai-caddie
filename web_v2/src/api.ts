import type { HistoryOverviewResponse, HistoryRoundsResponse, HistoryStatsResponse, SyncStatusResponse } from './types'

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path)
  if (!response.ok) {
    throw new Error(`GET ${path} failed: ${response.status} ${response.statusText}`)
  }
  return response.json() as Promise<T>
}

export function fetchHistoryOverview(): Promise<HistoryOverviewResponse> {
  return getJson<HistoryOverviewResponse>('/api/v2/history/overview')
}

export function fetchHistoryRounds(): Promise<HistoryRoundsResponse> {
  return getJson<HistoryRoundsResponse>('/api/v2/history/rounds')
}

export function fetchHistoryStats(): Promise<HistoryStatsResponse> {
  return getJson<HistoryStatsResponse>('/api/v2/history/stats')
}

export function fetchSyncStatus(): Promise<SyncStatusResponse> {
  return getJson<SyncStatusResponse>('/api/v2/sync/status')
}
