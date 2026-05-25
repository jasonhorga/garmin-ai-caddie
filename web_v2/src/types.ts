export type DataQualityState = 'good' | 'partial' | 'missing'
export type ScoreClass = 'eagle' | 'birdie' | 'par' | 'bogey' | 'double' | 'missing'
export type AnnotationTargetType = 'round' | 'hole' | 'shot' | 'decision'
export type AnnotationKind =
  | 'round_note'
  | 'hole_note'
  | 'shot_note'
  | 'issue_tag'
  | 'club_correction'
  | 'lie_correction'
  | 'penalty_correction'
  | 'putt_correction'
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
}

export interface DistributionBucket {
  label: string
  start: number
  count: number
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
  courses: Array<Record<string, unknown>>
  holes: Array<Record<string, unknown>>
  clubs: Array<Record<string, unknown>>
  issues: Array<Record<string, unknown>>
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

export type ConnectorState = 'ready' | 'no_data' | 'reauth_required' | 'error'
export type ResolvedDataMode = 'local' | 'fixture'

export interface ConnectorStatus {
  name: 'garmin_cn_web_session'
  state: ConnectorState
  detail: string
  canSync: boolean
  reauthRequired: boolean
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
