export type DataQualityState = 'good' | 'partial' | 'missing'
export type ScoreClass = 'eagle' | 'birdie' | 'par' | 'bogey' | 'double' | 'missing'
export type CaddieShotType = 'tee' | 'approach' | 'recovery'
export type AnnotationTargetType = 'round' | 'hole' | 'shot' | 'decision'
export type MediaTargetType = 'round' | 'hole' | 'shot'
export type MediaKind = 'photo' | 'video'
export type MediaPrivacyState = 'private_local' | 'synced' | 'redacted'
export type GeometryCoverageState = 'ready' | 'partial' | 'missing'
export type VisionConfirmationState = 'unconfirmed' | 'confirmed' | 'player_confirmed' | 'manual_confirmed' | 'rejected'
export type VisionFindingType =
  | 'poor_lie'
  | 'blocked_view'
  | 'visible_water'
  | 'visible_bunker'
  | 'slope_clue'
  | 'uncertainty'
export type AnnotationKind =
  | 'round_note'
  | 'hole_note'
  | 'shot_note'
  | 'issue_tag'
  | 'issue_tag_removed'
  | 'club_correction'
  | 'lie_correction'
  | 'penalty_correction'
  | 'putt_correction'
  | 'score_correction'
  | 'weather_context_note'
  | 'strategy_note'
  | 'caddie_feedback'

export interface DataQualityBadge {
  label: string
  state: DataQualityState
  value: string
  reason: string
}

export interface ScoreStripCell {
  hole: number
  par: number | null
  score: number | null
  toPar: number | null
  className: ScoreClass
}

export interface RoundCard {
  id: string
  date: string | null
  courseName: string
  courseKey: string | null
  holesCompleted: number | null
  score: number | null
  par: number | null
  toPar: number | null
  scoreStrip: ScoreStripCell[]
  badges: DataQualityBadge[]
  primaryIssue: string | null
}

export interface HistoryMetricSet {
  totalRounds: number
  eighteenHoleRounds: number
  nineHoleRounds: number
  courseCount: number
  shotCount: number
  average18: number | null
  recent10Average: number | null
  bestScore: number | null
}

export interface DistributionFamily {
  label: string
  count: number
  pct: number
  className: Exclude<ScoreClass, 'missing'>
  roundRefs?: string[]
}

export interface DistributionBucket {
  label: string
  start: number
  count: number
  roundRefs?: string[]
}

export interface ScoreDistribution {
  total: number
  average: number | null
  best: number | null
  worst: number | null
  families: DistributionFamily[]
  histogram: DistributionBucket[]
}

export interface EmptyState {
  kind: string
  title: string
  detail: string
}

export interface HistoryOverviewResponse {
  schema: 'ai-caddie-history-overview-v2'
  metrics: HistoryMetricSet
  recentRounds: RoundCard[]
  distribution: ScoreDistribution
  dataQuality: DataQualityBadge[]
  emptyState: EmptyState | null
}

export interface CaddieDecisionRequest {
  shotType: CaddieShotType
  context: Record<string, unknown>
  includeExplanation?: boolean
}

export interface CaddieDecisionResponse {
  schema: 'ai-caddie-decision-v2'
  decisionId: string
  sourceRef: string | null
  evidenceRefs: string[]
  shotType: CaddieShotType
  phase: string
  context: Record<string, unknown>
  options: Array<Record<string, unknown>>
  selected: Record<string, unknown> | null
  selectedOptionId: string | null
  selectedOption: Record<string, unknown> | null
  sequences?: Array<Record<string, unknown>>
  selectedSequence?: Record<string, unknown> | null
  avoidZones: Array<Record<string, unknown>>
  forbiddenZones: Array<Record<string, unknown>>
  acceptableMiss: Record<string, unknown>
  evidence: Array<Record<string, unknown>>
  confidence: Record<string, unknown>
  missingData: Array<Record<string, unknown>>
  auditCriteria: Array<Record<string, unknown>>
  explanation?: Record<string, unknown> | null
}

