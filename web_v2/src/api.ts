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
  HoleGeometryRouteParams,
  GarminSessionImportRequest,
  GarminSessionImportResponse,
  HoleMapResponse,
  MediaCreateRequest,
  MediaCreateResponse,
  MediaListResponse,
  MediaTargetType,
  MobileReconciliationApplyResponse,
  MobileReconciliationResponse,
  ReadinessResponse,
  ReviewReportIndexResponse,
  ReviewReportResponse,
  SyncRunResponse,
  SyncStatusResponse,
  WeatherSnapshotParams,
  WeatherSnapshotResponse,
  VisionAnalysisResponse,
  VisionFindingsListResponse,
} from './types'

async function getJson<T>(path: string, adminToken?: string): Promise<T> {
  const headers = adminTokenHeader(adminToken)
  const init = Object.keys(headers).length ? { headers } : undefined
  const response = init ? await fetch(path, init) : await fetch(path)
  if (!response.ok) {
    throw new Error(`GET ${path} failed: ${response.status} ${response.statusText}`)
  }
  return response.json() as Promise<T>
}

function adminTokenHeader(adminToken?: string): Record<string, string> {
  const trimmed = adminToken?.trim()
  return trimmed ? { 'X-AI-Caddie-Admin-Token': trimmed } : {}
}

async function postJson<T>(path: string, body: unknown, adminToken?: string): Promise<T> {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...adminTokenHeader(adminToken) },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    throw new Error(`POST ${path} failed: ${response.status} ${response.statusText}`)
  }
  return response.json() as Promise<T>
}

