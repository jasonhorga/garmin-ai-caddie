import type {
  AnnotationCreateRequest,
  AnnotationCreateResponse,
  AnnotationListResponse,
  AnnotationTargetType,
  HistoryOverviewResponse,
  HistoryRoundsResponse,
  HistoryStatsResponse,
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

export function fetchSyncStatus(): Promise<SyncStatusResponse> {
  return getJson<SyncStatusResponse>('/api/v2/sync/status')
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