export interface CaddieContextParams {
  sourceRef: string
  shotType: CaddieShotType
  distanceToPinM?: number
  lie?: string
  currentLatitude?: number
  currentLongitude?: number
  targetLatitude?: number
  targetLongitude?: number
  strategyMode?: string
  startX?: number
  startY?: number
  targetX?: number
  targetY?: number
  landingRadiusM?: number
  capturedAt?: string
}

export interface CaddieContextResponse {
  schema: 'ai-caddie-context-v1'
  sourceRef: string
  shotType: CaddieShotType
  context: Record<string, unknown>
  evidence: Array<Record<string, unknown>>
  missingData: Array<Record<string, unknown>>
}

export interface CaddieDecisionAuditRequest {
  decision: CaddieDecisionResponse | Record<string, unknown>
  actualShot: Record<string, unknown> | null
  actualShots?: Array<Record<string, unknown>>
  actualScoreToPar?: number | null
  penalty?: boolean | null
}

export interface CaddieDecisionAuditRecord {
  id: string
  storedAt: string
  decisionId: string
  sourceRef?: string | null
  selectedOptionId?: string | null
  plannedOptionId?: string | null
  actualOptionId?: string | null
  actualShotRefs?: string[]
  evidenceRefs?: string[]
  classification?: string | null
  audit: Record<string, unknown>
}

export interface CaddieDecisionAuditStoreResponse {
  schema: 'ai-caddie-decision-audit-store-v1'
  record: CaddieDecisionAuditRecord
}

export interface CaddieDecisionAuditLatestResponse {
  schema: 'ai-caddie-decision-audit-latest-v1'
  decisionId: string
  record: CaddieDecisionAuditRecord | null
}

export type WeatherState = 'ready' | 'missing'
export type WeatherSource = 'manual' | 'open_meteo' | 'missing'

export interface WeatherSnapshotResponse {
  schema: 'ai-caddie-weather-snapshot-v1'
  state: WeatherState
  source: WeatherSource
  roundId: string | null
  hole: number | null
  capturedAt: string | null
  location: { latitude: number; longitude: number } | null
  windSpeedMps: number | null
  windDirectionDeg: number | null
  temperatureC: number | null
  precipitationMm: number | null
  confidence: ReportConfidence
  missingData: Array<Record<string, unknown>>
}

export interface WeatherSnapshotParams {
  source?: 'manual' | 'open_meteo'
  persist?: boolean
  roundId?: string
  hole?: number
  capturedAt?: string
  latitude?: number
  longitude?: number
  windSpeedMps?: number
  windDirectionDeg?: number
  temperatureC?: number
  precipitationMm?: number
}

export interface MediaRecord {
  id: string
  createdAt: string
  targetType: MediaTargetType
  targetId: string
  mediaKind: MediaKind
  localPath: string
  capturedAt: string
  privacyState: MediaPrivacyState
  source: 'manual'
}

export interface MediaCreateRequest {
  targetType: MediaTargetType
  targetId: string
  mediaKind: MediaKind
  localPath?: string
  fileName?: string
  contentBase64?: string
  capturedAt: string
  privacyState?: MediaPrivacyState
}

export interface MediaCreateResponse {
  schema: 'ai-caddie-media-create-v1'
  media: MediaRecord
}

export interface MediaRedactResponse {
  schema: 'ai-caddie-media-redact-v1'
  media: MediaRecord
  deletedContent: boolean
}

export interface MediaListResponse {
  schema: 'ai-caddie-media-list-v1'
  total: number
  media: MediaRecord[]
  target: { targetType: MediaTargetType; targetId: string } | null
}

export interface VisionFinding {
  findingType: VisionFindingType
  evidenceText: string
  confidence: ReportConfidence
  confirmationState?: VisionConfirmationState
  missingInfo: string[]
  provider: string
  model: string
  source: 'vision_model'
}

export interface VisionAnalysisResponse {
  schema: 'ai-caddie-vision-context-v1'
  mediaId: string | null
  targetType: string | null
  targetId: string | null
  mediaKind: string | null
  provider: string
  model: string
  findings: VisionFinding[]
}

export interface VisionFindingRecord extends VisionFinding {
  id: string
  createdAt: string
  confirmedAt?: string | null
  confirmedBy?: string | null
  targetType: MediaTargetType
  targetId: string
  mediaId: string
  mediaKind: MediaKind | null
}