async function postEmpty<T>(path: string, adminToken?: string): Promise<T> {
  const headers = adminTokenHeader(adminToken)
  const init: RequestInit = { method: 'POST' }
  if (Object.keys(headers).length) init.headers = headers
  const response = await fetch(path, init)
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

export function fetchCaddieDecision(request: CaddieDecisionRequest, adminToken?: string): Promise<CaddieDecisionResponse> {
  return postJson<CaddieDecisionResponse>('/api/v2/caddie/decision', request, adminToken)
}

export function fetchCaddieContext(params: CaddieContextParams, adminToken?: string): Promise<CaddieContextResponse> {
  const query = new URLSearchParams({
    source_ref: params.sourceRef,
    shot_type: params.shotType,
  })
  appendParam(query, 'distance_to_pin_m', params.distanceToPinM)
  appendParam(query, 'lie', params.lie)
  appendParam(query, 'current_latitude', params.currentLatitude)
  appendParam(query, 'current_longitude', params.currentLongitude)
  appendParam(query, 'target_latitude', params.targetLatitude)
  appendParam(query, 'target_longitude', params.targetLongitude)
  appendParam(query, 'strategy_mode', params.strategyMode)
  appendParam(query, 'start_x', params.startX)
  appendParam(query, 'start_y', params.startY)
  appendParam(query, 'target_x', params.targetX)
  appendParam(query, 'target_y', params.targetY)
  appendParam(query, 'landing_radius_m', params.landingRadiusM)
  return getJson<CaddieContextResponse>(`/api/v2/caddie/context?${query.toString()}`, adminToken)
}

export function createCaddieDecisionAudit(
  decisionId: string,
  request: CaddieDecisionAuditRequest,
  adminToken?: string,
): Promise<CaddieDecisionAuditStoreResponse> {
  return postJson<CaddieDecisionAuditStoreResponse>(
    `/api/v2/caddie/decisions/${encodeURIComponent(decisionId)}/audit`,
    request,
    adminToken,
  )
}

export function fetchLatestCaddieDecisionAudit(decisionId: string, adminToken?: string): Promise<CaddieDecisionAuditLatestResponse> {
  return getJson<CaddieDecisionAuditLatestResponse>(
    `/api/v2/caddie/decisions/${encodeURIComponent(decisionId)}/audit/latest`,
    adminToken,
  )
}

export function fetchWeatherSnapshot(params: WeatherSnapshotParams = {}, adminToken?: string): Promise<WeatherSnapshotResponse> {
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
  return getJson<WeatherSnapshotResponse>(`/api/v2/weather/snapshot${suffix ? `?${suffix}` : ''}`, adminToken)
}

export function createMedia(request: MediaCreateRequest, adminToken?: string): Promise<MediaCreateResponse> {
  return postJson<MediaCreateResponse>('/api/v2/media', request, adminToken)
}

export function fetchMediaForTarget(targetType: MediaTargetType, targetId: string, adminToken?: string): Promise<MediaListResponse> {
  return getJson<MediaListResponse>(
    `/api/v2/media/target/${encodeURIComponent(targetType)}/${encodeURIComponent(targetId)}`,
    adminToken,
  )
}

export function analyzeMedia(mediaId: string, adminToken?: string): Promise<VisionAnalysisResponse> {
  return postEmpty<VisionAnalysisResponse>(`/api/v2/media/${encodeURIComponent(mediaId)}/analyze`, adminToken)
}

export function fetchVisionFindingsForTarget(
  targetType: MediaTargetType,
  targetId: string,
  adminToken?: string,
): Promise<VisionFindingsListResponse> {
  return getJson<VisionFindingsListResponse>(
    `/api/v2/media/target/${encodeURIComponent(targetType)}/${encodeURIComponent(targetId)}/findings`,
    adminToken,
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

export function fetchHoleGeometryEvidence(
  globalId: number,
  localHole: number,
  sourceRef?: string,
  routeParams: HoleGeometryRouteParams = {},
): Promise<GeometryEvidenceResponse> {
  const query = new URLSearchParams()
  appendParam(query, 'source_ref', sourceRef)
  appendParam(query, 'start_x', routeParams.startX)
  appendParam(query, 'start_y', routeParams.startY)
  appendParam(query, 'target_x', routeParams.targetX)
  appendParam(query, 'target_y', routeParams.targetY)
  appendParam(query, 'landing_radius_m', routeParams.landingRadiusM)
  const suffix = query.toString()
  return getJson<GeometryEvidenceResponse>(
    `/api/v2/geometry/hole/${encodeURIComponent(String(globalId))}/${encodeURIComponent(String(localHole))}${suffix ? `?${suffix}` : ''}`,
  )
}

export function fetchHoleMap(
  globalId: number,
  localHole: number,
  provider = 'esri_world_imagery',
  sourceRef?: string,
): Promise<HoleMapResponse> {
  const query = new URLSearchParams({ provider })
  appendParam(query, 'source_ref', sourceRef)
  return getJson<HoleMapResponse>(
    `/api/v2/geometry/hole/${encodeURIComponent(String(globalId))}/${encodeURIComponent(String(localHole))}/map?${query.toString()}`,
  )
}

export function fetchRoundReport(roundId: string, adminToken?: string): Promise<ReviewReportResponse> {
  return getJson<ReviewReportResponse>(`/api/v2/reports/round/${encodeURIComponent(roundId)}`, adminToken)
}

export function fetchReportIndex(adminToken?: string): Promise<ReviewReportIndexResponse> {
  return getJson<ReviewReportIndexResponse>('/api/v2/reports', adminToken)
}

export function generateRoundReport(roundId: string, adminToken?: string): Promise<ReviewReportResponse> {
  return postEmpty<ReviewReportResponse>(`/api/v2/reports/round/${encodeURIComponent(roundId)}/generate`, adminToken)
}

export function fetchTrendReport(period: string, adminToken?: string): Promise<ReviewReportResponse> {
  return getJson<ReviewReportResponse>(`/api/v2/reports/trend/${encodeURIComponent(period)}`, adminToken)
}

export function generateTrendReport(period: string, adminToken?: string): Promise<ReviewReportResponse> {
  return postEmpty<ReviewReportResponse>(`/api/v2/reports/trend/${encodeURIComponent(period)}/generate`, adminToken)
}

export function fetchSyncStatus(): Promise<SyncStatusResponse> {
  return getJson<SyncStatusResponse>('/api/v2/sync/status')
}

export function fetchReadiness(): Promise<ReadinessResponse> {
  return getJson<ReadinessResponse>('/api/v2/readiness')
}

export function fetchMobileReconciliation(roundId: string): Promise<MobileReconciliationResponse> {
  return getJson<MobileReconciliationResponse>(`/api/v2/mobile/rounds/${encodeURIComponent(roundId)}/reconciliation`)
}

export function applyMobileReconciliationSuggestions(
  roundId: string,
  suggestionIds: string[],
  adminToken?: string,
): Promise<MobileReconciliationApplyResponse> {
  return postJson<MobileReconciliationApplyResponse>(
    `/api/v2/mobile/rounds/${encodeURIComponent(roundId)}/reconciliation/apply`,
    { suggestionIds },
    adminToken,
  )
}

export function runGarminSync(options: { withShots: boolean; forceRefreshAuth: boolean; adminToken?: string }): Promise<SyncRunResponse> {
  const params = new URLSearchParams({
    with_shots: String(options.withShots),
    force_refresh_auth: String(options.forceRefreshAuth),
  })
  const headers = adminTokenHeader(options.adminToken)
  const init: RequestInit = { method: 'POST' }
  if (Object.keys(headers).length) init.headers = headers
  return fetch(`/api/v2/sync/garmin?${params.toString()}`, init).then((response) => {
    if (!response.ok) {
      throw new Error(`POST /api/v2/sync/garmin failed: ${response.status} ${response.statusText}`)
    }
    return response.json() as Promise<SyncRunResponse>
  })
}

export function saveGarminSession(request: GarminSessionImportRequest, adminToken?: string): Promise<GarminSessionImportResponse> {
  return postJson<GarminSessionImportResponse>('/api/v2/sync/garmin/session', request, adminToken)
}

export function fetchAnnotations(adminToken?: string): Promise<AnnotationListResponse> {
  return getJson<AnnotationListResponse>('/api/v2/annotations', adminToken)
}

export function createAnnotation(request: AnnotationCreateRequest, adminToken?: string): Promise<AnnotationCreateResponse> {
  return postJson<AnnotationCreateResponse>('/api/v2/annotations', request, adminToken)
}

export function fetchAnnotationsForTarget(
  targetType: AnnotationTargetType,
  targetId: string,
  adminToken?: string,
): Promise<AnnotationListResponse> {
  return getJson<AnnotationListResponse>(
    `/api/v2/annotations/target/${encodeURIComponent(targetType)}/${encodeURIComponent(targetId)}`,
    adminToken,
  )
}
