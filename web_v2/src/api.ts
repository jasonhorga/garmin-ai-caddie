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
  CoursePrepResponse,
  CourseSearchResponse,
  HistoryOverviewResponse,
  HistoryDrilldownResponse,
  HistoryRoundDetailResponse,
  HistoryRoundsResponse,
  HistoryStatsResponse,
  RoundsFilters,
  CourseGeometryCoverageResponse,
  GeometryEnsureResponse,
  GeometryEvidenceResponse,
  HoleGeometryRouteParams,
  GarminSessionImportRequest,
  GarminSessionImportResponse,
  HoleMapResponse,
  LiveRoundPackageResponse,
  MediaCreateRequest,
  MediaCreateResponse,
  MediaListResponse,
  MediaRedactResponse,
  MediaTargetType,
  MobileCourseOptionsResponse,
  MobileReconciliationApplyResponse,
  MobileReconciliationResponse,
  MobileCoursePackageParams,
  MobileRoundPackageParams,
  PrepTipsResponse,
  ProductSettingsResponse,
  ReadinessResponse,
  ReviewReportIndexResponse,
  ReviewReportResponse,
  StatsWindow,
  SyncRunResponse,
  SyncStatusResponse,
  WeatherSnapshotParams,
  WeatherSnapshotResponse,
  VisionFindingConfirmationRequest,
  VisionFindingConfirmationResponse,
  VisionAnalysisResponse,
  VisionFindingsListResponse,
} from './types'
import { readPlayerToken } from './playerContext'

// Per-player capability token read from the URL (see playerContext). When
// present it scopes every request to that player via `Authorization: Bearer`.
// It coexists with the owner's admin-token header; the backend prefers the
// player token. Never log the token.
function playerTokenHeader(): Record<string, string> {
  const token = readPlayerToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function getJson<T>(path: string, adminToken?: string): Promise<T> {
  const url = apiUrl(path)
  const headers = { ...adminTokenHeader(adminToken), ...playerTokenHeader() }
  const init = Object.keys(headers).length ? { headers } : undefined
  const response = init ? await fetch(url, init) : await fetch(url)
  if (!response.ok) {
    throw new Error(`GET ${url} failed: ${response.status} ${response.statusText}`)
  }
  return response.json() as Promise<T>
}

function apiUrl(path: string): string {
  const baseUrl = String(import.meta.env.VITE_AI_CADDIE_API_BASE_URL ?? '').trim().replace(/\/+$/, '')
  if (!baseUrl) return path
  return `${baseUrl}${path.startsWith('/') ? path : `/${path}`}`
}

function adminTokenHeader(adminToken?: string): Record<string, string> {
  const trimmed = adminToken?.trim()
  return trimmed ? { 'X-AI-Caddie-Admin-Token': trimmed } : {}
}

async function postJson<T>(path: string, body: unknown, adminToken?: string): Promise<T> {
  const url = apiUrl(path)
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...adminTokenHeader(adminToken), ...playerTokenHeader() },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    throw new Error(`POST ${url} failed: ${response.status} ${response.statusText}`)
  }
  return response.json() as Promise<T>
}

async function postEmpty<T>(path: string, adminToken?: string): Promise<T> {
  const url = apiUrl(path)
  const headers = { ...adminTokenHeader(adminToken), ...playerTokenHeader() }
  const init: RequestInit = { method: 'POST' }
  if (Object.keys(headers).length) init.headers = headers
  const response = await fetch(url, init)
  if (!response.ok) {
    throw new Error(`POST ${url} failed: ${response.status} ${response.statusText}`)
  }
  return response.json() as Promise<T>
}

function appendParam(query: URLSearchParams, key: string, value: string | number | boolean | undefined): void {
  if (value !== undefined) query.append(key, String(value))
}

export function fetchHistoryOverview(adminToken?: string): Promise<HistoryOverviewResponse> {
  return getJson<HistoryOverviewResponse>('/api/v2/history/overview', adminToken)
}