export interface VisionFindingConfirmationRequest {
  confirmationState: Extract<VisionConfirmationState, 'unconfirmed' | 'manual_confirmed' | 'rejected'>
  confirmedBy?: string | null
}

export interface VisionFindingConfirmationResponse {
  schema: 'ai-caddie-vision-finding-confirmation-v1'
  finding: VisionFindingRecord
}

export interface VisionFindingsListResponse {
  schema: 'ai-caddie-vision-findings-list-v1'
  total: number
  findings: VisionFindingRecord[]
  target: { targetType: MediaTargetType; targetId: string }
}

export interface GeometryEvidenceResponse {
  schema: 'ai-caddie-geometry-evidence-v1'
  globalId: number
  localHole: number
  coverage: GeometryCoverageState
  hasHazards: boolean
  hasMeshes: boolean
  sourceRef?: string | null
  shotRoutes?: Array<Record<string, unknown>>
  surfaceClassifications?: Array<Record<string, unknown>>
  routeEvidence?: RouteGeometryEvidence | null
  evidence: Array<Record<string, unknown>>
  missingData: Array<Record<string, unknown>>
}

export interface GeometryEnsureResponse {
  schema: 'ai-caddie-geometry-ensure-v1'
  status: string
  ok: boolean
  globalId: number
  localHole: number
  releaseSource?: string | null
  releaseId?: string | null
  courseName?: string | null
  hazards?: string | null
  meshes?: string | null
  steps: Record<string, unknown>
  error?: string | null
}

export interface RouteGeometryEvidence {
  routeLength_m?: number
  routeStartLocal?: number[]
  routeTargetLocal?: number[]
  landingWindowLocal?: Record<string, unknown>
  lineIntersections?: Array<Record<string, unknown>>
  hazardClearances?: Array<Record<string, unknown>>
  landingWindowRisks?: Array<Record<string, unknown>>
  avoidZones?: Array<Record<string, unknown>>
  missingData?: Array<Record<string, unknown>>
  sourceRefs?: string[]
}

export interface HoleGeometryRouteParams {
  startX?: number
  startY?: number
  targetX?: number
  targetY?: number
  landingRadiusM?: number
}

export interface CourseGeometryCoverageResponse {
  schema: 'ai-caddie-course-geometry-coverage-v1'
  globalId: number
  coverage: GeometryCoverageState
  readyHoles: number
  partialHoles: number
  totalHoles: number
  holes: Array<Record<string, unknown>>
}

export interface GeoJsonFeature {
  type: 'Feature'
  geometry: {
    type: string
    coordinates: unknown
  }
  properties: Record<string, unknown>
}

export interface GeoJsonFeatureCollection {
  type: 'FeatureCollection'
  features: GeoJsonFeature[]
}

export interface HoleMapResponse {
  schema: 'ai-caddie-hole-map-v1'
  globalId: number
  localHole: number
  provider: Record<string, unknown>
  coverage: GeometryCoverageState
  layers: string[]
  featureCollection: GeoJsonFeatureCollection
  missingData: Array<Record<string, unknown>>
}

export interface MonthRoundGroup {
  key: string
  label: string
  count: number
  average18: number | null
  bestScore: number | null
  rounds: RoundCard[]
}

export interface CourseFilterOption {
  key: string
  label: string
}

export interface RoundsFilters {
  year?: string
  course?: string
  hasShots?: boolean
  hasReport?: boolean
}

export interface HistoryRoundsResponse {
  schema: 'ai-caddie-history-rounds-v2'
  total: number
  groups: MonthRoundGroup[]
  emptyState: EmptyState | null
  availableYears?: string[]
  availableCourses?: CourseFilterOption[]
  appliedFilters?: RoundsFilters
}

export interface HistoryRoundDetailScorecardCell {
  hole: number
  par: number | null
  score: number | null
  toPar: number | null
  className: ScoreClass
  putts: number | null
  gir: boolean | null
  fairway: string | null
  globalId?: number | null
  localHole?: number | null
  holeRef: string
  shotRefs: string[]
  sourceRefs: string[]
  status: string
}

