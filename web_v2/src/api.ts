import type {
  AnnotationCreateRequest,
  AnnotationCreateResponse,
  AnnotationListResponse,
  AnnotationTargetType,
  CaddieDecisionRequest,
  CaddieDecisionResponse,
  HistoryOverviewResponse,
  HistoryDrilldownResponse,
  HistoryRoundsResponse,
  HistoryStatsResponse,
  ReviewReportResponse,
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

export function fetchCaddieDecision(request: CaddieDecisionRequest): Promise<CaddieDecisionResponse> {
  return postJson<CaddieDecisionResponse>('/api/v2/caddie/decision', request)
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

export function fetchRoundReport(roundId: string): Promise<ReviewReportResponse> {
  return getJson<ReviewReportResponse>(`/api/v2/reports/round/${encodeURIComponent(roundId)}`)
}

export function generateRoundReport(roundId: string): Promise<ReviewReportResponse> {
  return fetch(`/api/v2/reports/round/${encodeURIComponent(roundId)}/generate`, { method: 'POST' }).then((response) => {
    if (!response.ok) {
      throw new Error(`POST /api/v2/reports/round/${roundId}/generate failed: ${response.status} ${response.statusText}`)
    }
    return response.json() as Promise<ReviewReportResponse>
  })
}

export function fetchTrendReport(period: string): Promise<ReviewReportResponse> {
  return getJson<ReviewReportResponse>(`/api/v2/reports/trend/${encodeURIComponent(period)}`)
}

export function generateTrendReport(period: string): Promise<ReviewReportResponse> {
  return fetch(`/api/v2/reports/trend/${encodeURIComponent(period)}/generate`, { method: 'POST' }).then((response) => {
    if (!response.ok) {
      throw new Error(`POST /api/v2/reports/trend/${period}/generate failed: ${response.status} ${response.statusText}`)
    }
    return response.json() as Promise<ReviewReportResponse>
  })
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
