export type DataQualityState = 'good' | 'partial' | 'missing'
export type ScoreClass = 'eagle' | 'birdie' | 'par' | 'bogey' | 'double' | 'missing'
export type CaddieShotType = 'tee' | 'approach' | 'recovery'
export type AnnotationTargetType = 'round' | 'hole' | 'shot' | 'decision'
export type MediaTargetType = 'round' | 'hole' | 'shot'
export type MediaKind = 'photo' | 'video'
export type MediaPrivacyState = 'private_local' | 'synced' | 'redacted'
export type GeometryCoverageState = 'ready' | 'partial' | 'missing'
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
  targetType: MediaTargetType
  targetId: string
  mediaId: string
  mediaKind: MediaKind | null
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
  evidence: Array<Record<string, unknown>>
  missingData: Array<Record<string, unknown>>
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

export interface HistoryRoundsResponse {
  schema: 'ai-caddie-history-rounds-v2'
  total: number
  groups: MonthRoundGroup[]
  emptyState: EmptyState | null
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
}

export type ReportKind = 'round' | 'trend'
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

export interface ConnectorStatus {
  name: 'garmin_cn_web_session' | 'garmin_oauth_feasibility'
  state: ConnectorState
  detail: string
  canSync: boolean
  reauthRequired: boolean
  nextAction?: ConnectorNextAction | null
  track?: string | null
  feasibilityQuestions?: string[]
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
}

export interface SyncRunResponse {
  schema: 'ai-caddie-sync-run-v2'
  connector: 'garmin_cn_web_session'
  state: ConnectorState
  detail: string
  reauthRequired: boolean
  errorCode: string | null
  snapshot: SyncSnapshotPayload | null
}

export interface GarminSessionImportRequest {
  webSessionHeader: string
  antiForgeryValue: string
}

export interface GarminSessionImportResponse {
  schema: 'ai-caddie-garmin-session-import-v1'
  connector: 'garmin_cn_web_session'
  state: 'stored'
  detail: string
  sessionFieldCount: number
  antiForgeryPresent: boolean
  source: 'manual_paste'
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