export interface HistoryRoundDetailResponse {
  schema: 'ai-caddie-history-round-detail-v1'
  roundRef: string
  requestedRef: string
  found: boolean
  title: string
  round: Record<string, unknown> | null
  scorecard: HistoryRoundDetailScorecardCell[]
  phaseSummary: Array<Record<string, unknown>>
  holeDetails: Array<Record<string, unknown>>
  relatedRefs: {
    roundRefs: string[]
    holeRefs: string[]
    shotRefs: string[]
    sourceRefs?: string[]
  }
  sourceFields: Record<string, unknown>
  missingData: Array<Record<string, unknown>>
  annotations?: AnnotationRecord[]
  corrections?: AnnotationRecord[]
}

export interface HistoryStatsResponse {
  schema: 'ai-caddie-history-stats-v1'
  dataMode: ResolvedDataMode
  summary: Record<string, unknown>
  time: Record<string, unknown>
  scoring: Record<string, unknown>
  courseDistribution: Array<Record<string, unknown>>
  records: Record<string, unknown>
  courses: Array<Record<string, unknown>>
  holes: Array<Record<string, unknown>>
  clubs: Array<Record<string, unknown>>
  issues: Array<Record<string, unknown>>
  diagnosis?: Record<string, unknown>
  playerProfile?: Record<string, unknown>
  dataQuality: Array<Record<string, unknown>>
  drillDown: Record<string, unknown>
}

export type HistoryRefType = 'round' | 'hole' | 'shot' | 'unknown'

export interface HistoryDrilldownResponse {
  schema: 'ai-caddie-history-drilldown-v1'
  ref: string
  refType: HistoryRefType
  found: boolean
  title: string
  round: Record<string, unknown> | null
  hole: Record<string, unknown> | null
  shot: Record<string, unknown> | null
  relatedRefs: {
    roundRefs: string[]
    holeRefs: string[]
    shotRefs: string[]
  }
  sourceFields: Record<string, unknown>
  missingData: Array<Record<string, unknown>>
  annotations?: AnnotationRecord[]
  corrections?: AnnotationRecord[]
  reports?: Array<Record<string, unknown>>
  weatherSnapshots?: Array<Record<string, unknown>>
  decisionAudits?: Array<Record<string, unknown>>
  geometryEvidence?: Array<Record<string, unknown>>
}

export type ReportKind = 'round' | 'trend' | 'course' | 'hole' | 'club'
export type ReportConfidence = 'low' | 'medium' | 'high'

export interface ReviewReportResponse {
  schema: 'ai-caddie-review-report-v1'
  kind: ReportKind
  subjectId: string
  sourceRefs: string[]
  provider: string
  model: string
  factsUsed: Array<Record<string, unknown>>
  missingData: Array<Record<string, unknown>>
  inferencesMade: Array<Record<string, unknown>>
  unsupportedClaims?: Array<Record<string, unknown>>
  factBinding?: Record<string, unknown>
  narrative: string
  confidence: ReportConfidence
}

export interface ReviewReportIndexItem {
  id: string
  storedAt: string
  kind: ReportKind
  subjectId: string
  confidence: ReportConfidence
  provider: string
  model: string
  sourceRefs: string[]
}

export interface ReviewReportIndexResponse {
  schema: 'ai-caddie-review-report-index-v1'
  total: number
  reports: ReviewReportIndexItem[]
}

export type ConnectorState = 'ready' | 'no_data' | 'reauth_required' | 'error' | 'not_available'
export type ConnectorNextAction = 'connect_garmin' | 'review_history' | 'reauthenticate_garmin' | 'inspect_sync_error'
export type ResolvedDataMode = 'local' | 'fixture'

export type ConnectorCapabilityState = 'unproven' | 'not_available' | 'possible' | 'proven' | 'needs_golf_fit_validation' | 'not_replacement'

export interface ConnectorCapability {
  key: string
  label: string
  state: ConnectorCapabilityState
  evidence: string
  nextStep: string
  canReplaceCnConnector: boolean
  migrationValue: boolean
}

