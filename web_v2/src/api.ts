import type {
  AnnotationCreateRequest,
  AnnotationCreateResponse,
  AnnotationListResponse,
  AnnotationTargetType,
  CaddieDecisionRequest,
  CaddieContextParams,
  CaddieContextResponse,
  CaddieDecisionAuditLatestResponse,
  CaddieDecisionAuditRequest,
  CaddieDecisionAuditStoreResponse,
  CaddieDecisionResponse,
  HistoryOverviewResponse,
  HistoryDrilldownResponse,
  HistoryRoundsResponse,
  HistoryStatsResponse,
  CourseGeometryCoverageResponse,
  GeometryEvidenceResponse,
  HoleMapResponse,
  MediaCreateRequest,
  MediaCreateResponse,
  MediaListResponse,
  MediaTargetType,
  ReadinessResponse,
  ReviewReportResponse,
  SyncRunResponse,
  SyncStatusResponse,
  WeatherSnapshotParams,
  WeatherSnapshotResponse,
  VisionAnalysisResponse,
  VisionFindingsListResponse,
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

function appendParam(query: URLSearchParams, key: string, value: string | number | boolean | undefined): void {
  if (value !== undefined) query.append(key, String(value))
}

export function fetchHistoryOverview(): Promise<HistoryOverviewResponse> {
  return getJson<HistoryOverviewResponse>('/api/v2/history/overview')
}

export function fetchCaddieDecision(request: CaddieDecisionRequest): Promise<CaddieDecisionResponse> {
  return postJson<CaddieDecisionResponse>('/api/v2/caddie/decision', request)
}

export function fetchCaddieContext(params: CaddieContextParams): Promise<CaddieContextResponse> {
  const query = new URLSearchParams({
    source_ref: params.sourceRef,
    shot_type: params.shotType,
  })
  appendParam(query, 'distance_to_pin_m', params.distanceToPinM)
  appendParam(query, 'lie', params.lie)
  return getJson<CaddieContextResponse>(`/api/v2/caddie/context?${query.toString()}`)
}

export function createCaddieDecisionAudit(
  decisionId: string,
  request: CaddieDecisionAuditRequest,
): Promise<CaddieDecisionAuditStoreResponse> {
  return postJson<CaddieDecisionAuditStoreResponse>(
    `/api/v2/caddie/decisions/${encodeURIComponent(decisionId)}/audit`,
    request,
  )
}

export function fetchLatestCaddieDecisionAudit(decisionId: string): Promise<CaddieDecisionAuditLatestResponse> {
  return getJson<CaddieDecisionAuditLatestResponse>(
    `/api/v2/caddie/decisions/${encodeURIComponent(decisionId)}/audit/latest`,
  )
}

export function fetchWeatherSnapshot(params: WeatherSnapshotParams = {}): Promise<WeatherSnapshotResponse> {
  const query = new URLSearchParams()
  appendParam(query, 'source', params.source)
  appendParam(query, 'persist', params.persist)
  appendParam(query, 'round_id', params.roundId)
  appendParam(query, 'hole', params.hole)
  appendParam(query, 'captured_at', params.capturedAt)
  appendParam(query, 'latitude', params.latitude)
  appendParam(query, 'longitude', params.longitude)
  appendParam(query, 'wind_speed_mps', params.windSpeedMps)
  appendParam(query, 'wind_direction_deg', params.windDirectionDeg)
  appendParam(query, 'temperature_c', params.temperatureC)
  appendParam(query, 'precipitation_mm', params.precipitationMm)
  const suffix = query.toString()
  return getJson<WeatherSnapshotResponse>(`/api/v2/weather/snapshot${suffix ? `?${suffix}` : ''}`)
}

export function createMedia(request: MediaCreateRequest): Promise<MediaCreateResponse> {
  return postJson<MediaCreateResponse>('/api/v2/media', request)
}

export function fetchMediaForTarget(targetType: MediaTargetType, targetId: string): Promise<MediaListResponse> {
  return getJson<MediaListResponse>(
    `/api/v2/media/target/${encodeURIComponent(targetType)}/${encodeURIComponent(targetId)}`,
  )
}

export function analyzeMedia(mediaId: string): Promise<VisionAnalysisResponse> {
  return fetch(`/api/v2/media/${encodeURIComponent(mediaId)}/analyze`, { method: 'POST' }).then((response) => {
    if (!response.ok) {
      throw new Error(`POST /api/v2/media/${mediaId}/analyze failed: ${response.status} ${response.statusText}`)
    }
    return response.json() as Promise<VisionAnalysisResponse>
  })
}

export function fetchVisionFindingsForTarget(
  targetType: MediaTargetType,
  targetId: string,
): Promise<VisionFindingsListResponse> {
  return getJson<VisionFindingsListResponse>(
    `/api/v2/media/target/${encodeURIComponent(targetType)}/${encodeURIComponent(targetId)}/findings`,
  )
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

export function fetchCourseGeometryCoverage(
  globalId: number,
  holes: number[] = [],
): Promise<CourseGeometryCoverageResponse> {
  const query = new URLSearchParams()
  holes.forEach((hole) => query.append('holes', String(hole)))
  const suffix = query.toString()
  return getJson<CourseGeometryCoverageResponse>(
    `/api/v2/geometry/course/${encodeURIComponent(String(globalId))}/coverage${suffix ? `?${suffix}` : ''}`,
  )
}

export function fetchHoleGeometryEvidence(globalId: number, localHole: number): Promise<GeometryEvidenceResponse> {
  return getJson<GeometryEvidenceResponse>(
    `/api/v2/geometry/hole/${encodeURIComponent(String(globalId))}/${encodeURIComponent(String(localHole))}`,
  )
}

export function fetchHoleMap(
  globalId: number,
  localHole: number,
  provider = 'esri_world_imagery',
): Promise<HoleMapResponse> {
  const query = new URLSearchParams({ provider })
  return getJson<HoleMapResponse>(
    `/api/v2/geometry/hole/${encodeURIComponent(String(globalId))}/${encodeURIComponent(String(localHole))}/map?${query.toString()}`,
  )
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

export function fetchReadiness(): Promise<ReadinessResponse> {
  return getJson<ReadinessResponse>('/api/v2/readiness')
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
