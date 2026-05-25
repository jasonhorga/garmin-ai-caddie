import type {
  AnnotationCreateRequest,
  AnnotationCreateResponse,
  AnnotationListResponse,
  AnnotationTargetType,
  HistoryOverviewResponse,
  HistoryDrilldownResponse,
  HistoryRoundsResponse,
  HistoryStatsResponse,
  SyncRunResponse,
  SyncStatusResponse,
} from './types'

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path)
  if (!response.ok) {
    throw new Error(`GET ${path} failed: ${response.status} ${response.statusText}`)
  }
  return response.json() as Promise<T>
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    throw new Error(`POST ${path} failed: ${response.status} ${response.statusText}`)
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

export function fetchHistoryDrilldown(sourceRef: string): Promise<HistoryDrilldownResponse> {
  return getJson<HistoryDrilldownResponse>(`/api/v2/history/drilldown/${encodeURIComponent(sourceRef)}`)
}

export function fetchSyncStatus(): Promise<SyncStatusResponse> {
  return getJson<SyncStatusResponse>('/api/v2/sync/status')
}

export function runGarminSync(options: { withShots: boolean; forceRefreshAuth: boolean }): Promise<SyncRunResponse> {
  const params = new URLSearchParams({
    with_shots: String(options.withShots),
    force_refresh_auth: String(options.forceRefreshAuth),
  })
  return fetch(`/api/v2/sync/garmin?${params.toString()}`, { method: 'POST' }).then((response) => {
    if (!response.ok) {
      throw new Error(`POST /api/v2/sync/garmin failed: ${response.status} ${response.statusText}`)
    }
    return response.json() as Promise<SyncRunResponse>
  })
}

export function fetchAnnotations(): Promise<AnnotationListResponse> {
  return getJson<AnnotationListResponse>('/api/v2/annotations')
}

export function createAnnotation(request: AnnotationCreateRequest): Promise<AnnotationCreateResponse> {
  return postJson<AnnotationCreateResponse>('/api/v2/annotations', request)
}

export function fetchAnnotationsForTarget(
  targetType: AnnotationTargetType,
  targetId: string,
): Promise<AnnotationListResponse> {
  return getJson<AnnotationListResponse>(
    `/api/v2/annotations/target/${encodeURIComponent(targetType)}/${encodeURIComponent(targetId)}`,
  )
}