export interface ConnectorProbeStatus {
  schema: 'ai-caddie-garmin-oauth-probe-v2'
  state: 'not_configured' | 'ready_for_manual_consent'
  liveProbeAllowed: boolean
  configured: Record<string, boolean>
  missing?: string[]
  consentRequest: {
    method: string
    endpoint?: string
    endpointConfigured: boolean
    parameterKeys: string[]
    redactedPreview: string | null
  }
  tokenExchange?: {
    method: string
    endpoint?: string
    ready: boolean
    missing: string[]
    parameterKeys: string[]
  }
  resourceProbe?: {
    userIdEndpoint?: string
    permissionsEndpoint?: string
    checks: string[]
  }
  manualSteps: string[]
}

export interface ConnectorStatus {
  name: 'garmin_cn_web_session' | 'garmin_oauth_feasibility'
  state: ConnectorState
  detail: string
  canSync: boolean
  reauthRequired: boolean
  nextAction?: ConnectorNextAction | null
  track?: string | null
  feasibilityQuestions?: string[]
  capabilities?: ConnectorCapability[]
  probe?: ConnectorProbeStatus
}

export interface SyncLastRunStatus {
  state: ConnectorState
  detail: string
  snapshotId: string | null
  errorCode: string | null
  updatedAt: string | null
}

export interface SnapshotStatus {
  dataMode: ResolvedDataMode
  scorecardCount: number
  shotFileCount: number
  summaryPresent: boolean
  lastSuccessfulSyncAt: string | null
}

export interface SyncStatusResponse {
  schema: 'ai-caddie-sync-status-v2'
  connector: ConnectorStatus
  connectors?: ConnectorStatus[]
  snapshot: SnapshotStatus
  lastRun: SyncLastRunStatus | null
}

export interface SyncSnapshotPayload {
  snapshotId: string
  scorecardCount: number
  shotFileCount: number
  summaryPresent: boolean
  files: string[]
  geometryDependencyCount?: number
  geometryReadyCount?: number
  geometryMissingCount?: number
  geometryDependencies?: Array<Record<string, unknown>>
}

export interface SyncRunResponse {
  schema: 'ai-caddie-sync-run-v2'
  connector: 'garmin_cn_web_session'
  state: ConnectorState
  detail: string
  reauthRequired: boolean
  errorCode: string | null
  snapshot: SyncSnapshotPayload | null
  safeMeta?: Record<string, unknown>
}

export interface GarminSessionImportRequest {
  webSessionHeader: string
  antiForgeryValue: string
  source?: 'manual_paste' | 'web_secure_paste' | 'ios_secure_input' | 'ios_keychain_replay' | 'ios_web_login'
}

export interface GarminSessionImportResponse {
  schema: 'ai-caddie-garmin-session-import-v1'
  connector: 'garmin_cn_web_session'
  state: 'stored'
  detail: string
  sessionFieldCount: number
  antiForgeryPresent: boolean
  source: 'manual_paste' | 'web_secure_paste' | 'ios_secure_input' | 'ios_keychain_replay' | 'ios_web_login'
  acceptedSources?: Array<'manual_paste' | 'web_secure_paste' | 'ios_secure_input' | 'ios_keychain_replay' | 'ios_web_login'>
}

export interface MobileReconciliationSummary {
  eventCount: number
  matchedCount: number
  localOnlyCount: number
  garminOnlyCount: number
  conflictCount: number
  candidateDecisionAuditCount: number
  annotationSuggestionCount: number
}

export interface MobileReconciliationSuggestion {
  id: string
  targetType: AnnotationTargetType
  targetId: string
  kind: AnnotationKind
  payload: Record<string, unknown>
  reason: string
  confidence: ReportConfidence
}

export interface MobileReconciliationResponse {
  schema: 'ai-caddie-mobile-reconciliation-v1'
  roundId: string
  summary: MobileReconciliationSummary
  matched: Array<Record<string, unknown>>
  localOnly: Array<Record<string, unknown>>
  garminOnly: Array<Record<string, unknown>>
  conflicts: Array<Record<string, unknown>>
  candidateDecisionAudits: Array<Record<string, unknown>>
  annotationSuggestions: MobileReconciliationSuggestion[]
}

