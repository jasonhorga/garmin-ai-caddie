export type DataQualityState = 'good' | 'partial' | 'missing'
export type ScoreClass = 'eagle' | 'birdie' | 'par' | 'bogey' | 'double' | 'missing'

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

export type ConnectorState = 'ready' | 'no_data' | 'reauth_required' | 'error'
export type ResolvedDataMode = 'local' | 'fixture'

export interface ConnectorStatus {
  name: 'garmin_cn_web_session'
  state: ConnectorState
  detail: string
  canSync: boolean
  reauthRequired: boolean
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
}