export function fetchCoursePrep(
  globalId: number,
  opts?: { holes?: number[]; render?: boolean; includeShots?: boolean },
  adminToken?: string,
): Promise<CoursePrepResponse> {
  const params = new URLSearchParams()
  for (const hole of opts?.holes ?? []) params.append('holes', String(hole))
  if (opts?.render === false) params.set('render', 'false')
  if (opts?.includeShots === true) params.set('include_shots', 'true')
  const query = params.toString()
  return getJson<CoursePrepResponse>(`/api/v2/courses/${globalId}/prep${query ? `?${query}` : ''}`, adminToken)
}

export function fetchPrepTips(globalId: number, adminToken?: string): Promise<PrepTipsResponse> {
  return getJson<PrepTipsResponse>(`/api/v2/courses/${globalId}/prep-tips`, adminToken)
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
  appendParam(query, 'captured_at', params.capturedAt)
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

export function redactMedia(mediaId: string, adminToken?: string): Promise<MediaRedactResponse> {
  return postEmpty<MediaRedactResponse>(`/api/v2/media/${encodeURIComponent(mediaId)}/redact`, adminToken)
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

export function confirmVisionFinding(
  findingId: string,
  request: VisionFindingConfirmationRequest,
  adminToken?: string,
): Promise<VisionFindingConfirmationResponse> {
  return postJson<VisionFindingConfirmationResponse>(
    `/api/v2/media/findings/${encodeURIComponent(findingId)}/confirmation`,
    request,
    adminToken,
  )
}

export function fetchHistoryRounds(adminToken?: string, filters?: RoundsFilters): Promise<HistoryRoundsResponse> {
  const params = new URLSearchParams()
  if (filters?.year) params.set('year', filters.year)
  if (filters?.course) params.set('course', filters.course)
  if (filters?.hasShots !== undefined) params.set('hasShots', String(filters.hasShots))
  if (filters?.hasReport !== undefined) params.set('hasReport', String(filters.hasReport))
  // The backend defaults to limit=120 (server_v2/history_rounds.py), which
  // silently truncates the real archive (435+ rounds) — always ask for all.
  params.set('limit', '1000')
  return getJson<HistoryRoundsResponse>(`/api/v2/history/rounds?${params.toString()}`, adminToken)
}

export function fetchHistoryRoundDetail(roundRef: string, adminToken?: string): Promise<HistoryRoundDetailResponse> {
  return getJson<HistoryRoundDetailResponse>(`/api/v2/history/rounds/${encodeURIComponent(roundRef)}`, adminToken)
}

export function fetchHistoryStats(adminToken?: string, window: StatsWindow = 'all'): Promise<HistoryStatsResponse> {
  const qs = window !== 'all' ? `?window=${window}` : ''
  return getJson<HistoryStatsResponse>(`/api/v2/history/stats${qs}`, adminToken)
}

export function fetchCourseSearch(name: string, adminToken?: string): Promise<CourseSearchResponse> {
  return getJson<CourseSearchResponse>(`/api/v2/courses/search?name=${encodeURIComponent(name)}`, adminToken)
}

export function fetchHistoryDrilldown(sourceRef: string, adminToken?: string): Promise<HistoryDrilldownResponse> {
  return getJson<HistoryDrilldownResponse>(`/api/v2/history/drilldown/${encodeURIComponent(sourceRef)}`, adminToken)
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

export function ensureHoleGeometry(
  globalId: number,
  localHole: number,
  params: { profileId?: string; force?: boolean } = {},
  adminToken?: string,
): Promise<GeometryEnsureResponse> {
  const query = new URLSearchParams()
  appendParam(query, 'profile_id', params.profileId)
  appendParam(query, 'force', params.force)
  const suffix = query.toString()
  return postEmpty<GeometryEnsureResponse>(
    `/api/v2/geometry/hole/${encodeURIComponent(String(globalId))}/${encodeURIComponent(String(localHole))}/ensure${suffix ? `?${suffix}` : ''}`,
    adminToken,
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

export function fetchCourseReport(courseKey: string, adminToken?: string): Promise<ReviewReportResponse> {
  return getJson<ReviewReportResponse>(`/api/v2/reports/course/${encodeURIComponent(courseKey)}`, adminToken)
}

export function generateCourseReport(courseKey: string, adminToken?: string): Promise<ReviewReportResponse> {
  return postEmpty<ReviewReportResponse>(`/api/v2/reports/course/${encodeURIComponent(courseKey)}/generate`, adminToken)
}

export function fetchHoleReport(courseKey: string, hole: number, adminToken?: string): Promise<ReviewReportResponse> {
  return getJson<ReviewReportResponse>(
    `/api/v2/reports/hole/${encodeURIComponent(courseKey)}/${encodeURIComponent(String(hole))}`,
    adminToken,
  )
}

export function generateHoleReport(courseKey: string, hole: number, adminToken?: string): Promise<ReviewReportResponse> {
  return postEmpty<ReviewReportResponse>(
    `/api/v2/reports/hole/${encodeURIComponent(courseKey)}/${encodeURIComponent(String(hole))}/generate`,
    adminToken,
  )
}

export function fetchClubReport(clubName: string, adminToken?: string): Promise<ReviewReportResponse> {
  return getJson<ReviewReportResponse>(`/api/v2/reports/club/${encodeURIComponent(clubName)}`, adminToken)
}

export function generateClubReport(clubName: string, adminToken?: string): Promise<ReviewReportResponse> {
  return postEmpty<ReviewReportResponse>(`/api/v2/reports/club/${encodeURIComponent(clubName)}/generate`, adminToken)
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

export function fetchProductSettings(): Promise<ProductSettingsResponse> {
  return getJson<ProductSettingsResponse>('/api/v2/settings/product')
}

export function fetchMobileCourseOptions(adminToken?: string): Promise<MobileCourseOptionsResponse> {
  return getJson<MobileCourseOptionsResponse>('/api/v2/mobile/courses/options', adminToken)
}

export function fetchMobileReconciliation(roundId: string, adminToken?: string): Promise<MobileReconciliationResponse> {
  return getJson<MobileReconciliationResponse>(
    `/api/v2/mobile/rounds/${encodeURIComponent(roundId)}/reconciliation`,
    adminToken,
  )
}

export function fetchMobileRoundPackage(
  roundId: string,
  params: MobileRoundPackageParams = {},
  adminToken?: string,
): Promise<LiveRoundPackageResponse> {
  const query = new URLSearchParams()
  appendParam(query, 'captured_at', params.capturedAt)
  appendParam(query, 'ensure_geometry', params.ensureGeometry)
  const suffix = query.toString()
  return getJson<LiveRoundPackageResponse>(
    `/api/v2/mobile/rounds/${encodeURIComponent(roundId)}/package${suffix ? `?${suffix}` : ''}`,
    adminToken,
  )
}

export function fetchMobileCoursePackage(
  globalId: number,
  params: MobileCoursePackageParams = {},
  adminToken?: string,
): Promise<LiveRoundPackageResponse> {
  const query = new URLSearchParams()
  appendParam(query, 'round_id', params.roundId)
  appendParam(query, 'tee_box', params.teeBox)
  appendParam(query, 'captured_at', params.capturedAt)
  appendParam(query, 'ensure_geometry', params.ensureGeometry)
  const suffix = query.toString()
  return getJson<LiveRoundPackageResponse>(
    `/api/v2/mobile/courses/${encodeURIComponent(String(globalId))}/package${suffix ? `?${suffix}` : ''}`,
    adminToken,
  )
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
  const path = `/api/v2/sync/garmin?${params.toString()}`
  const url = apiUrl(path)
  const headers = { ...adminTokenHeader(options.adminToken), ...playerTokenHeader() }
  const init: RequestInit = { method: 'POST' }
  if (Object.keys(headers).length) init.headers = headers
  return fetch(url, init).then((response) => {
    if (!response.ok) {
      throw new Error(`POST ${url} failed: ${response.status} ${response.statusText}`)
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