export interface MobileReconciliationApplyResponse {
  schema: 'ai-caddie-mobile-reconciliation-apply-v1'
  roundId: string
  appliedCount: number
  decisionAuditCount: number
  skippedCount: number
  missingSuggestionIds: string[]
  skippedSuggestionIds: string[]
  annotations: AnnotationRecord[]
  decisionAudits: Array<Record<string, unknown>>
}

export type LiveRoundPreparationMode = 'round' | 'course'
export type LiveRoundSourceCoverageState = 'ready' | 'degraded'
export type OfflinePackageState = 'ready' | 'degraded' | 'expired'

export interface LiveRoundSourceCoverage {
  state: LiveRoundSourceCoverageState
  dataMode: ResolvedDataMode
  requestedRoundId: string
  selectedRoundId: string | null
  roundFound: boolean
  availableRoundCount: number
  holeCount: number
  clubProfileCount: number
  preparationMode?: LiveRoundPreparationMode
  requestedCourseGlobalId?: number | null
  courseFound?: boolean
  geometryEnsure?: GeometryEnsureSummary
}

export interface GeometryEnsureSummary {
  schema: 'ai-caddie-geometry-ensure-summary-v1'
  requested: boolean
  state: 'not_requested' | 'skipped' | 'ready' | 'partial' | 'failed'
  attempted: number
  ready: number
  failed: number
  sourceRefs: string[]
  results: Array<{
    hole: number
    globalId: number | null
    localHole: number
    status: string
    ok: boolean
    sourceRef: string
    releaseSource?: string
    reason?: string
  }>
}

export interface LiveRoundWeatherSnapshot {
  schema: 'ai-caddie-weather-snapshot-v1'
  state: WeatherState
  source: WeatherSource
  confidence: ReportConfidence
  missingData: Array<Record<string, unknown>>
  coverage?: { ready: number; total: number; pct: number }
  holeCoverage?: Array<Record<string, unknown>>
  roundId?: string | null
  hole?: number | null
  capturedAt?: string | null
  location?: { latitude: number; longitude: number } | null
  windSpeedMps?: number | null
  windDirectionDeg?: number | null
  temperatureC?: number | null
  precipitationMm?: number | null
}

export interface OfflinePackageStatus {
  state: OfflinePackageState
  preparedAt: string
  expiresAt: string
  cachePolicy: {
    staleAfterHours: number
    expiresAfterHours: number
  }
}

export interface PackageReadinessCheck {
  label: string
  state: 'ready' | 'degraded' | 'missing'
  ready: number
  total: number
  reason: string
  sourceRefs: string[]
}

export interface LiveRoundPackageResponse {
  schema: 'ai-caddie-live-round-package-v1'
  roundId: string
  dataMode: ResolvedDataMode
  sourceCoverage: LiveRoundSourceCoverage
  missingData: Array<Record<string, unknown>>
  playerProfile: Record<string, unknown>
  course: {
    globalId: number
    name: string
    teeBox: string
  }
  holes: Array<Record<string, unknown>>
  geometryCoverage: {
    state: GeometryCoverageState
    readyHoles: number
    totalHoles: number
  }
  readinessChecks: PackageReadinessCheck[]
  caddieContextSeeds: Array<Record<string, unknown>>
  weatherSnapshot: LiveRoundWeatherSnapshot
  clubProfiles: Array<Record<string, unknown>>
  caddieDecisionEndpoint: string
  offlinePackageStatus: OfflinePackageStatus
  eventCursor: Record<string, unknown>
  recentHistory: Record<string, unknown>
  cachedCaddieRules: Record<string, unknown>
  generatedAt: string
}

export interface MobileCourseOption {
  globalId: number
  courseKey?: string | null
  name: string
  roundCount: number
  latestRoundId?: string | null
  latestRoundDate?: string | null
  templateRoundId?: string | null
  suggestedLiveRoundId?: string | null
  holes: number
  teeBox?: string | null
  geometryCoverage: string
  sourceRefs: string[]
}

export interface MobileCourseOptionsResponse {
  schema: 'ai-caddie-mobile-course-options-v1'
  dataMode: ResolvedDataMode
  total: number
  courses: MobileCourseOption[]
  emptyState: EmptyState | null
  generatedAt: string
}

