import type {
  AdminPlayer,
  AdminPlayerCreateResponse,
  AdminPlayerDeleteResponse,
  AdminPlayersListResponse,
  AdminPlayerTokenResponse,
  AnnotationCreateRequest,
  AnnotationCreateResponse,
  AnnotationListResponse,
  AnnotationTargetType,
  FamilyUsersResponse,
  CaddieDecisionRequest,
  CaddieContextParams,
  CaddieContextResponse,
  CaddieDecisionAuditLatestResponse,
  CaddieDecisionAuditRequest,
  CaddieDecisionAuditStoreResponse,
  CaddieDecisionResponse,
  ClubBagUpdateRequest,
  CoursePrepResponse,
  CourseSearchResponse,
  CourseTeesResponse,
  HistoryOverviewResponse,
  HistoryDrilldownResponse,
  HistoryRoundDetailResponse,
  HistoryRoundsResponse,
  HistoryStatsResponse,
  HistoryStatsSummaryResponse,
  MobileStatsResponse,
  RoundIngestRequestBody,
  RoundIngestResult,
  RoundsFilters,
  CourseGeometryCoverageResponse,
  EffectiveClubBagResponse,
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
  RoundHoleShotMapResponse,
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
import { currentSession, currentSessionToken, OWNER_PLAYER_ID } from './sessionStore'

// The bearer for every request: the Apple sign-in session token if signed in,
// else a per-player capability link token from the URL (legacy `/p/<token>`).
// Attached as `Authorization: Bearer`. Never log the token.
function playerTokenHeader(): Record<string, string> {
  const token = currentSessionToken() ?? readPlayerToken()
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

// The realistic-topo base bitmap for a course hole (design-system §九), rendered + cached
// server-side. Used as the <img> base layer under the hole canvases' vector overlays. Public
// (course geometry, no auth). The query separates renderer styles; the response ETag additionally
// binds Garmin's current geometry asset. 404s without CourseView geometry → client falls back.
export function topoImageUrl(globalId: number, hole: number, geometryRevision?: string | null): string {
  const revision = geometryRevision?.trim()
  const query = revision
    ? `v=topo-v8&r=${encodeURIComponent(revision)}`
    : 'v=topo-v8'
  return apiUrl(`/api/v2/courses/${globalId}/holes/${hole}/topo.png?${query}`)
}

// Fire-and-forget: ask the server to render + cache EVERY geometry-backed hole's topo bitmap for a
// course in the background so browsing holes hits a warm cache (each first render is ~6–10s). Called
// on course select; best-effort — a failure just means holes render lazily on first view as before.
export function prewarmCourseTopo(globalId: number): Promise<void> {
  // Public course knowledge (no auth needed, like /topo.png + /prep); we never read the body.
  return fetch(apiUrl(`/api/v2/courses/${globalId}/topo/prewarm`), { method: 'POST' }).then(() => undefined)
}

// Warm the browser's image cache for a hole's topo bitmap so stepping to it is instant. A no-op
// where the Image constructor is unavailable (SSR/tests without a DOM image shim).
export function prefetchTopoImage(url: string): void {
  if (typeof Image === 'undefined') return
  const img = new Image()
  img.src = url
}

function adminTokenHeader(adminToken?: string): Record<string, string> {
  const trimmed = adminToken?.trim()
  if (!trimmed) return {}
  // SECURITY: never let a signed-in MEMBER send the owner admin token. A member
  // authenticates with their own Apple session Bearer (attached separately); the
  // admin token (typed / baked / owner-homeserver fallback) may ride ONLY when there
  // is no member session — i.e. no session at all (the bare-URL owner, whose ONLY
  // credential is the admin token) or an OWNER session (playerId === OWNER_PLAYER_ID).
  // The server also rejects member-bearer + admin-header with 403 (#213); this is the
  // matching client belt so the header never leaves a member's browser in the first place.
  const session = currentSession()
  if (session && session.playerId !== OWNER_PLAYER_ID) return {}
  return { 'X-AI-Caddie-Admin-Token': trimmed }
}

export interface AppleSignInResponse {
  token: string
  expiresAt: string
  userId: string
  playerId: string
}

/** Exchange an Apple identity token for a session (owner Apple IDs → playerId "me"). */
export async function signInWithApple(identityToken: string, displayName?: string): Promise<AppleSignInResponse> {
  return postJson<AppleSignInResponse>('/api/v2/auth/apple', { identityToken, displayName })
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

async function patchJson<T>(path: string, body: unknown, adminToken?: string): Promise<T> {
  const url = apiUrl(path)
  const response = await fetch(url, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...adminTokenHeader(adminToken), ...playerTokenHeader() },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    throw new Error(`PATCH ${url} failed: ${response.status} ${response.statusText}`)
  }
  return response.json() as Promise<T>
}

async function putJson<T>(path: string, body: unknown, adminToken?: string): Promise<T> {
  const url = apiUrl(path)
  const response = await fetch(url, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...adminTokenHeader(adminToken), ...playerTokenHeader() },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    throw new Error(`PUT ${url} failed: ${response.status} ${response.statusText}`)
  }
  return response.json() as Promise<T>
}

async function deleteJson<T>(path: string, adminToken?: string): Promise<T> {
  const url = apiUrl(path)
  const headers = { ...adminTokenHeader(adminToken), ...playerTokenHeader() }
  const init: RequestInit = { method: 'DELETE' }
  if (Object.keys(headers).length) init.headers = headers
  const response = await fetch(url, init)
  if (!response.ok) {
    throw new Error(`DELETE ${url} failed: ${response.status} ${response.statusText}`)
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

// The course's selectable tee boxes (colour + total yards + default) for the pre-round tee picker.
// Public course knowledge (no player data) — the same list Garmin's new-round tee chooser shows.
export function fetchCourseTees(globalId: number, adminToken?: string): Promise<CourseTeesResponse> {
  return getJson<CourseTeesResponse>(`/api/v2/courses/${encodeURIComponent(String(globalId))}/tees`, adminToken)
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

// First paint of 球局 fetches just the first page (the real archive is 440+
// rounds ≈ 600KB at full scoreStrips); the timeline pulls the full set in the
// background only once the visitor reveals past it. ROUNDS_FULL_LIMIT sits at
// the backend's hard cap (server_v2/main.py Query le=2000).
export const ROUNDS_FIRST_PAGE = 120
export const ROUNDS_FULL_LIMIT = 2000

export function fetchHistoryRounds(
  adminToken?: string,
  filters?: RoundsFilters,
  limit: number = ROUNDS_FIRST_PAGE,
): Promise<HistoryRoundsResponse> {
  const params = new URLSearchParams()
  if (filters?.year) params.set('year', filters.year)
  if (filters?.course) params.set('course', filters.course)
  if (filters?.hasShots !== undefined) params.set('hasShots', String(filters.hasShots))
  if (filters?.hasReport !== undefined) params.set('hasReport', String(filters.hasReport))
  params.set('limit', String(limit))
  return getJson<HistoryRoundsResponse>(`/api/v2/history/rounds?${params.toString()}`, adminToken)
}

export function fetchHistoryRoundDetail(roundRef: string, adminToken?: string): Promise<HistoryRoundDetailResponse> {
  return getJson<HistoryRoundDetailResponse>(`/api/v2/history/rounds/${encodeURIComponent(roundRef)}`, adminToken)
}

// 复盘逐洞落点图: this round's actual shots projected onto the hole's 2D render.
// Rendered on demand per hole (one supersampled image), so the 复盘 workbench
// fetches it lazily as the player switches holes — never all 18 at once.
export function fetchRoundHoleShotMap(roundRef: string, hole: number, adminToken?: string): Promise<RoundHoleShotMapResponse> {
  return getJson<RoundHoleShotMapResponse>(
    `/api/v2/history/rounds/${encodeURIComponent(roundRef)}/holes/${encodeURIComponent(String(hole))}/shotmap`,
    adminToken,
  )
}

export function fetchHistoryStats(adminToken?: string, window: StatsWindow = 'all'): Promise<HistoryStatsResponse> {
  const qs = window !== 'all' ? `?window=${window}` : ''
  return getJson<HistoryStatsResponse>(`/api/v2/history/stats${qs}`, adminToken)
}

// Compact 统计 payload (window-aware) for the GolfLive 趋势 landing — ~246KB vs the ~11MB full
// /history/stats, so first paint is fast. Deep tabs (强弱/球场/报告) still use the full stats lazily.
export function fetchMobileStats(adminToken?: string, window: StatsWindow = 'all'): Promise<MobileStatsResponse> {
  const qs = window !== 'all' ? `?window=${window}` : ''
  return getJson<MobileStatsResponse>(`/api/v2/history/stats/mobile${qs}`, adminToken)
}

// 概览 landing only needs summary + top issue; this slim endpoint avoids pulling
// the ~20MB full /history/stats on first paint (full stats stays lazy per page).
export function fetchHistorySummary(adminToken?: string): Promise<HistoryStatsSummaryResponse> {
  return getJson<HistoryStatsSummaryResponse>('/api/v2/history/summary', adminToken)
}

// Land a manual ("phone") round captured by the web GPS recorder. A player
// bearer may only target its own player; the owner (admin token) may target any.
export function ingestPlayerRound(
  playerId: string,
  body: RoundIngestRequestBody,
  adminToken?: string,
): Promise<RoundIngestResult> {
  return postJson<RoundIngestResult>(`/api/v2/players/${encodeURIComponent(playerId)}/rounds`, body, adminToken)
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
  adminToken?: string,
): Promise<GeometryEvidenceResponse> {
  const query = new URLSearchParams()
  appendParam(query, 'source_ref', sourceRef)
  appendParam(query, 'start_x', routeParams.startX)
  appendParam(query, 'start_y', routeParams.startY)
  appendParam(query, 'target_x', routeParams.targetX)
  appendParam(query, 'target_y', routeParams.targetY)
  appendParam(query, 'landing_radius_m', routeParams.landingRadiusM)
  const suffix = query.toString()
  // P1-4: the backend admin-gates this route whenever source_ref is present (owner per-hole
  // drilldown), so the token must be threaded or the owner UI 401s.
  return getJson<GeometryEvidenceResponse>(
    `/api/v2/geometry/hole/${encodeURIComponent(String(globalId))}/${encodeURIComponent(String(localHole))}${suffix ? `?${suffix}` : ''}`,
    adminToken,
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
  adminToken?: string,
): Promise<HoleMapResponse> {
  const query = new URLSearchParams({ provider })
  appendParam(query, 'source_ref', sourceRef)
  // P1-4: admin-gated alongside the evidence route when source_ref is present — thread the token.
  return getJson<HoleMapResponse>(
    `/api/v2/geometry/hole/${encodeURIComponent(String(globalId))}/${encodeURIComponent(String(localHole))}/map?${query.toString()}`,
    adminToken,
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
  appendParam(query, 'background_geometry', params.backgroundGeometry)
  appendParam(query, 'include_event_cursor', params.includeEventCursor)
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

// Owner-side player management (admin token). These hit /api/v2/admin/players,
// which is NOT player-scoped: the admin gate is enforced server-side, so a
// per-player URL token can never reach these. create/rotate return the plaintext
// token + URL exactly once — surface it to the owner immediately, never log it.
export function fetchAdminPlayers(adminToken?: string): Promise<AdminPlayersListResponse> {
  return getJson<AdminPlayersListResponse>('/api/v2/admin/players', adminToken)
}

// Owner-facing family roster from the identity DB. Unlike /admin/players (the legacy
// file registry of link-issued players), this lists the Apple-registered family
// members (display name + role + join date), so it's the consumer-era roster source.
// Admin-gated server-side; never returns any token/link material.
export function fetchFamilyUsers(adminToken?: string): Promise<FamilyUsersResponse> {
  return getJson<FamilyUsersResponse>('/api/v2/admin/family/users', adminToken)
}

// Member-scoped manual club bag. The owner (admin token) acts-for-any player; a per-player bearer
// reads/writes only its own. GET returns the EFFECTIVE bag (manual wins, else Garmin, else empty);
// PUT sets the manual bag (an empty clubs list clears it). Distances are metres.
export function fetchPlayerClubBag(playerId: string, adminToken?: string): Promise<EffectiveClubBagResponse> {
  return getJson<EffectiveClubBagResponse>(`/api/v2/players/${encodeURIComponent(playerId)}/clubs/bag`, adminToken)
}

export function putPlayerClubBag(
  playerId: string,
  body: ClubBagUpdateRequest,
  adminToken?: string,
): Promise<EffectiveClubBagResponse> {
  return putJson<EffectiveClubBagResponse>(`/api/v2/players/${encodeURIComponent(playerId)}/clubs/bag`, body, adminToken)
}

export function createAdminPlayer(
  request: { name: string; avatar?: string | null },
  adminToken?: string,
): Promise<AdminPlayerCreateResponse> {
  return postJson<AdminPlayerCreateResponse>('/api/v2/admin/players', request, adminToken)
}

export function updateAdminPlayer(
  playerId: string,
  request: { name?: string; avatar?: string | null },
  adminToken?: string,
): Promise<AdminPlayer> {
  return patchJson<AdminPlayer>(`/api/v2/admin/players/${encodeURIComponent(playerId)}`, request, adminToken)
}

export function rotateAdminPlayerToken(playerId: string, adminToken?: string): Promise<AdminPlayerTokenResponse> {
  return postEmpty<AdminPlayerTokenResponse>(
    `/api/v2/admin/players/${encodeURIComponent(playerId)}/rotate-token`,
    adminToken,
  )
}

export function deleteAdminPlayer(playerId: string, adminToken?: string): Promise<AdminPlayerDeleteResponse> {
  return deleteJson<AdminPlayerDeleteResponse>(`/api/v2/admin/players/${encodeURIComponent(playerId)}`, adminToken)
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