export interface MobileRoundPackageParams {
  capturedAt?: string
  ensureGeometry?: boolean
}

export interface MobileCoursePackageParams {
  roundId?: string
  teeBox?: string
  capturedAt?: string
  ensureGeometry?: boolean
}

export type ReadinessState = 'ready' | 'degraded' | 'error'

export interface ReadinessCheck {
  label: string
  state: ReadinessState
  detail: string
  evidence: Record<string, unknown>
}

export interface ReadinessResponse {
  schema: 'ai-caddie-readiness-v1'
  status: ReadinessState
  checks: ReadinessCheck[]
}

export interface ProductSettingsResponse {
  schema: 'ai-caddie-product-settings-v1'
  dataSources: Array<Record<string, unknown>>
  aiProviders: {
    activeProvider: string
    factBindingRequired: boolean
    providers: Array<Record<string, unknown>>
  }
  liveApps: Record<string, unknown>
  privacy: Record<string, unknown>
  endpoints: Record<string, string>
}

export interface AnnotationRecord {
  id: string
  createdAt: string
  targetType: AnnotationTargetType
  targetId: string
  kind: AnnotationKind
  payload: Record<string, unknown>
  source: 'manual'
}

export interface AnnotationCreateRequest {
  targetType: AnnotationTargetType
  targetId: string
  kind: AnnotationKind
  payload: Record<string, unknown>
}

export interface AnnotationCreateResponse {
  schema: 'ai-caddie-annotation-create-v1'
  annotation: AnnotationRecord
}

export interface AnnotationListResponse {
  schema: 'ai-caddie-annotations-v1'
  total: number
  annotations: AnnotationRecord[]
  target: { targetType: AnnotationTargetType; targetId: string } | null
}

export type ParSource = 'played' | 'courseview' | 'estimate'

export interface CoursePrepOverlay {
  w: number
  h: number
  ppm: number
  ln: number
  route: Array<[number, number, number]> // [px, py, cumMetres]
}

export interface CoursePrepStep {
  club: string | null
  note: string
}

export interface CoursePrepMissingData {
  label?: string
  reason?: string
}

export interface CoursePrepCandidateRoute {
  id: string
  club?: string
  carryM?: number
  riskScore?: number
}

export interface CoursePrepCarryTarget {
  kind: string
  distanceM?: number
  enterM?: number
  clearM?: number
  sideM?: number
}

export interface CoursePrepShotDot {
  x: number
  y: number
  club: string | null
  shotType: string
  roundId: string
}

export interface CoursePrepHole {
  hole: number
  par: number
  par_source: ParSource
  blue_yards: number
  route_len_m: number
  route: Array<[number, number, number]>
  geometryCoverage: GeometryCoverageState
  sourceRefs: string[]
  missingData: CoursePrepMissingData[]
  candidateRoutes: CoursePrepCandidateRoute[]
  carryTargets: CoursePrepCarryTarget[]
  steps: CoursePrepStep[]
  cautions: string[]
  landing_m: number | null
  tee_club: string | null
  hazards: { water_carry: Array<[number, number]>; bunkers: Array<[number, number]> }
  map?: { image: string; overlay: CoursePrepOverlay }
  yourShots?: CoursePrepShotDot[]
}

export interface CoursePrepClub {
  name: string
  m: number
  yd: number
}

export interface CoursePrepResponse {
  schema: 'ai-caddie-course-prep-v1'
  globalId: number
  holeCount: number
  clubs: CoursePrepClub[]
  holes: CoursePrepHole[]
}

export type StatsWindow = 'all' | '12m' | 'last10'

export interface CourseSearchMatch {
  globalId: number
  name: string
  holes: number | null
  city: string | null
  province: string | null
  ratio: number
}

export interface CourseSearchResponse {
  schema: 'ai-caddie-course-search-v1'
  query: string
  matches: CourseSearchMatch[]
}

export interface PrepTip {
  priority: number
  severity: 'high' | 'medium' | 'info'
  text: string
  basis: string
  sourceRefs: string[]
}

export interface PrepTipsResponse {
  schema: 'ai-caddie-prep-tips-v1'
  courseKey: string | null
  tips: PrepTip[]
}
